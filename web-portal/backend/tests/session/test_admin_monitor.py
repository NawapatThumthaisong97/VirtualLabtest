"""
กลุ่ม 8: หน้า admin monitor — session ผูกคาบ (class_slot_id) + infra map / room usage จาก node จริง
(docs/ADMIN_MONITOR.md PR 1)
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.class_slot import ClassSlot, ClassSlotStatus
from app.models.session import SessionStatus
from app.services.admin_monitor_service import AdminMonitorService
from tests.fakes import FakeK8s
from tests.session.conftest import sessions_of
from tests.session.test_warm_pod import PETE_IP, k8s  # noqa: F401 (fixture)


@pytest.fixture
def add_slot(db, world):
    def _add(start=timedelta(minutes=-30), length=timedelta(hours=3), status=ClassSlotStatus.READY,
             deleted=False, room=None, seats=30, now=None):
        now = now or datetime.now(timezone.utc)
        slot = ClassSlot(course_id=world.course.id, lab_image_id=world.k8s_image.id, starts_at=now + start, ends_at=now + start + length,
                         expected_seats=seats, status=status, created_by=world.user.id, room=room,
                         deleted_at=now if deleted else None)
        db.add(slot)
        db.commit()
        return slot
    return _add


class TestSessionSlot:
    """create_session links the session to the class slot running now"""

    @pytest.fixture(autouse=True)
    def lab_machine(self, monkeypatch):
        from app.configs.settings import settings
        monkeypatch.setattr(settings, "LAB_ISOLATION_ENABLED", True)

    def test_slot_now(self, svc, db, world, fake_sky, k8s, add_slot):
        """Slot of this course running now -> class_slot_id set"""
        slot = add_slot()
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        [s] = sessions_of(db, world.user)
        assert s.class_slot_id == slot.id

    @pytest.mark.parametrize("kind", ["future", "past", "cancelled", "deleted"])
    def test_no_slot(self, svc, db, world, fake_sky, k8s, add_slot, kind):
        """No running slot (future / past / cancelled / deleted) -> class_slot_id NULL"""
        if kind == "future":
            add_slot(start=timedelta(hours=1))
        elif kind == "past":
            add_slot(start=timedelta(hours=-5))
        elif kind == "cancelled":
            add_slot(status=ClassSlotStatus.CANCELLED)
        else:
            add_slot(deleted=True)
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        [s] = sessions_of(db, world.user)
        assert s.class_slot_id is None


@pytest.fixture
def cluster():
    fake = FakeK8s()
    fake.add_node("master", control_plane=True)
    fake.add_node("lc123-pc01", room="LC-123")
    fake.add_node("lc123-pc02", room="LC-123")
    fake.add_node("lc123-pc03", room="LC-123", ready=False)
    fake.add_node("lc207-pc01", room="LC-207")
    fake.add_node("spare")
    return fake


class TestInfraMap:
    """GET /admin/infra/map: rooms from node labels, no made-up numbers"""

    def test_rooms(self, db, world, cluster, add_session):
        """Rooms grouped by vlab/room, ready / in-use counted, unassigned last, master excluded"""
        s = add_session(SessionStatus.RUNNING)
        s.node_name = "lc123-pc01"
        db.commit()

        result = AdminMonitorService(db, cluster).get_infra_map()
        k3s, aws = result.clusters

        assert (k3s.status, k3s.control_plane.node, k3s.control_plane.ready) == ("warn", "master", True)
        assert [(r.room, r.status, r.pcs_total, r.pcs_ready, r.pcs_in_use) for r in k3s.rooms] == [
            ("LC-123", "warn", 3, 2, 1),
            ("LC-207", "ok", 1, 1, 0),
            ("unassigned", "ok", 1, 1, 0),
        ]
        assert (aws.type, aws.status, aws.instances_running) == ("cloud", "unknown", 0)
        # ผังห้องแลป: สถานะรายเครื่อง เรียงตามชื่อ
        assert [(m.name, m.ready, m.in_use) for m in k3s.rooms[0].machines] == [
            ("lc123-pc01", True, True),
            ("lc123-pc02", True, False),
            ("lc123-pc03", False, False),
        ]

    def test_aws_count(self, db, world, cluster, add_session):
        """AWS = cloud sessions RUNNING / PENDING; stopped ones not counted"""
        for status in (SessionStatus.RUNNING, SessionStatus.PENDING, SessionStatus.STOPPED):
            s = add_session(status, lab=world.aws_lab)
            s.is_cloud = True
        db.commit()
        aws = AdminMonitorService(db, cluster).get_infra_map().clusters[1]
        assert aws.instances_running == 2

    def test_k8s_down(self, db, world):
        """K3s unreachable -> cluster down, no rooms (not fake capacity)"""
        broken = FakeK8s()
        broken.error = RuntimeError("connection refused")
        k3s = AdminMonitorService(db, broken).get_infra_map().clusters[0]
        assert (k3s.status, k3s.rooms, k3s.control_plane) == ("down", [], None)

    def test_camel_case(self, db, world, cluster):
        """JSON keys are camelCase"""
        data = AdminMonitorService(db, cluster).get_infra_map().model_dump(by_alias=True)
        assert {"controlPlane", "rooms"} <= set(data["clusters"][0])
        assert {"pcsTotal", "pcsReady", "pcsInUse"} <= set(data["clusters"][0]["rooms"][0])


class TestRoomUsage:
    """GET /admin/rooms/usage: PCs in use per room and by which class"""

    def test_slot_shown(self, db, world, cluster, add_session, add_slot):
        """Room in use -> launched + course name and slot time"""
        slot = add_slot()
        for node in ("lc123-pc01", "lc123-pc02"):
            s = add_session(SessionStatus.RUNNING)
            s.node_name, s.class_slot_id = node, slot.id
        db.commit()

        rooms = {r.room: r for r in AdminMonitorService(db, cluster).get_rooms_usage().rooms}

        lc123 = rooms["LC-123"]
        assert (lc123.state, lc123.pcs_in_use, lc123.pcs_total) == ("launched", 2, 3)
        assert (lc123.slot.course, lc123.slot.starts_at, lc123.slot.status) == (
            world.course.name, slot.starts_at, "ready")
        assert (rooms["LC-207"].state, rooms["LC-207"].slot) == ("idle", None)

    # 12:00 เวลาไทย — คาบ ±3 ชม. อยู่ในวันเดียวกันเสมอ ไม่ขึ้นกับเวลาที่รันเทส
    NOON = datetime(2031, 3, 3, 5, 0, tzinfo=timezone.utc)

    def _classes(self, db, cluster, room="LC-123"):
        usage = AdminMonitorService(db, cluster).get_rooms_usage(now=self.NOON)
        return {r.room: r for r in usage.rooms}[room].classes

    @pytest.mark.parametrize("start, status, slot_status, expected", [
        (timedelta(hours=2), ClassSlotStatus.SCHEDULED, "pending", 0),
        (timedelta(minutes=20), ClassSlotStatus.PREWARMING, "preparing", 0),
        (timedelta(minutes=20), ClassSlotStatus.READY, "ready", 0),
        (timedelta(hours=-4), ClassSlotStatus.DONE, "done", 0),
    ], ids=["pending", "preparing", "ready", "done"])
    def test_today_class_status(self, db, world, cluster, add_slot, start, status, slot_status, expected):
        """Today's classes of the room show a status by time even before anyone opens a lab"""
        add_slot(start=start, status=status, room="LC-123", seats=2, now=self.NOON)
        [c] = self._classes(db, cluster)
        assert (c.status, c.in_use, c.seats, c.course) == (slot_status, expected, 2, f"{world.course.code} {world.course.name}")

    def test_in_class_vs_incomplete(self, db, world, cluster, add_slot, add_session):
        """Class started: 2 seats and 2 ready PCs -> in_class; 3 seats but only 2 ready -> incomplete"""
        ok = add_slot(start=timedelta(minutes=-10), length=timedelta(minutes=50), room="LC-123", seats=2, now=self.NOON)
        s = add_session(SessionStatus.RUNNING)
        s.node_name, s.class_slot_id = "lc123-pc01", ok.id
        add_slot(start=timedelta(hours=1), length=timedelta(hours=1), room="LC-123", seats=3, now=self.NOON)
        db.commit()
        first, second = self._classes(db, cluster)
        assert (first.status, first.in_use, first.seats) == ("in_class", 1, 2)

        later = self.NOON + timedelta(hours=1, minutes=5)
        usage = AdminMonitorService(db, cluster).get_rooms_usage(now=later)
        [_, c] = {r.room: r for r in usage.rooms}["LC-123"].classes
        assert (c.status, c.seats, c.pcs_ready) == ("incomplete", 3, 2)

    def test_cancelled_other_room_and_outside_class(self, db, world, cluster, add_slot, add_session):
        """Cancelled / other-room classes hidden; lab opened outside class counted separately"""
        add_slot(start=timedelta(hours=1), status=ClassSlotStatus.CANCELLED, room="LC-123", now=self.NOON)
        add_slot(start=timedelta(hours=1), room="LC-207", now=self.NOON)
        s = add_session(SessionStatus.RUNNING)
        s.node_name = "lc123-pc02"
        db.commit()
        usage = {r.room: r for r in AdminMonitorService(db, cluster).get_rooms_usage(now=self.NOON).rooms}
        assert usage["LC-123"].classes == [] and usage["LC-123"].outside_class == 1

    def test_in_use_without_slot(self, db, world, cluster, add_session):
        """Someone using a PC outside class -> launched, slot null"""
        s = add_session(SessionStatus.RUNNING)
        s.node_name = "lc207-pc01"
        db.commit()
        lc207 = {r.room: r for r in AdminMonitorService(db, cluster).get_rooms_usage().rooms}["LC-207"]
        assert (lc207.state, lc207.pcs_in_use, lc207.slot) == ("launched", 1, None)
