"""
Exp2: ตารางเรียน (class_schedules / class_slots) + prewarm scheduler อ่านคาบจาก DB

ใช้ DB เทส (virtual_lab_test) เพราะ constraint หลายตัวอยู่ที่ระดับ Postgres และ FakeK8s แทน cluster
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import IntegrityError

from app.configs.settings import settings
from app.exceptions.domain import ValidationError
from app.models.class_schedule import ClassSchedule
from app.models.class_slot import ClassSlot, ClassSlotStatus
from app.models.courses import Course
from app.models.lab import RunTarget
from app.models.lab_image import LabImage
from app.models.user import User
from app.services.prewarm_scheduler import sync_prewarm
from app.services.prewarm_service import PrewarmService, daemonset_name
from app.services.schedule_service import generate_slots
from app.services.warm_pod_service import WarmPodService, build_warm_daemonset, warm_daemonset_name
from tests.conftest import REGISTRY
from tests.fakes import FakeK8s

BKK = ZoneInfo("Asia/Bangkok")
NOW = datetime(2026, 10, 19, 1, 0, tzinfo=timezone.utc)  # จันทร์ 08:00 เวลาไทย
HELLO_V1 = f"{REGISTRY}/vlab/hello:v1"
HELLO_V2 = f"{REGISTRY}/vlab/hello:v2"


@pytest.fixture
def world(db):
    user = User(email=f"t-{uuid.uuid4().hex[:8]}@test.local", name="Teacher")
    db.add(user)
    db.flush()

    def course(code):
        c = Course(code=f"{code}-{uuid.uuid4().hex[:4]}", name=code, lecturer_name="T", created_by=user.id)
        db.add(c)
        db.flush()
        return c

    se, devops = course("SE301"), course("DEVOPS201")

    def image(tag, c):
        img = LabImage(uploaded_by=user.id, course_id=c.id, repository="vlab/hello", tag=tag,
                       image_digest=f"sha256:{uuid.uuid4().hex}", size_mb=55)
        db.add(img)
        db.flush()
        return img

    ns = SimpleNamespace(user=user, se=se, devops=devops, v1=image("v1", se), v2=image("v2", devops))
    db.commit()
    return ns


@pytest.fixture
def add_slot(db, world):
    def _add(course=None, image=None, start=timedelta(minutes=10), length=timedelta(hours=3),
             status=ClassSlotStatus.SCHEDULED, run_target=RunTarget.KUBERNETES, deleted=False, commit=True):
        slot = ClassSlot(course_id=(course or world.se).id, lab_image_id=(image or world.v1).id,
                         starts_at=NOW + start, ends_at=NOW + start + length, expected_seats=40,
                         status=status, run_target=run_target, created_by=world.user.id,
                         deleted_at=NOW if deleted else None)
        db.add(slot)
        if commit:
            db.commit()
        return slot
    return _add


@pytest.fixture
def k8s():
    fake = FakeK8s()
    fake.add_node("worker-pete")
    fake.add_node("thinkpad")
    return fake


@pytest.fixture
def prewarm(k8s, monkeypatch):
    monkeypatch.setattr(settings, "PREWARM_LEAD_MINUTES", 30)
    monkeypatch.setattr(settings, "PREWARM_TARGETS", [])
    return PrewarmService(k8s, namespace="default")


def pull_done(k8s, image):
    """จำลองว่าทุก worker pull image เสร็จแล้ว (pod running)"""
    name = daemonset_name(image)
    k8s.ds_status[name] = (2, 2)
    for w in ("worker-pete", "thinkpad"):
        k8s.add_pod(name, w, running_after=5)


def schedule_of(db, world, **overrides):
    fields = dict(course_id=world.se.id, weekday=0, start_time=time(9, 0), end_time=time(12, 0),
                  valid_from=date(2026, 9, 21), valid_until=date(2026, 11, 15),  # 8 สัปดาห์
                  default_lab_image_id=world.v1.id, expected_seats=40, created_by=world.user.id)
    fields.update(overrides)
    s = ClassSchedule(**fields)
    db.add(s)
    db.commit()
    return s


class TestGenerateSlots:
    """Generate class_slots from a weekly schedule"""

    def test_eight_mondays(self, db, world):
        """8-week term gives 8 slots, all Monday 09:00-12:00 Bangkok time"""
        slots = generate_slots(db, schedule_of(db, world))

        assert len(slots) == 8
        for s in slots:
            local_start, local_end = s.starts_at.astimezone(BKK), s.ends_at.astimezone(BKK)
            assert (local_start.weekday(), local_start.time(), local_end.time()) == (0, time(9), time(12))
            assert s.starts_at.utcoffset() == timedelta(0)  # เก็บเป็น UTC (= 02:00Z)
            assert (s.expected_seats, s.lab_image_id, s.status) == (40, world.v1.id, ClassSlotStatus.SCHEDULED)

    def test_valid_from_not_on_weekday(self, db, world):
        """valid_from on a Wednesday starts from the next Monday"""
        slots = generate_slots(db, schedule_of(db, world, valid_from=date(2026, 9, 23),
                                               valid_until=date(2026, 10, 5)))
        assert [s.starts_at.astimezone(BKK).date() for s in slots] == [date(2026, 9, 28), date(2026, 10, 5)]

    def test_idempotent(self, db, world):
        """Calling generate again creates nothing new"""
        schedule = schedule_of(db, world)
        generate_slots(db, schedule)

        assert generate_slots(db, schedule) == []
        assert db.query(ClassSlot).filter(ClassSlot.schedule_id == schedule.id).count() == 8

    def test_deleted_slot_not_recreated(self, db, world):
        """A soft-deleted slot does not come back on regenerate"""
        schedule = schedule_of(db, world)
        first = generate_slots(db, schedule)[0]
        first.deleted_at = datetime.now(timezone.utc)
        db.commit()

        assert generate_slots(db, schedule) == []

    def test_no_default_image(self, db, world):
        """Schedule without default image is rejected"""
        with pytest.raises(ValidationError):
            generate_slots(db, schedule_of(db, world, default_lab_image_id=None))


class TestSlotConstraints:
    """DB constraints on class_slots / class_schedules"""

    def test_overlap_same_course_rejected(self, db, add_slot):
        """Overlapping slot of the same course is rejected by the exclusion constraint"""
        add_slot(start=timedelta(hours=1))
        add_slot(start=timedelta(hours=2), commit=False)
        with pytest.raises(IntegrityError, match="ex_class_slots_no_overlap"):
            db.flush()
        db.rollback()

    @pytest.mark.parametrize("case", ["other course", "back to back", "cancelled", "deleted"])
    def test_overlap_allowed(self, db, world, add_slot, case):
        """Not an overlap: other course / back to back / cancelled / soft-deleted"""
        add_slot(start=timedelta(hours=1),
                 status=ClassSlotStatus.CANCELLED if case == "cancelled" else ClassSlotStatus.SCHEDULED,
                 deleted=case == "deleted")
        if case == "other course":
            add_slot(course=world.devops, start=timedelta(hours=2))
        elif case == "back to back":
            add_slot(start=timedelta(hours=4))  # คาบแรก 1-4 คาบสอง 4-7
        else:
            add_slot(start=timedelta(hours=2))

    def test_ends_before_starts(self, db, add_slot):
        """ends_at must be after starts_at"""
        add_slot(length=timedelta(0), commit=False)
        with pytest.raises(IntegrityError, match="ck_class_slots_time_order"):
            db.flush()
        db.rollback()

    def test_bad_weekday(self, db, world):
        """weekday outside 0-6 is rejected"""
        db.add(ClassSchedule(course_id=world.se.id, weekday=7, start_time=time(9), end_time=time(12),
                             valid_from=date(2026, 9, 21), valid_until=date(2026, 11, 15),
                             expected_seats=40, created_by=world.user.id))
        with pytest.raises(IntegrityError, match="ck_class_schedules_weekday"):
            db.flush()
        db.rollback()


class TestSchedulerWithSlots:
    """Prewarm scheduler reads class_slots"""

    def test_within_lead_time(self, db, prewarm, k8s, add_slot):
        """Slot starting within 30 min: DaemonSet created, slot PREWARMING"""
        slot = add_slot(start=timedelta(minutes=20))

        result = sync_prewarm(prewarm, db, NOW)

        assert result["created"] == [HELLO_V1]
        db.refresh(slot)
        assert slot.status == ClassSlotStatus.PREWARMING

    def test_too_early(self, db, prewarm, k8s, add_slot):
        """Slot starting in 2 hours: nothing yet"""
        slot = add_slot(start=timedelta(hours=2))

        assert sync_prewarm(prewarm, db, NOW)["created"] == []
        db.refresh(slot)
        assert slot.status == ClassSlotStatus.SCHEDULED

    def test_ready_when_all_workers_pulled(self, db, prewarm, k8s, add_slot):
        """All workers ready: slot READY"""
        slot = add_slot()
        sync_prewarm(prewarm, db, NOW)
        pull_done(k8s, HELLO_V1)

        result = sync_prewarm(prewarm, db, NOW + timedelta(minutes=1))

        db.refresh(slot)
        assert slot.status == ClassSlotStatus.READY
        assert result["slots"] == {str(slot.id): "PREWARMING -> READY"}

    def test_ready_back_to_prewarming_when_worker_drops(self, db, prewarm, k8s, add_slot):
        """Regression: worker drops after READY → slot back to PREWARMING, READY again when it returns"""
        slot = add_slot()
        sync_prewarm(prewarm, db, NOW)
        pull_done(k8s, HELLO_V1)
        sync_prewarm(prewarm, db, NOW + timedelta(minutes=1))

        k8s.nodes = []
        k8s.add_node("worker-pete", ready=False, not_ready_for=timedelta(seconds=10))
        k8s.add_node("thinkpad")
        k8s.ds_status[daemonset_name(HELLO_V1)] = (1, 1)  # k8s ลด desired ตามเครื่องที่หลุด
        sync_prewarm(prewarm, db, NOW + timedelta(minutes=2))
        db.refresh(slot)
        assert slot.status == ClassSlotStatus.PREWARMING

        k8s.nodes = []
        k8s.add_node("worker-pete")
        k8s.add_node("thinkpad")
        sync_prewarm(prewarm, db, NOW + timedelta(minutes=3))
        db.refresh(slot)
        assert slot.status == ClassSlotStatus.READY

    def test_two_classes_first_ends(self, db, world, prewarm, k8s, add_slot):
        """Two classes, different images: first class ends, only its DaemonSet is removed"""
        first = add_slot(image=world.v1, length=timedelta(hours=1))
        second = add_slot(course=world.devops, image=world.v2, length=timedelta(hours=3))
        assert sync_prewarm(prewarm, db, NOW)["created"] == [HELLO_V1, HELLO_V2]

        result = sync_prewarm(prewarm, db, NOW + timedelta(hours=2))

        assert result["removed"] == [HELLO_V1]
        assert set(prewarm.list_managed()) == {HELLO_V2}
        db.refresh(first)
        db.refresh(second)
        assert (first.status, second.status) == (ClassSlotStatus.DONE, ClassSlotStatus.PREWARMING)

    def test_two_classes_same_image(self, db, world, prewarm, k8s, add_slot):
        """Two classes, same image: DaemonSet kept until the last one ends"""
        add_slot(image=world.v1, length=timedelta(hours=1))
        add_slot(course=world.devops, image=world.v1, length=timedelta(hours=3))
        sync_prewarm(prewarm, db, NOW)

        assert sync_prewarm(prewarm, db, NOW + timedelta(hours=2))["removed"] == []
        assert sync_prewarm(prewarm, db, NOW + timedelta(hours=4))["removed"] == [HELLO_V1]

    @pytest.mark.parametrize("kind", ["aws", "cancelled", "deleted"])
    def test_ignored_slots(self, db, prewarm, k8s, add_slot, kind):
        """AWS / cancelled / soft-deleted slots are not pre-warmed"""
        add_slot(run_target=RunTarget.AWS if kind == "aws" else RunTarget.KUBERNETES,
                 status=ClassSlotStatus.CANCELLED if kind == "cancelled" else ClassSlotStatus.SCHEDULED,
                 deleted=kind == "deleted")

        assert sync_prewarm(prewarm, db, NOW)["created"] == []

    def test_past_slot_done(self, db, prewarm, k8s, add_slot):
        """Slot that already ended is marked DONE without touching K8s"""
        slot = add_slot(start=timedelta(days=-7))

        result = sync_prewarm(prewarm, db, NOW)

        db.refresh(slot)
        assert slot.status == ClassSlotStatus.DONE
        assert result["created"] == [] and k8s.created == []


class TestWarmPodScheduler:
    """Warm pod DaemonSets follow class slots"""

    @pytest.fixture
    def warm(self, k8s, monkeypatch):
        monkeypatch.setattr(settings, "WARM_POD_ENABLED", True)
        return WarmPodService(k8s, namespace="default")

    def test_created_with_class(self, db, world, prewarm, warm, k8s, add_slot):
        """Slot within lead time: warm DaemonSet runs the lab with hostPort, separate from pre-pull"""
        world.v1.exposed_ports = [8080]
        world.v1.entrypoint_script = "httpd -f -p 8080"
        world.v1.env_vars = {"IDE_PASSWORD": "x"}
        db.commit()
        add_slot()

        result = sync_prewarm(prewarm, db, NOW, warm=warm)

        assert result["warm_created"] == ["vlab/hello:v1"]
        name = warm_daemonset_name(world.v1)
        container = k8s.daemonsets[name]["spec"]["template"]["spec"]["containers"][0]
        assert container["image"] == HELLO_V1
        assert container["command"] == ["/bin/sh", "-c", "httpd -f -p 8080"]
        assert container["ports"] == [{"containerPort": 8080, "hostPort": 8080}]
        assert {"name": "IDE_PASSWORD", "value": "x"} in container["env"]
        assert set(prewarm.list_managed()) == {HELLO_V1}  # pre-pull ยังสร้างแยกตามเดิม
        assert set(warm.list_managed()) == {str(world.v1.id)}

    def test_class_end_keeps_claimed_pod(self, db, world, prewarm, warm, k8s, add_slot):
        """Class ends: DaemonSet deleted as Orphan, free pods deleted, claimed pod (student still working) kept"""
        add_slot(length=timedelta(hours=1))
        sync_prewarm(prewarm, db, NOW, warm=warm)
        name = warm_daemonset_name(world.v1)
        free = k8s.add_warm_pod(name, "thinkpad", world.v1.id)
        claimed = k8s.add_warm_pod(name, "worker-pete", world.v1.id, state="claimed")

        result = sync_prewarm(prewarm, db, NOW + timedelta(hours=2), warm=warm)

        assert result["warm_removed"] == [name]
        assert k8s.ds_delete_policy[name] == "Orphan"
        assert k8s.pod(free.metadata.name) is None
        assert k8s.pod(claimed.metadata.name) is not None

    def test_disabled_no_warm(self, db, world, prewarm, k8s, add_slot):
        """warm=None (WARM_POD_ENABLED off): only pre-pull DaemonSet"""
        add_slot()

        result = sync_prewarm(prewarm, db, NOW)

        assert "warm_created" not in result
        assert all(not n.startswith("warm-") for n in k8s.daemonsets)

    def test_image_entrypoint_and_resources(self, world):
        """Empty entrypoint uses the image CMD; "2+" / "4+" become integer k8s requests"""
        world.v1.entrypoint_script = ""
        world.v1.cpu_requirement, world.v1.memory_requirement = "2+", "4+"

        container = build_warm_daemonset(world.v1)["spec"]["template"]["spec"]["containers"][0]

        assert "command" not in container
        assert container["resources"] == {"requests": {"cpu": "2000m", "memory": "4096Mi"}}
