"""
กลุ่ม 10: การ์ด System status หน้า admin — ตรวจ service, เก็บประวัติ, แถบ 24 ชั่วโมง (docs/ADMIN_MONITOR.md PR 2)
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as _ns

import pytest

from app.configs.settings import settings
from app.models.health_check import HealthCheck
from app.services import health_service
from app.services.health_service import check_k8s, check_once, get_system_status, run_check
from tests.fakes import FakeK8s

NOW = datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)
VERSION_API = _ns(get_code=lambda: _ns(git_version="v1.35.5+k3s1"))


def ok(version=None, detail=None):
    return lambda: (version, detail, False)


def boom(msg):
    def _check():
        raise RuntimeError(msg)
    return _check


@pytest.fixture
def clean(db):
    db.query(HealthCheck).delete()
    db.commit()
    return db


class TestRunCheck:
    """run_check: ok / degraded / down from one checker"""

    def test_ok(self):
        """Checker returns -> ok with latency and version"""
        r = run_check("backend", ok("1.0.0"))
        assert (r.status, r.version, r.detail) == ("ok", "1.0.0", None)
        assert r.latency_ms is not None

    def test_down(self):
        """Checker raises -> down, error kept as detail, no latency"""
        r = run_check("registry", boom("connection refused"))
        assert (r.status, r.latency_ms) == ("down", None)
        assert "connection refused" in r.detail

    def test_slow(self, monkeypatch):
        """Slower than HEALTH_CHECK_SLOW_MS -> degraded"""
        monkeypatch.setattr(settings, "HEALTH_CHECK_SLOW_MS", -1)
        r = run_check("aws", ok())
        assert r.status == "degraded" and r.detail.startswith("slow:")


class TestK8sCheck:
    """k8s: API version + every node Ready"""

    def test_all_ready(self):
        """All nodes Ready -> ok, version from API"""
        k8s = FakeK8s()
        k8s.add_node("master", control_plane=True)
        k8s.add_node("worker-pete")
        assert check_k8s(k8s, VERSION_API)() == ("v1.35.5+k3s1", "2 nodes Ready", False)

    def test_worker_not_ready(self):
        """Worker NotReady -> degraded, names the machine"""
        k8s = FakeK8s()
        k8s.add_node("master", control_plane=True)
        k8s.add_node("worker-pete", ready=False)
        r = run_check("k8s", check_k8s(k8s, VERSION_API))
        assert r.status == "degraded" and r.detail == "NotReady: worker-pete (worker)"

    def test_api_down(self):
        """K3s API unreachable -> down"""
        k8s = FakeK8s()
        k8s.error = RuntimeError("connection refused")
        assert run_check("k8s", check_k8s(k8s, VERSION_API)).status == "down"


class TestHistory:
    """check_once stores results; old rows deleted (table does not grow)"""

    def test_store_and_retention(self, clean, monkeypatch):
        """Each round adds one row per service; rows older than retention removed"""
        monkeypatch.setattr(settings, "HEALTH_CHECK_RETENTION_DAYS", 7)
        clean.add(HealthCheck(service="backend", status="ok", checked_at=NOW - timedelta(days=8)))
        clean.add(HealthCheck(service="backend", status="ok", checked_at=NOW - timedelta(days=6)))
        clean.commit()

        check_once(clean, [("backend", ok()), ("aws", boom("expired"))], now=NOW)

        rows = clean.query(HealthCheck).order_by(HealthCheck.checked_at).all()
        assert [(r.service, r.status, r.checked_at) for r in rows] == [
            ("backend", "ok", NOW - timedelta(days=6)),
            ("backend", "ok", NOW),
            ("aws", "down", NOW),
        ]

    def test_infrastructure_log_retention(self, clean, monkeypatch):
        """Old infrastructure_logs older than INFRASTRUCTURE_LOG_RETENTION_DAYS are purged by check_once"""
        from app.models.infrastructure_log import InfrastructureLog
        import uuid

        monkeypatch.setattr(settings, "INFRASTRUCTURE_LOG_RETENTION_DAYS", 30)
        old_log = InfrastructureLog(
            id=uuid.uuid4(),
            timestamp=NOW - timedelta(days=31),
            severity="INFO",
            category="SYSTEM_LOG",
            event_type="SYSTEM_METRIC",
            source="worker-old",
            message="Old routine log",
        )
        recent_log = InfrastructureLog(
            id=uuid.uuid4(),
            timestamp=NOW - timedelta(days=15),
            severity="WARNING",
            category="SECURITY_VIOLATION",
            event_type="FALCO_EBPF_ALERT",
            source="worker-new",
            message="Recent alert",
        )
        clean.add_all([old_log, recent_log])
        clean.commit()

        check_once(clean, [("backend", ok())], now=NOW)

        remaining = clean.query(InfrastructureLog).all()
        assert len(remaining) == 1
        assert remaining[0].id == recent_log.id

    def test_default_checks_skip_unconfigured(self, db, monkeypatch):
        """Services not configured (no registry / SkyPilot / K8S_ENABLED off) are not checked"""
        monkeypatch.setattr(settings, "K8S_ENABLED", False)
        monkeypatch.setattr(settings, "DOCKER_REGISTRY_HOST", None)
        monkeypatch.setattr(settings, "SKYPILOT_API_SERVER_ENDPOINT", None)
        assert [name for name, _ in health_service.default_checks(db)] == ["backend", "aws"]


class TestSystemStatus:
    """GET /admin/system/status: latest result + 24 hourly slots"""

    def add(self, db, service, status, ago, **kw):
        db.add(HealthCheck(service=service, status=status, checked_at=NOW - ago, **kw))

    def test_hourly(self, clean):
        """Worst status per hour, oldest -> newest, nodata where nothing checked; order backend, k8s, ..."""
        self.add(clean, "k8s", "ok", timedelta(minutes=10), version="v1.35.5+k3s1", latency_ms=12)
        self.add(clean, "k8s", "degraded", timedelta(minutes=40), detail="NotReady: worker-pete (worker)")
        self.add(clean, "k8s", "ok", timedelta(minutes=50))
        self.add(clean, "k8s", "down", timedelta(hours=5, minutes=30))
        self.add(clean, "k8s", "ok", timedelta(hours=30))           # เกิน 24 ชม. ไม่นับ
        self.add(clean, "backend", "ok", timedelta(minutes=5), version="1.0.0", latency_ms=3)
        clean.commit()

        status = get_system_status(clean, now=NOW)

        assert [s.key for s in status.services] == ["backend", "k8s"]
        k8s = status.services[1]
        assert (k8s.name, k8s.status, k8s.version, k8s.latency_ms) == ("Kubernetes", "ok", "v1.35.5+k3s1", 12)
        assert len(k8s.hourly) == 24
        assert k8s.hourly[23] == "degraded"
        assert k8s.hourly[18] == "down"
        assert k8s.hourly.count("nodata") == 22
        assert status.checked_at == NOW - timedelta(minutes=5)

    def test_empty(self, clean):
        """Never checked -> no services, checkedAt null"""
        status = get_system_status(clean, now=NOW)
        assert (status.services, status.checked_at) == ([], None)

    def test_camel_case(self, clean):
        """JSON keys camelCase"""
        self.add(clean, "aws", "down", timedelta(minutes=1), detail="SignatureDoesNotMatch")
        clean.commit()
        data = get_system_status(clean, now=NOW).model_dump(by_alias=True)
        assert {"checkedAt", "services"} == set(data)
        assert {"latencyMs", "checkedAt", "hourly", "detail"} <= set(data["services"][0])
