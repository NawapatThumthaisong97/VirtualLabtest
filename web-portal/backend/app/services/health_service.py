"""
Health Service — การ์ด System status หน้า admin (docs/ADMIN_MONITOR.md PR 2)

job ใน backend ตรวจ backend / k8s / registry / SkyPilot / AWS ทุก HEALTH_CHECK_INTERVAL_SECONDS
เก็บผลลงตาราง health_checks (ลบที่เก่ากว่า HEALTH_CHECK_RETENTION_DAYS ทุกรอบ) หน้า admin อ่านจากตารางนี้
แถบ 24 ชั่วโมงจึงเป็นประวัติจริง ไม่ได้สร้างตอนเปิดหน้า
"""
import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.configs.db import SessionLocal
from app.configs.settings import settings
from app.models.health_check import HealthCheck
from app.schemas.admin_monitor_schema import ServiceStatus, SystemStatusResponse
from app.services.admin_log_service import collect, log_health_changes
from app.services.prewarm_service import CONTROL_PLANE_LABEL
from app.utils.logger import logger

# ลำดับบนหน้า admin
SERVICE_NAMES = {
    "backend": "FastAPI Server",
    "k8s": "Kubernetes",
    "registry": "Docker registry",
    "skypilot": "SkyPilot API",
    "aws": "AWS Cloud",
}
STATUS_RANK = {"ok": 0, "degraded": 1, "down": 2}
HTTP_TIMEOUT = 5

# checker คืน (version, detail, degraded) หรือ raise = down
Checker = Callable[[], tuple[Optional[str], Optional[str], bool]]


@dataclass
class CheckResult:
    service: str
    status: str
    latency_ms: Optional[int]
    version: Optional[str]
    detail: Optional[str]


def run_check(service: str, checker: Checker) -> CheckResult:
    start = time.monotonic()
    try:
        version, detail, degraded = checker()
    except Exception as e:
        return CheckResult(service, "down", None, None, f"{type(e).__name__}: {e}"[:500])
    latency_ms = int((time.monotonic() - start) * 1000)
    if latency_ms > settings.HEALTH_CHECK_SLOW_MS:
        degraded = True
        detail = detail or f"slow: {latency_ms} ms"
    return CheckResult(service, "degraded" if degraded else "ok", latency_ms, version, detail)


def check_backend(db: DbSession) -> Checker:
    def _check():
        db.execute(text("SELECT 1"))
        return settings.APP_VERSION, None, False
    return _check


def check_k8s(k8s, version_api) -> Checker:
    """API ตอบ + node ทุกตัว Ready (worker หลุด = degraded บอกชื่อเครื่อง)"""
    def _check():
        version = version_api.get_code().git_version
        not_ready = []
        nodes = k8s.v1.list_node().items
        for node in nodes:
            ready = any(c.type == "Ready" and c.status == "True" for c in (node.status.conditions or []))
            if not ready:
                role = "control plane" if CONTROL_PLANE_LABEL in (node.metadata.labels or {}) else "worker"
                not_ready.append(f"{node.metadata.name} ({role})")
        if not_ready:
            return version, "NotReady: " + ", ".join(not_ready), True
        return version, f"{len(nodes)} nodes Ready", False
    return _check


def _get(url: str, headers: Optional[dict] = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def check_registry(host: str) -> Checker:
    """Docker registry API v2: 200 (ไม่มี auth) หรือ 401 (มี auth) = ทำงาน"""
    def _check():
        code, _ = _get(f"http://{host}/v2/")
        if code not in (200, 401):
            raise RuntimeError(f"HTTP {code}")
        return None, None, False
    return _check


def check_skypilot(endpoint: str, token: Optional[str]) -> Checker:
    """SkyPilot กลาง /api/health — แนบ token ไปด้วย ได้ user กลับมา = token ยังใช้ได้"""
    def _check():
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        code, body = _get(f"{endpoint.rstrip('/')}/api/health", headers)
        if code != 200:
            raise RuntimeError(f"HTTP {code}")
        data = json.loads(body)
        if data.get("status") != "healthy":
            return data.get("version"), f"status: {data.get('status')}", True
        if token and not data.get("user"):
            return data.get("version"), "service account token rejected", True
        return data.get("version"), None, False
    return _check


def check_aws() -> Checker:
    """STS GetCallerIdentity — credential ใช้ได้ + นาฬิกาตรง (คลาดเกิน 5 นาที AWS ปฏิเสธ signature)"""
    def _check():
        import boto3
        from botocore.config import Config
        cfg = Config(connect_timeout=HTTP_TIMEOUT, read_timeout=HTTP_TIMEOUT, retries={"max_attempts": 1})
        boto3.client("sts", region_name=settings.AWS_REGION, config=cfg).get_caller_identity()
        return None, None, False
    return _check


def default_checks(db: DbSession) -> list[tuple[str, Checker]]:
    """service ที่ตั้งค่าไว้ ตัวที่ไม่ได้ใช้ (เช่นไม่มี SkyPilot กลาง) ไม่ตรวจ ไม่ขึ้นบนหน้า admin"""
    checks: list[tuple[str, Checker]] = [("backend", check_backend(db))]
    if settings.K8S_ENABLED:
        def _k8s():
            from kubernetes import client
            from app.services.kubernetes_service import get_kubernetes_service
            k8s = get_kubernetes_service()  # โหลด kubeconfig ไม่ได้ = raise = down
            return check_k8s(k8s, client.VersionApi())()
        checks.append(("k8s", _k8s))
    if settings.DOCKER_REGISTRY_HOST:
        checks.append(("registry", check_registry(settings.DOCKER_REGISTRY_HOST)))
    if settings.SKYPILOT_API_SERVER_ENDPOINT:
        checks.append(("skypilot", check_skypilot(settings.SKYPILOT_API_SERVER_ENDPOINT,
                                                  settings.SKYPILOT_SERVICE_ACCOUNT_TOKEN)))
    checks.append(("aws", check_aws()))
    return checks


def _latest(db: DbSession) -> dict[str, HealthCheck]:
    """ผลล่าสุดของแต่ละ service (ไว้เทียบว่าสถานะเปลี่ยนไหม → เขียน log)"""
    latest: dict[str, HealthCheck] = {}
    since = datetime.now(timezone.utc) - timedelta(days=settings.HEALTH_CHECK_RETENTION_DAYS)
    for row in db.query(HealthCheck).filter(HealthCheck.checked_at > since).order_by(HealthCheck.checked_at):
        latest[row.service] = row
    return latest


def check_once(db: DbSession, checks: Optional[list[tuple[str, Checker]]] = None,
               now: Optional[datetime] = None) -> list[HealthCheck]:
    """ตรวจทุก service 1 รอบ บันทึกผล + ลบผลที่เก่ากว่า retention"""
    now = now or datetime.now(timezone.utc)
    previous = _latest(db)
    rows = []
    for service, checker in (checks if checks is not None else default_checks(db)):
        r = run_check(service, checker)
        rows.append(HealthCheck(service=r.service, status=r.status, latency_ms=r.latency_ms,
                                version=r.version, detail=r.detail, checked_at=now))
    db.add_all(rows)
    log_health_changes(db, previous, rows)
    cutoff = now - timedelta(days=settings.HEALTH_CHECK_RETENTION_DAYS)
    db.query(HealthCheck).filter(HealthCheck.checked_at < cutoff).delete(synchronize_session=False)
    db.commit()
    return rows


def _check_once_own_session() -> list[HealthCheck]:
    db = SessionLocal()
    try:
        rows = check_once(db)
        k8s = None
        if settings.K8S_ENABLED:
            try:
                from app.services.kubernetes_service import get_kubernetes_service
                k8s = get_kubernetes_service()
            except Exception:
                pass
        collect(db, k8s)   # k8s events + เกณฑ์ budget → log
        bad = [f"{r.service}={r.status}" for r in rows if r.status != "ok"]
        if bad:
            logger.warning(f"Health check: {', '.join(bad)}")
        return rows
    finally:
        db.close()


async def run_health_checker(interval_seconds: int, stop: asyncio.Event) -> None:
    """ตรวจทันทีตอนเปิด แล้วทุก interval_seconds จนกว่า stop จะถูก set (งาน blocking รันใน thread)"""
    logger.info(f"Health checker started (every {interval_seconds}s, keep "
                f"{settings.HEALTH_CHECK_RETENTION_DAYS} days)")
    while not stop.is_set():
        try:
            await asyncio.to_thread(_check_once_own_session)
        except Exception as e:
            logger.warning(f"Health checker failed: {e}")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
    logger.info("Health checker stopped")


def get_system_status(db: DbSession, now: Optional[datetime] = None) -> SystemStatusResponse:
    """ผลล่าสุดของแต่ละ service + แถบ 24 ช่อง (ช่องละชั่วโมง เก่า → ใหม่) = status แย่สุดในชั่วโมงนั้น"""
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    rows = (
        db.query(HealthCheck)
        .filter(HealthCheck.checked_at > start, HealthCheck.checked_at <= now)
        .order_by(HealthCheck.checked_at)
        .all()
    )
    by_service: dict[str, list[HealthCheck]] = {}
    for r in rows:
        by_service.setdefault(r.service, []).append(r)

    order = list(SERVICE_NAMES) + sorted(s for s in by_service if s not in SERVICE_NAMES)
    services = []
    for key in order:
        history = by_service.get(key)
        if not history:
            continue
        hourly: list[Optional[str]] = [None] * 24
        for r in history:
            i = min(int((r.checked_at - start) / timedelta(hours=1)), 23)
            if hourly[i] is None or STATUS_RANK[r.status] > STATUS_RANK[hourly[i]]:
                hourly[i] = r.status
        latest = history[-1]
        services.append(ServiceStatus(
            key=key, name=SERVICE_NAMES.get(key, key), version=latest.version, status=latest.status,
            latency_ms=latest.latency_ms, detail=latest.detail, checked_at=latest.checked_at,
            hourly=[h or "nodata" for h in hourly],
        ))
    checked_at = max((s.checked_at for s in services), default=None)
    return SystemStatusResponse(checked_at=checked_at, services=services)
