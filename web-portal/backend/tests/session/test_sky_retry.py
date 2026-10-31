"""
กลุ่ม: ต่อ SkyPilot API server ไม่ได้ชั่วคราว (ApiServerConnectionError ทันที ทั้งที่ server ยังดี)

เจอบน VM 2026-11-01: launch EC2 สำเร็จ แต่ job_status ถัดมาพัง → session FAILED + sky.down พังอีก → EC2 ค้าง
"""
from datetime import datetime, timedelta

import pytest
import sky
from sky.exceptions import ApiServerConnectionError

from app.exceptions.domain import ClusterOperationError
from app.models.session import SessionEndReason, SessionStatus
from app.services import session_service
from tests.session.conftest import sessions_of


class TestRetry:
    """Transient API server connection errors are retried"""

    def test_job_status_blip_launch_ok(self, svc, db, world, fake_sky):
        """job_status fails twice then works -> session RUNNING, nothing downed"""
        fake_sky.connection_errors = {"job_status": 2}
        svc.create_session(world.user.id, world.aws_lab.id)

        [s] = sessions_of(db, world.user)
        assert s.status == SessionStatus.RUNNING and fake_sky.downed == []

    def test_endpoints_blip(self, svc, db, world, fake_sky):
        """endpoints fails once -> still RUNNING with endpoints"""
        fake_sky.connection_errors = {"endpoints": 1}
        result = svc.create_session(world.user.id, world.aws_lab.id)
        assert result["endpoints"] == {"8080": "http://10.0.0.5:8080"}

    def test_down_after_failed_launch_retried(self, svc, db, world, fake_sky):
        """Server really unreachable for job_status (3 tries) -> FAILED, and down retried until it works (no leak)"""
        fake_sky.connection_errors = {"job_status": 3, "down": 2}
        with pytest.raises(ClusterOperationError):
            svc.create_session(world.user.id, world.aws_lab.id)

        [s] = sessions_of(db, world.user)
        assert (s.status, s.end_reason) == (SessionStatus.FAILED, SessionEndReason.LAUNCH_FAILED)
        assert s.sky_cluster_name not in fake_sky.clusters      # EC2 ถูกลบจริง ไม่ค้าง

    def test_user_close_retried(self, svc, db, world, fake_sky):
        """Close Lab while API blips -> cluster still downed, session STOPPED"""
        svc.create_session(world.user.id, world.aws_lab.id)
        [s] = sessions_of(db, world.user)
        fake_sky.connection_errors = {"down": 2}
        svc.delete_session(s.id)
        assert s.status == SessionStatus.STOPPED and s.sky_cluster_name not in fake_sky.clusters

    def test_gives_up_after_attempts(self, fake_sky):
        """Still failing after SKY_RETRY_ATTEMPTS -> error raised (not swallowed)"""
        calls = []

        def always():
            calls.append(1)
            raise ApiServerConnectionError("http://fake")
        with pytest.raises(ApiServerConnectionError):
            session_service.sky_call(always)
        assert len(calls) == session_service.SKY_RETRY_ATTEMPTS

    def test_other_errors_not_retried(self, fake_sky):
        """Real errors (e.g. ClusterDoesNotExist / RuntimeError) go straight through"""
        calls = []

        def boom():
            calls.append(1)
            raise RuntimeError("InsufficientInstanceCapacity")
        with pytest.raises(RuntimeError):
            session_service.sky_call(boom)
        assert calls == [1]


class TestLeakSweep:
    """Reconciler downs clusters of FAILED sessions that are still up (down failed at launch time)"""

    def _failed(self, db, add_session, cluster, ended_ago):
        s = add_session(SessionStatus.FAILED, cluster=cluster)
        s.end_reason = SessionEndReason.LAUNCH_FAILED
        s.ended_at = datetime.utcnow() - ended_ago
        db.commit()
        return s

    def test_leaked_cluster_downed(self, svc, db, fake_sky, add_session):
        """FAILED 10 min ago, cluster still UP -> downed by reconciler"""
        self._failed(db, add_session, "music-lab-leak", timedelta(minutes=10))
        fake_sky.clusters["music-lab-leak"] = sky.ClusterStatus.UP

        result = svc.reconcile_sessions()
        assert result["leaked_downed"] == ["music-lab-leak"] and "music-lab-leak" not in fake_sky.clusters

    def test_old_failed_ignored(self, svc, db, fake_sky, add_session):
        """FAILED 3 hours ago -> not checked (autostop has removed it)"""
        self._failed(db, add_session, "music-lab-old-fail", timedelta(hours=3))
        result = svc.reconcile_sessions()
        assert result["leaked_downed"] == [] and fake_sky.downed == []

    def test_failed_without_cluster_left(self, svc, db, fake_sky, add_session):
        """FAILED and cluster already gone -> nothing to do"""
        self._failed(db, add_session, "music-lab-cleaned", timedelta(minutes=5))
        assert svc.reconcile_sessions()["leaked_downed"] == [] and fake_sky.downed == []
