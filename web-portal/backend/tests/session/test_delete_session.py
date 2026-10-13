"""
กลุ่ม 3: delete_session — กดปิด lab
"""
import uuid

import pytest
import sky

from app.exceptions.domain import ClusterOperationError, SessionNotFoundError
from app.models.session import SessionEndReason, SessionStatus


class TestDeleteSession:
    """Delete session"""

    def test_running(self, svc, db, fake_sky, add_session):
        """RUNNING: cluster removed, STOPPED / USER_DELETE, soft deleted"""
        s = add_session(SessionStatus.RUNNING, cluster="music-lab-up")
        fake_sky.clusters["music-lab-up"] = sky.ClusterStatus.UP

        result = svc.delete_session(s.id)

        db.refresh(s)
        assert result["cluster_stopped"] is True
        assert (s.status, s.end_reason) == (SessionStatus.STOPPED, SessionEndReason.USER_DELETE)
        assert s.deleted_at is not None
        assert fake_sky.downed == ["music-lab-up"]

    def test_regression_cluster_already_gone(self, svc, db, fake_sky, add_session):
        """Regression: cluster already removed by autostop still deletes cleanly

        sky.down ของ cluster ที่ไม่มีแล้ว raise ClusterDoesNotExist ต้องไม่กลายเป็น 500
        """
        s = add_session(SessionStatus.RUNNING, cluster="music-lab-gone")

        result = svc.delete_session(s.id)

        db.refresh(s)
        assert result["cluster_stopped"] is False
        assert s.status == SessionStatus.STOPPED
        assert s.deleted_at is not None

    def test_down_error_keeps_session(self, svc, db, fake_sky, add_session):
        """Other sky.down errors return 500 and keep the session"""
        s = add_session(SessionStatus.RUNNING, cluster="music-lab-up")
        fake_sky.clusters["music-lab-up"] = sky.ClusterStatus.UP
        fake_sky.down_error = RuntimeError("API server down")

        with pytest.raises(ClusterOperationError):
            svc.delete_session(s.id)

        db.refresh(s)
        assert s.status == SessionStatus.RUNNING
        assert s.deleted_at is None

    def test_running_without_cluster_name(self, svc, db, fake_sky, add_session):
        """RUNNING without a cluster name (seed data) deletes without calling sky"""
        s = add_session(SessionStatus.RUNNING, cluster=None)

        svc.delete_session(s.id)

        db.refresh(s)
        assert s.deleted_at is not None
        assert fake_sky.downed == []

    def test_unknown_session(self, svc, fake_sky):
        """Unknown session returns not found"""
        with pytest.raises(SessionNotFoundError):
            svc.delete_session(uuid.uuid4())
