"""
กลุ่ม 12: Log Explorer หน้า admin — log จากเหตุการณ์จริง (session พัง, เครื่องหลุด, k8s event, budget, burst)
(docs/ADMIN_MONITOR.md PR 5)
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as _ns

import pytest

from app.configs.settings import settings
from app.models.health_check import HealthCheck
from app.models.infrastructure_log import InfrastructureLog
from app.models.session import SessionEndReason, SessionStatus
from app.services import admin_billing_service as billing
from app.services import admin_log_service as logs
from app.services.health_service import check_once
from tests.fakes import FakeK8s

NOW = datetime.now(timezone.utc)


@pytest.fixture
def clean(db):
    db.query(InfrastructureLog).delete()
    db.query(HealthCheck).delete()
    db.commit()
    return db


def all_logs(db, event_type=None):
    q = db.query(InfrastructureLog)
    if event_type:
        q = q.filter(InfrastructureLog.event_type == event_type)
    return q.order_by(InfrastructureLog.timestamp).all()


class TestSessionLogs:
    """Session that ends badly -> one log, user only as anonId"""

    @pytest.mark.parametrize("reason,cloud,event_type,severity,category", [
        (SessionEndReason.LAUNCH_FAILED, True, "CLOUD_LAUNCH_FAILED", "ERROR", "CLOUD"),
        (SessionEndReason.LAUNCH_FAILED, False, "SESSION_FAILED", "ERROR", "CLUSTER"),
        (SessionEndReason.LOST, False, "SESSION_FAILED", "WARNING", "CLUSTER"),
        (SessionEndReason.STALE_PENDING, True, "SESSION_FAILED", "ERROR", "CLOUD"),
    ])
    def test_failed(self, svc, clean, world, add_session, reason, cloud, event_type, severity, category):
        """LAUNCH_FAILED / LOST / STALE_PENDING -> logged with the right type"""
        s = add_session(SessionStatus.RUNNING)
        s.is_cloud = cloud
        svc._end_session(s, SessionStatus.FAILED, reason)
        [log] = all_logs(clean)
        assert (log.event_type, log.severity, log.category) == (event_type, severity, category)
        assert log.anon_id and str(world.user.id) not in log.message and log.anon_id != str(world.user.id)

    @pytest.mark.parametrize("reason", [SessionEndReason.USER_DELETE, SessionEndReason.EXPIRED])
    def test_normal_end_not_logged(self, svc, clean, add_session, reason):
        """User closed / expired normally -> no log"""
        svc._end_session(add_session(SessionStatus.RUNNING), SessionStatus.STOPPED, reason)
        assert all_logs(clean) == []


class TestHealthLogs:
    """Health check writes a log only when status changes"""

    def round(self, db, minutes, **checks):
        check_once(db, [(k, v) for k, v in checks.items()], now=NOW + timedelta(minutes=minutes))

    def test_node_and_service(self, clean):
        """worker drops -> NODE_NOT_READY once; back -> NODE_READY; registry down / ok -> HEALTH_*"""
        ok = lambda detail=None: (lambda: (None, detail, False))   # noqa: E731
        notready = lambda: ("v1", "NotReady: worker-pete (worker)", True)   # noqa: E731

        def boom():
            raise RuntimeError("refused")

        self.round(clean, 0, k8s=ok("2 nodes Ready"), registry=ok())
        self.round(clean, 5, k8s=notready, registry=boom)
        self.round(clean, 10, k8s=notready, registry=boom)      # ไม่เปลี่ยน = ไม่เขียนซ้ำ
        self.round(clean, 15, k8s=ok("2 nodes Ready"), registry=ok())

        assert [(l.event_type, l.source, l.severity) for l in all_logs(clean)] == [
            ("NODE_NOT_READY", "worker-pete", "WARNING"),
            ("HEALTH_DOWN", "registry", "ERROR"),
            ("NODE_READY", "worker-pete", "INFO"),
            ("HEALTH_RECOVERED", "registry", "INFO"),
        ]

    def test_first_round_ok_no_log(self, clean):
        """Very first check all ok -> nothing logged"""
        self.round(clean, 0, backend=lambda: ("1", None, False))
        assert all_logs(clean) == []


class TestPodEvents:
    """k8s Warning events of pods -> POD_EVENT once per event"""

    def event(self, uid, reason, type_="Warning", kind="Pod"):
        return _ns(type=type_, reason=reason, message="Back-off pulling image", count=3,
                   involved_object=_ns(kind=kind, name="lab-pod-1234"), source=_ns(host="worker-pete"),
                   last_timestamp=NOW, event_time=None, metadata=_ns(uid=uid, creation_timestamp=NOW))

    def test_collect(self, clean):
        """Only Warning pod events with known reasons; seen twice -> one log"""
        k8s = FakeK8s()
        events = [self.event("e1", "BackOff"), self.event("e2", "Scheduled", type_="Normal"),
                  self.event("e3", "Failed", kind="Node"), self.event("e4", "Evicted")]
        k8s.list_namespaced_event = lambda ns: _ns(items=events)
        assert logs.collect_pod_events(clean, k8s) == 2
        clean.commit()
        assert logs.collect_pod_events(clean, k8s) == 0
        assert [(l.severity, l.message[:8]) for l in all_logs(clean, "POD_EVENT")] == [
            ("WARNING", "BackOff:"), ("ERROR", "Evicted:")]


class TestBudgetAndBurst:
    """BUDGET_ALERT once per level per month; BURST_TOGGLED on every switch"""

    def test_budget_once(self, clean):
        """Same month + level twice -> one log; over is a separate log"""
        for _ in range(2):
            logs.log_budget_alert(clean, "2026-10", "warn", 170, 200)
            clean.commit()
        logs.log_budget_alert(clean, "2026-10", "over", 205, 200)
        logs.log_budget_alert(clean, "2026-10", "none", 0, 200)
        clean.commit()
        assert [(l.severity, l.metadata_json["level"]) for l in all_logs(clean, "BUDGET_ALERT")] == [
            ("WARNING", "warn"), ("CRITICAL", "over")]

    def test_burst(self, clean, world):
        """Admin switches burst off / on -> two logs with anonId"""
        billing.set_burst(clean, False, "เกิน budget", world.user.id)
        billing.set_burst(clean, True, None, world.user.id)
        rows = all_logs(clean, "BURST_TOGGLED")
        assert [r.message for r in rows] == ["AWS burst disabled: เกิน budget", "AWS burst enabled"]
        assert all(r.anon_id for r in rows)


class TestRead:
    """GET /admin/logs and /admin/logs/histogram"""

    def test_list_and_histogram(self, clean):
        """Filter by category, newest first; histogram buckets old -> new + by type"""
        logs.write_log(clean, "POD_EVENT", "WARNING", "CLUSTER", "p1", "a", timestamp=NOW - timedelta(hours=5))
        logs.write_log(clean, "NODE_NOT_READY", "WARNING", "CLUSTER", "n1", "b", timestamp=NOW - timedelta(minutes=30))
        logs.write_log(clean, "BUDGET_ALERT", "WARNING", "CLOUD", "budget", "c", timestamp=NOW - timedelta(hours=1))
        logs.write_log(clean, "POD_EVENT", "WARNING", "CLUSTER", "p2", "old", timestamp=NOW - timedelta(days=5))
        clean.commit()

        page = logs.list_logs(clean, category="cluster", limit=2)
        assert page.total == 3 and [i.source for i in page.items] == ["n1", "p1"]

        h = logs.histogram(clean, "CLUSTER", hours=72, bucket_hours=2, now=NOW)
        assert len(h.buckets) == 36 and sum(b.count for b in h.buckets) == 2
        assert h.buckets[-1].count == 1 and h.buckets[-3].count == 1
        assert h.by_type == {"POD_EVENT": 1, "NODE_NOT_READY": 1}
        assert h.model_dump(by_alias=True)["bucketHours"] == 2
