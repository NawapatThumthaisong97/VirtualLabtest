"""
กลุ่ม 2: create_session — กด Start Lab

ใช้ Postgres สำหรับเทส (virtual_lab_test) + FakeSky แทน SkyPilot ดู tests/session/conftest.py
"""
import uuid
from datetime import timedelta

import pytest
import sky

from app.exceptions.domain import (
    ClusterOperationError,
    LabImageMissingError,
    LabNotFoundError,
    SessionAlreadyExistsError,
    UserNotFoundError,
)
from app.models.session import SessionEndReason, SessionStatus
from app.services import session_service
from tests.session.conftest import sessions_of


class TestInputValidation:
    """Input validation"""

    def test_unknown_user(self, svc, world, fake_sky):
        """Unknown user returns not found"""
        with pytest.raises(UserNotFoundError):
            svc.create_session(uuid.uuid4(), world.k8s_lab.id)
        assert fake_sky.launched == []

    def test_unknown_lab(self, svc, world, fake_sky):
        """Unknown lab returns not found"""
        with pytest.raises(LabNotFoundError):
            svc.create_session(world.user.id, uuid.uuid4())

    def test_lab_without_image(self, svc, world, fake_sky):
        """Lab without an image is rejected before launching"""
        with pytest.raises(LabImageMissingError):
            svc.create_session(world.user.id, world.no_image_lab.id)
        assert fake_sky.launched == []


class TestLaunchSuccess:
    """Launch success"""

    def test_k3s(self, svc, db, world, fake_sky):
        """K3s lab: PENDING -> RUNNING with job id, endpoints, expires_at"""
        result = svc.create_session(world.user.id, world.k8s_lab.id)

        [s] = sessions_of(db, world.user)
        assert s.status == SessionStatus.RUNNING
        assert s.sky_job_id == 1
        assert s.endpoints == {"8080": "http://10.0.0.5:8080"}
        assert s.is_cloud is False
        assert s.end_reason is None
        assert s.expires_at is not None
        assert result["expires_at"] == s.expires_at
        assert result["cluster_name"].startswith("music-lab-")
        [(cluster, task)] = fake_sky.launched
        assert "ECR_TOKEN" not in (task.secrets or {})  # K3s ไม่ต้องขอ ECR token

    def test_expires_at_uses_lifespan(self, svc, db, world, fake_sky):
        """expires_at is about now + lifespan_minutes"""
        world.k8s_image.lifespan_minutes = 15
        db.commit()
        svc.create_session(world.user.id, world.k8s_lab.id)

        [s] = sessions_of(db, world.user)
        left = s.expires_at - s.started_at
        assert timedelta(minutes=14) < left < timedelta(minutes=16)

    def test_aws(self, svc, db, world, fake_sky):
        """AWS lab: ECR token passed as a secret and is_cloud is true"""
        svc.create_session(world.user.id, world.aws_lab.id)

        [s] = sessions_of(db, world.user)
        assert s.status == SessionStatus.RUNNING
        assert s.is_cloud is True
        [(cluster, task)] = fake_sky.launched
        assert cluster.startswith("music-lab-ide-")
        assert task.secrets["ECR_TOKEN"].get_secret_value() == "fake-ecr-token"

    def test_waits_through_setup(self, svc, db, world, fake_sky):
        """Waits while the job is INIT / PENDING / SETTING_UP until RUNNING"""
        fake_sky.job_statuses = ["INIT", "PENDING", "SETTING_UP", "RUNNING"]
        svc.create_session(world.user.id, world.k8s_lab.id)

        assert sessions_of(db, world.user)[0].status == SessionStatus.RUNNING
        assert fake_sky.job_statuses == ["RUNNING"]


class TestDuplicateStart:
    """Duplicate start"""

    def test_regression_pending_returns_409_without_asking_skypilot(
            self, svc, db, world, fake_sky, add_session):
        """Regression: Start while PENDING returns 409 and never calls sky.status

        เดิมไปถาม sky.status ซึ่งช่วงแรกยังไม่มี record ของ cluster โค้ดเลยคิดว่า cluster หาย
        แล้ว launch ซ้อน (เทสกับ K3s จริงได้ 2 pod)
        """
        add_session(SessionStatus.PENDING, cluster="music-lab-starting")

        with pytest.raises(SessionAlreadyExistsError):
            svc.create_session(world.user.id, world.k8s_lab.id)
        assert fake_sky.status_calls == []
        assert fake_sky.launched == []

    def test_stale_pending_is_cleared(self, svc, db, world, fake_sky, add_session):
        """PENDING older than 20 minutes becomes FAILED / STALE_PENDING and a new launch starts"""
        old = add_session(SessionStatus.PENDING, cluster="music-lab-stuck",
                          started_ago=timedelta(minutes=30))
        fake_sky.clusters["music-lab-stuck"] = sky.ClusterStatus.INIT

        svc.create_session(world.user.id, world.k8s_lab.id)

        db.refresh(old)
        assert (old.status, old.end_reason) == (SessionStatus.FAILED, SessionEndReason.STALE_PENDING)
        assert "music-lab-stuck" in fake_sky.downed
        assert len(fake_sky.launched) == 1

    def test_running_and_cluster_up_returns_409(self, svc, world, fake_sky, add_session):
        """RUNNING with the cluster still up returns 409"""
        add_session(SessionStatus.RUNNING, cluster="music-lab-up")
        fake_sky.clusters["music-lab-up"] = sky.ClusterStatus.UP

        with pytest.raises(SessionAlreadyExistsError):
            svc.create_session(world.user.id, world.k8s_lab.id)
        assert fake_sky.launched == []

    @pytest.mark.parametrize("expires_in, reason", [
        (timedelta(minutes=-1), SessionEndReason.EXPIRED),
        (timedelta(minutes=30), SessionEndReason.LOST),
    ], ids=["after expires_at", "before expires_at"])
    def test_running_but_cluster_gone(self, svc, db, world, fake_sky, add_session,
                                      expires_in, reason):
        """RUNNING but the cluster is gone: old session closed, new launch starts"""
        old = add_session(SessionStatus.RUNNING, cluster="music-lab-gone", expires_in=expires_in)

        svc.create_session(world.user.id, world.k8s_lab.id)

        db.refresh(old)
        assert (old.status, old.end_reason) == (SessionStatus.STOPPED, reason)
        assert len(fake_sky.launched) == 1


class TestLaunchFailure:
    """Launch failure"""

    def test_ecr_token_failure_creates_no_session(self, svc, db, world, fake_sky, monkeypatch):
        """ECR token failure returns 500 and creates no session row"""
        def boom(region):
            raise RuntimeError("no credentials")
        monkeypatch.setattr(session_service, "get_ecr_token", boom)

        with pytest.raises(ClusterOperationError, match="ECR token"):
            svc.create_session(world.user.id, world.aws_lab.id)
        assert sessions_of(db, world.user) == []
        assert fake_sky.launched == []

    def test_provision_failure(self, svc, db, world, fake_sky):
        """Provision failure: FAILED / LAUNCH_FAILED, cluster cleaned up, no log fetch"""
        fake_sky.launch_error = RuntimeError("Failed to provision")

        with pytest.raises(ClusterOperationError, match="Failed to provision"):
            svc.create_session(world.user.id, world.k8s_lab.id)

        [s] = sessions_of(db, world.user)
        assert (s.status, s.end_reason) == (SessionStatus.FAILED, SessionEndReason.LAUNCH_FAILED)
        assert s.ended_at is not None
        assert fake_sky.downed == [s.sky_cluster_name]
        assert fake_sky.tailed == []  # ยังไม่มี job ไม่มี log ให้ดึง

    def test_regression_setup_failure(self, svc, db, world, fake_sky, caplog):
        """Regression: setup failure (FAILED_SETUP) is not saved as RUNNING

        เดิม sky.launch คืนตั้งแต่ส่ง job เลยได้ 201 + RUNNING ทั้งที่ pull ไม่ผ่าน และ EC2 ค้าง
        """
        fake_sky.job_statuses = ["SETTING_UP", "FAILED_SETUP"]

        with pytest.raises(ClusterOperationError, match="FAILED_SETUP"):
            svc.create_session(world.user.id, world.aws_lab.id)

        [s] = sessions_of(db, world.user)
        assert (s.status, s.end_reason) == (SessionStatus.FAILED, SessionEndReason.LAUNCH_FAILED)
        assert fake_sky.downed == [s.sky_cluster_name]
        assert fake_sky.tailed == [(s.sky_cluster_name, 1)]
        assert "no-such-tag" in caplog.text  # ท้าย log ถูกเก็บไว้ก่อนลบ cluster

    def test_job_start_timeout(self, svc, db, world, fake_sky, monkeypatch):
        """Job stuck in SETTING_UP past the timeout is treated as a failure"""
        monkeypatch.setattr(session_service, "JOB_START_TIMEOUT", timedelta(seconds=-1))
        fake_sky.job_statuses = ["SETTING_UP"]

        with pytest.raises(ClusterOperationError, match="still SETTING_UP"):
            svc.create_session(world.user.id, world.k8s_lab.id)
        [s] = sessions_of(db, world.user)
        assert s.end_reason == SessionEndReason.LAUNCH_FAILED
        assert fake_sky.downed == [s.sky_cluster_name]

    def test_cleanup_failure_keeps_original_error(self, svc, db, world, fake_sky):
        """If cleanup also fails, the original launch error is still reported"""
        fake_sky.launch_error = RuntimeError("Failed to provision")
        fake_sky.down_error = RuntimeError("down also broke")

        with pytest.raises(ClusterOperationError, match="Failed to provision"):
            svc.create_session(world.user.id, world.k8s_lab.id)
