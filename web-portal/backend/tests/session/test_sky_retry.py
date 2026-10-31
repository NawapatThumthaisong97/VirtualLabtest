"""
กลุ่ม: ต่อ SkyPilot API server ไม่ได้ชั่วคราว (ApiServerConnectionError ทันที ทั้งที่ server ยังดี)

เจอบน VM 2026-11-01: launch EC2 สำเร็จ แต่ job_status ถัดมาพัง → session FAILED + sky.down พังอีก → EC2 ค้าง
"""
import pytest
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
