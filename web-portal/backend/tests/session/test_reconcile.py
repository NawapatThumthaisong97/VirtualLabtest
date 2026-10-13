"""
กลุ่ม 4: reconciler — ปิด session ที่เครื่องหายเอง
"""
from datetime import timedelta

import pytest
import sky
from sqlalchemy import text

from app.models.session import SessionEndReason, SessionStatus
from app.services import session_reconciler


class TestReconcileSessions:
    """Reconciler"""

    @pytest.mark.parametrize("expires_in, reason", [
        (timedelta(minutes=-1), SessionEndReason.EXPIRED),
        (timedelta(minutes=30), SessionEndReason.LOST),
        (None, SessionEndReason.LOST),
    ], ids=["after expires_at", "before expires_at", "no expires_at"])
    def test_cluster_gone(self, svc, db, fake_sky, add_session, expires_in, reason):
        """Cluster gone: STOPPED with EXPIRED or LOST"""
        s = add_session(SessionStatus.RUNNING, cluster="music-lab-gone", expires_in=expires_in)

        result = svc.reconcile_sessions()

        db.refresh(s)
        assert (s.status, s.end_reason) == (SessionStatus.STOPPED, reason)
        assert s.ended_at is not None
        assert result["stopped"] == ["music-lab-gone"]

    def test_cluster_stopped_counts_as_gone(self, svc, db, fake_sky, add_session):
        """Cluster in STOPPED state counts as gone"""
        s = add_session(SessionStatus.RUNNING, cluster="music-lab-stopped")
        fake_sky.clusters["music-lab-stopped"] = sky.ClusterStatus.STOPPED

        svc.reconcile_sessions()

        db.refresh(s)
        assert s.status == SessionStatus.STOPPED

    @pytest.mark.parametrize("state", [sky.ClusterStatus.UP, sky.ClusterStatus.AUTOSTOPPING,
                                       sky.ClusterStatus.INIT], ids=lambda s: s.value)
    def test_cluster_alive_untouched(self, svc, db, fake_sky, add_session, state):
        """Cluster still UP / AUTOSTOPPING / INIT is left alone

        AUTOSTOPPING ไม่นับว่าหาย เคยเห็นค้างสถานะนี้ตอน autostop ลบเครื่องไม่สำเร็จ
        """
        s = add_session(SessionStatus.RUNNING, cluster="music-lab-alive")
        fake_sky.clusters["music-lab-alive"] = state

        svc.reconcile_sessions()

        db.refresh(s)
        assert s.status == SessionStatus.RUNNING
        assert s.end_reason is None

    def test_skypilot_down_changes_nothing(self, svc, db, fake_sky, add_session):
        """SkyPilot unreachable: RUNNING sessions are not touched"""
        s = add_session(SessionStatus.RUNNING, cluster="music-lab-unknown")
        fake_sky.status_error = ConnectionError("API server down")

        with pytest.raises(ConnectionError):
            svc.reconcile_sessions()

        db.refresh(s)
        assert s.status == SessionStatus.RUNNING

    def test_stale_pending(self, svc, db, fake_sky, add_session):
        """PENDING older than 20 minutes: FAILED / STALE_PENDING, cluster cleaned up"""
        s = add_session(SessionStatus.PENDING, cluster="music-lab-stuck",
                        started_ago=timedelta(minutes=30))
        fake_sky.clusters["music-lab-stuck"] = sky.ClusterStatus.INIT

        result = svc.reconcile_sessions()

        db.refresh(s)
        assert (s.status, s.end_reason) == (SessionStatus.FAILED, SessionEndReason.STALE_PENDING)
        assert fake_sky.downed == ["music-lab-stuck"]
        assert result["failed"] == ["music-lab-stuck"]

    def test_recent_pending_untouched(self, svc, db, fake_sky, add_session):
        """Recent PENDING is left alone and sky.status is not called"""
        s = add_session(SessionStatus.PENDING, cluster="music-lab-starting")

        svc.reconcile_sessions()

        db.refresh(s)
        assert s.status == SessionStatus.PENDING
        assert fake_sky.status_calls == []

    def test_session_without_cluster_name_skipped(self, svc, db, fake_sky, add_session):
        """RUNNING without a cluster name (seed data) is skipped"""
        s = add_session(SessionStatus.RUNNING, cluster=None)

        svc.reconcile_sessions()

        db.refresh(s)
        assert s.status == SessionStatus.RUNNING
        assert fake_sky.status_calls == []

    def test_one_status_call_with_refresh(self, svc, db, fake_sky, add_session):
        """Many sessions: one sky.status call per round, with refresh=AUTO"""
        for i in range(3):
            add_session(SessionStatus.RUNNING, cluster=f"music-lab-{i}")
        fake_sky.clusters["music-lab-1"] = sky.ClusterStatus.UP

        result = svc.reconcile_sessions()

        [(names, refresh)] = fake_sky.status_calls
        assert sorted(names) == ["music-lab-0", "music-lab-1", "music-lab-2"]
        assert refresh == sky.StatusRefreshMode.AUTO
        assert sorted(result["stopped"]) == ["music-lab-0", "music-lab-2"]


class TestReconcilerLock:
    """Reconciler lock"""

    def test_skips_when_another_backend_holds_the_lock(self, db_engine, monkeypatch):
        """Another backend holding the advisory lock: this round is skipped"""
        monkeypatch.setattr(session_reconciler, "engine", db_engine)
        with db_engine.connect() as other:
            other.execute(text("SELECT pg_advisory_lock(:k)"),
                          {"k": session_reconciler.ADVISORY_LOCK_KEY})
            try:
                assert session_reconciler.reconcile_once() is None
            finally:
                other.execute(text("SELECT pg_advisory_unlock(:k)"),
                              {"k": session_reconciler.ADVISORY_LOCK_KEY})
