"""
กลุ่ม: คาบ online — prelaunch scheduler เปิด EC2 รอไว้ให้นักศึกษาทุกคน และคืนเครื่องที่ไม่มีคนรับ
(docs/AWS_PRELAUNCH.md)

งานยาว (launch / down) ส่ง background ที่รันทันทีแทน thread pool และให้ thread ใช้ DB ของเทส
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.configs.settings import settings
from app.models.class_slot import ClassSlot, ClassSlotStatus
from app.models.cloud_control import CloudControl
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import RunTarget
from app.models.session import Session as SessionModel, SessionEndReason, SessionStatus
from app.models.user import User
from app.exceptions.domain import ClusterOperationError
from app.services import prelaunch_service as pl
from app.services import session_service

NOW = datetime(2031, 3, 3, 9, 0, tzinfo=timezone.utc)


class _SameDb:
    """thread ของ launch เปิด SessionLocal เอง — ในเทสให้ใช้ DB (transaction) ของเทส และ close ไม่ได้ปิดจริง"""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


@pytest.fixture
def run_now(db, monkeypatch, fake_sky):
    monkeypatch.setattr(pl, "SessionLocal", lambda: _SameDb(db))
    jobs = []

    def background(fn):
        jobs.append(fn)
        fn()
    background.jobs = jobs
    return background


@pytest.fixture
def online(db, world):
    """คาบ online ของ world.course เริ่ม NOW+5 นาที (อยู่ในช่วง lead 10 นาที) นักศึกษา 2 คน"""
    second = User(email=f"student2-{uuid.uuid4().hex[:6]}@test.local", name="Student 2")
    db.add(second)
    db.flush()
    db.add(Enrollment(user_id=second.id, course_id=world.course.id, role_in_course=RoleInCourse.STUDENT))

    def make(starts_in=timedelta(minutes=5), target=RunTarget.AWS):
        slot = ClassSlot(course_id=world.course.id, lab_id=world.aws_lab.id, lab_image_id=world.aws_image.id,
                         starts_at=NOW + starts_in, ends_at=NOW + starts_in + timedelta(hours=3),
                         expected_seats=2, run_target=target, created_by=world.user.id)
        db.add(slot)
        db.commit()
        return slot
    make.students = [world.user, second]
    return make


def prelaunched(db, slot):
    return (db.query(SessionModel).filter(SessionModel.class_slot_id == slot.id,
                                          SessionModel.prelaunched_at.isnot(None))
            .order_by(SessionModel.started_at).all())


class TestLaunch:
    """Launch one EC2 per enrolled student before an online class"""

    def test_one_per_student(self, db, world, online, run_now, fake_sky):
        """10 min before class -> 2 students = 2 machines, RUNNING, unclaimed, short autostop, unique names"""
        slot = online()
        result = pl.sync_prelaunch(db, NOW, background=run_now)

        sessions = prelaunched(db, slot)
        assert len(result["launched"]) == 2 and len(sessions) == 2
        assert {s.user_id for s in sessions} == {u.id for u in online.students}
        assert {(s.status, s.is_cloud, s.claimed_at) for s in sessions} == {(SessionStatus.RUNNING, True, None)}
        assert len({s.sky_cluster_name for s in sessions}) == 2
        for _, task in fake_sky.launched:
            assert task.resources.pop().autostop_config.idle_minutes == pl.safety_minutes()
        assert slot.status == ClassSlotStatus.READY

    def test_outside_window(self, db, world, online, run_now, fake_sky):
        """Class in 30 min (before lead) or already started -> nothing launched"""
        online(starts_in=timedelta(minutes=30))
        online(starts_in=timedelta(minutes=-1, hours=-4))
        assert pl.sync_prelaunch(db, NOW, background=run_now)["launched"] == []
        assert fake_sky.launched == []

    def test_onsite_slot_ignored(self, db, world, online, run_now, fake_sky):
        """On-site class (KUBERNETES) -> warm pod's job, no EC2"""
        online(target=RunTarget.KUBERNETES)
        pl.sync_prelaunch(db, NOW, background=run_now)
        assert fake_sky.launched == []

    def test_no_duplicates(self, db, world, online, run_now, fake_sky):
        """Second scheduler tick -> no new machines"""
        online()
        pl.sync_prelaunch(db, NOW, background=run_now)
        assert pl.sync_prelaunch(db, NOW + timedelta(minutes=1), background=run_now)["launched"] == []
        assert len(fake_sky.launched) == 2

    def test_student_already_running(self, db, world, online, run_now, fake_sky, add_session):
        """Student who already opened this lab -> skipped"""
        slot = online()
        add_session(SessionStatus.RUNNING, lab=world.aws_lab)
        pl.sync_prelaunch(db, NOW, background=run_now)
        assert [s.user_id for s in prelaunched(db, slot)] == [online.students[1].id]

    def test_max_parallel(self, db, world, online, monkeypatch, fake_sky):
        """PRELAUNCH_MAX_PARALLEL=1 and launches still running -> 1 per tick"""
        monkeypatch.setattr(settings, "PRELAUNCH_MAX_PARALLEL", 1)
        slot = online()
        never_runs = []          # ไม่รันงาน = launch ยังไม่เสร็จ (PENDING ค้าง)
        pl.sync_prelaunch(db, NOW, background=never_runs.append)
        pl.sync_prelaunch(db, NOW + timedelta(minutes=1), background=never_runs.append)
        assert [s.status for s in prelaunched(db, slot)] == [SessionStatus.PENDING]

    def test_failed_launch_retried(self, db, world, online, run_now, fake_sky):
        """Launch fails -> FAILED + down; next tick tries again"""
        slot = online()
        fake_sky.launch_error = RuntimeError("InsufficientInstanceCapacity")
        pl.sync_prelaunch(db, NOW, background=run_now)
        assert {s.status for s in prelaunched(db, slot)} == {SessionStatus.FAILED}

        fake_sky.launch_error = None
        pl.sync_prelaunch(db, NOW + timedelta(minutes=1), background=run_now)
        assert sorted(s.status.name for s in prelaunched(db, slot)) == ["FAILED", "FAILED", "RUNNING", "RUNNING"]

    def test_burst_disabled(self, db, world, online, run_now, fake_sky):
        """Admin turned cloud burst off -> no machines launched"""
        online()
        db.merge(CloudControl(id=1, burst_enabled=False))
        db.commit()
        result = pl.sync_prelaunch(db, NOW, background=run_now)
        assert fake_sky.launched == [] and result["errors"] == ["cloud burst disabled"]


class TestExpire:
    """Unclaimed machines are released PRELAUNCH_CLAIM_MINUTES after class starts"""

    def test_unclaimed_released(self, db, world, online, run_now, fake_sky):
        """15 min after start: unclaimed -> STOPPED / PRELAUNCH_UNCLAIMED + sky down; claimed one stays"""
        slot = online()
        pl.sync_prelaunch(db, NOW, background=run_now)
        claimed, unclaimed = prelaunched(db, slot)
        claimed.claimed_at = NOW + timedelta(minutes=6)
        db.commit()

        later = slot.starts_at + timedelta(minutes=settings.PRELAUNCH_CLAIM_MINUTES)
        result = pl.sync_prelaunch(db, later, background=run_now)

        assert result["expired"] == [unclaimed.sky_cluster_name]
        assert (unclaimed.status, unclaimed.end_reason) == (SessionStatus.STOPPED, SessionEndReason.PRELAUNCH_UNCLAIMED)
        assert fake_sky.downed == [unclaimed.sky_cluster_name]
        assert claimed.status == SessionStatus.RUNNING

    def test_not_before_deadline(self, db, world, online, run_now, fake_sky):
        """14 min after start -> still waiting for students"""
        slot = online()
        pl.sync_prelaunch(db, NOW, background=run_now)
        early = slot.starts_at + timedelta(minutes=settings.PRELAUNCH_CLAIM_MINUTES - 1)
        assert pl.sync_prelaunch(db, early, background=run_now)["expired"] == []

    def test_slot_done_after_end(self, db, world, online, run_now, fake_sky):
        """Class over -> slot DONE"""
        slot = online()
        pl.sync_prelaunch(db, slot.ends_at, background=run_now)
        assert slot.status == ClassSlotStatus.DONE


def _started_online(online):
    """คาบ online ที่เริ่มไปแล้ว 1 นาที (create_session ดูเวลาจริง ไม่ใช่ NOW)"""
    return online(starts_in=datetime.now(timezone.utc) - NOW - timedelta(minutes=1))


def _prelaunch_for(db, svc, world, slot, user, status=SessionStatus.RUNNING):
    """record ที่ scheduler เปิดรอไว้ให้ user (ข้าม sync_prelaunch ตรงนี้ไม่ต้องอิงช่วงเวลา lead)"""
    session, _task = svc._new_sky_session(user.id, world.aws_lab, world.aws_image, RunTarget.AWS, None,
                                          class_slot_id=slot.id, prelaunched_at=datetime.now(timezone.utc),
                                          autostop_minutes=pl.safety_minutes())
    if status == SessionStatus.RUNNING:
        session.endpoints = {"8080": "http://10.10.2.7:8080"}
    session.status = status
    db.commit()
    return session


class TestClaim:
    """Student presses Start in an online class and gets the machine launched for them"""

    def test_claim_running(self, db, svc, world, online, fake_sky):
        """Machine ready -> returned at once, claimed_at set, autostop reset to lifespan, nothing launched"""
        slot = _started_online(online)
        waiting = _prelaunch_for(db, svc, world, slot, world.user)

        result = svc.create_session(world.user.id, world.aws_lab.id)

        assert result["session_id"] == waiting.id and result["endpoints"] == {"8080": "http://10.10.2.7:8080"}
        assert waiting.claimed_at is not None
        assert fake_sky.autostops == [(waiting.sky_cluster_name, world.aws_image.lifespan_minutes, True)]
        assert fake_sky.launched == []
        left = waiting.expires_at.replace(tzinfo=None) - datetime.utcnow()
        assert timedelta(minutes=58) < left <= timedelta(minutes=60)

    def test_claim_waits_for_pending(self, db, svc, world, online, fake_sky):
        """Still launching -> wait until the scheduler's thread finishes, then claim (no second machine)"""
        slot = _started_online(online)
        waiting = _prelaunch_for(db, svc, world, slot, world.user, status=SessionStatus.PENDING)

        def finish(clock):
            waiting.status = SessionStatus.RUNNING
            waiting.endpoints = {"8080": "http://10.10.2.8:8080"}
            db.commit()
        session_service.time.on_sleep = finish   # FakeClock ของ fake_sky: รอ 1 รอบแล้ว launch เสร็จ

        result = svc.create_session(world.user.id, world.aws_lab.id)
        assert result["session_id"] == waiting.id and waiting.claimed_at is not None
        assert fake_sky.launched == []

    def test_failed_prelaunch_launches_new(self, db, svc, world, online, fake_sky):
        """Pre-launch failed -> normal Sky launch for the student"""
        slot = _started_online(online)
        failed = _prelaunch_for(db, svc, world, slot, world.user, status=SessionStatus.FAILED)

        result = svc.create_session(world.user.id, world.aws_lab.id)
        assert result["session_id"] != failed.id and len(fake_sky.launched) == 1

    def test_released_then_late_student(self, db, svc, world, online, fake_sky):
        """Machine released (unclaimed) -> late student gets a normal Sky launch"""
        slot = _started_online(online)
        released = _prelaunch_for(db, svc, world, slot, world.user)
        released.status, released.end_reason = SessionStatus.STOPPED, SessionEndReason.PRELAUNCH_UNCLAIMED
        db.commit()

        result = svc.create_session(world.user.id, world.aws_lab.id)
        assert result["run_target"] == "aws" and len(fake_sky.launched) == 1

    def test_autostop_failure_not_claimed(self, db, svc, world, online, fake_sky, monkeypatch):
        """Cannot reset autostop -> error, machine stays unclaimed (student can press again)"""
        slot = _started_online(online)
        waiting = _prelaunch_for(db, svc, world, slot, world.user)

        def broken(*a, **k):
            raise RuntimeError("API server down")
        monkeypatch.setattr(fake_sky, "autostop", broken)

        with pytest.raises(ClusterOperationError):
            svc.create_session(world.user.id, world.aws_lab.id)
        assert waiting.claimed_at is None

    def test_lab_machine_in_online_class_goes_aws(self, db, svc, world, online, fake_sky, monkeypatch):
        """Online class: Start from a lab machine still gets EC2 (no warm pod / pod)"""
        _started_online(online)
        monkeypatch.setattr(svc, "_client_node", lambda ip, always=False: ("worker-pete", "100.83.96.97"))
        monkeypatch.setattr(svc, "_try_warm_pod", lambda *a: pytest.fail("warm pod used in online class"))

        result = svc.create_session(world.user.id, world.aws_lab.id, client_ip="100.83.96.97")
        assert result["run_target"] == "aws" and len(fake_sky.launched) == 1


class TestCancelReleases:
    """Cancelling an online class releases machines nobody has claimed"""

    def test_release_unclaimed_only(self, db, world, online, run_now, fake_sky):
        """2 machines ready, 1 claimed -> cancel releases the other one only"""
        slot = online()
        pl.sync_prelaunch(db, NOW, background=run_now)
        claimed, unclaimed = prelaunched(db, slot)
        claimed.claimed_at = NOW
        db.commit()

        released = pl.release_unclaimed(db, slot.id, background=run_now)

        assert released == [unclaimed.sky_cluster_name]
        assert (unclaimed.status, unclaimed.end_reason) == (SessionStatus.STOPPED, SessionEndReason.PRELAUNCH_UNCLAIMED)
        assert fake_sky.downed == [unclaimed.sky_cluster_name] and claimed.status == SessionStatus.RUNNING

