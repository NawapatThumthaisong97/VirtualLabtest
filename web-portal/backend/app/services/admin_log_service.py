"""
Admin Log Service — การ์ด Log Explorer หน้า admin (docs/ADMIN_MONITOR.md PR 5)

เขียน log จากเหตุการณ์จริงลงตาราง infrastructure_logs (ของ #98) ผ่าน LogMaskerService (user → anon_id, ตัด PII)
- category = CLUSTER / CLOUD (ปุ่มสลับใน Log Explorer), event_type = ประเภท, source = เครื่อง / service / pod
- id คงที่ (uuid5) สำหรับเหตุการณ์ที่อาจเห็นซ้ำ (k8s event, เตือน budget) → เขียนครั้งเดียว
"""
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session as DbSession

from app.configs.settings import settings
from app.models.health_check import HealthCheck
from app.models.infrastructure_log import InfrastructureLog
from app.models.session import Session as SessionModel, SessionEndReason
from app.schemas.admin_monitor_schema import LogHistogramBucket, LogHistogramResponse, LogItem, LogListResponse
from app.services.log_masker_service import LogMaskerService
from app.utils.logger import logger

CLUSTER, CLOUD = "CLUSTER", "CLOUD"
ID_NAMESPACE = uuid.UUID("6f1c2a52-7d0e-4c1e-9a55-1b0d3c2f4e8a")

# k8s Events ที่นับว่าเป็นปัญหาของ pod (type Warning)
POD_EVENT_REASONS = {"Failed", "BackOff", "Evicted", "FailedScheduling", "OOMKilling", "FailedMount"}
FAILED_END_REASONS = {
    SessionEndReason.LAUNCH_FAILED: "ERROR",
    SessionEndReason.STALE_PENDING: "ERROR",
    SessionEndReason.LOST: "WARNING",
}


def write_log(db: DbSession, event_type: str, severity: str, category: str, source: str, message: str,
              user_id: Any = None, room: Optional[str] = None, metadata: Optional[dict] = None,
              log_id: Optional[uuid.UUID] = None, timestamp: Optional[datetime] = None) -> Optional[InfrastructureLog]:
    """เพิ่ม log (ไม่ commit) — log_id ซ้ำกับที่มีอยู่ = ข้าม"""
    if log_id is not None and db.get(InfrastructureLog, log_id) is not None:
        return None
    masker = LogMaskerService()
    row = InfrastructureLog(
        id=log_id or uuid.uuid4(),
        timestamp=timestamp or datetime.now(timezone.utc),
        severity=severity,
        category=category,
        event_type=event_type,
        source=source[:255],
        message=masker.mask_text(message),
        anon_id=masker.pseudonymize_user_id(user_id) if user_id else None,
        cluster_or_subnet=room,
        metadata_json=metadata or {},
    )
    db.add(row)
    return row


def log_session_end(db: DbSession, session: SessionModel, reason: Optional[SessionEndReason]) -> None:
    """session จบแบบมีปัญหา (launch พัง / ค้าง PENDING / หาย) → SESSION_FAILED หรือ CLOUD_LAUNCH_FAILED"""
    if reason not in FAILED_END_REASONS:
        return
    cloud = bool(session.is_cloud)
    event_type = "CLOUD_LAUNCH_FAILED" if cloud and reason == SessionEndReason.LAUNCH_FAILED else "SESSION_FAILED"
    write_log(
        db, event_type, FAILED_END_REASONS[reason], CLOUD if cloud else CLUSTER,
        source=session.node_name or session.sky_cluster_name or session.k8s_pod_name or "unknown",
        message=f"Session {str(session.id)[:8]} ended: {reason.value}",
        user_id=session.user_id,
        metadata={"sessionId": str(session.id), "reason": reason.value,
                  "labId": str(session.lab_id) if session.lab_id else None},
        log_id=uuid.uuid5(ID_NAMESPACE, f"session-end-{session.id}"),
    )


def _not_ready_nodes(detail: Optional[str]) -> set[str]:
    """detail ของ k8s check: "NotReady: worker-pete (worker), master (control plane)" → {"worker-pete", "master"}"""
    if not detail or not detail.startswith("NotReady: "):
        return set()
    return {part.split(" (")[0].strip() for part in detail[len("NotReady: "):].split(", ") if part}


def _service_status(row: Optional[HealthCheck]) -> str:
    """สถานะของ service ไว้เทียบว่าเปลี่ยนไหม — k8s ที่ degraded เพราะเครื่องหลุดนับเป็น ok (ใช้ NODE_* แทน)"""
    if row is None:
        return "ok"
    if row.service == "k8s" and row.status == "degraded" and _not_ready_nodes(row.detail):
        return "ok"
    return row.status


def log_health_changes(db: DbSession, previous: dict[str, HealthCheck], current: list[HealthCheck]) -> None:
    """เขียนเฉพาะตอนสถานะเปลี่ยน ไม่ใช่ทุกรอบ — เครื่องหลุด / กลับ = NODE_NOT_READY / NODE_READY,
    service down / degraded / กลับ ok = HEALTH_DOWN / HEALTH_RECOVERED"""
    for row in current:
        before = previous.get(row.service)
        category = CLOUD if row.service == "aws" else CLUSTER
        if row.service == "k8s":
            was, now = _not_ready_nodes(before.detail if before else None), _not_ready_nodes(row.detail)
            for node in sorted(now - was):
                write_log(db, "NODE_NOT_READY", "WARNING", CLUSTER, node, f"Node {node} NotReady",
                          timestamp=row.checked_at)
            for node in sorted(was - now):
                write_log(db, "NODE_READY", "INFO", CLUSTER, node, f"Node {node} Ready again",
                          timestamp=row.checked_at)
        was_status, now_status = _service_status(before), _service_status(row)
        if now_status == was_status:
            continue
        if now_status in ("down", "degraded"):
            write_log(db, "HEALTH_DOWN", "ERROR" if now_status == "down" else "WARNING", category, row.service,
                      f"{row.service} {now_status}: {row.detail or ''}".strip(), timestamp=row.checked_at)
        else:
            write_log(db, "HEALTH_RECOVERED", "INFO", category, row.service, f"{row.service} ok again",
                      timestamp=row.checked_at)


def collect_pod_events(db: DbSession, k8s) -> int:
    """k8s Events (Warning) ของ pod ใน namespace lab → POD_EVENT ตัวละครั้ง (id จาก uid ของ event)"""
    events = k8s.v1.list_namespaced_event(settings.K8S_DEFAULT_NAMESPACE).items
    added = 0
    for ev in events:
        obj = ev.involved_object
        if ev.type != "Warning" or ev.reason not in POD_EVENT_REASONS or (obj and obj.kind != "Pod"):
            continue
        when = ev.last_timestamp or ev.event_time or ev.metadata.creation_timestamp
        host = getattr(ev.source, "host", None) if ev.source else None
        row = write_log(
            db, "POD_EVENT", "ERROR" if ev.reason in ("Failed", "Evicted", "OOMKilling") else "WARNING", CLUSTER,
            source=obj.name if obj else "pod",
            message=f"{ev.reason}: {ev.message or ''}"[:2000],
            metadata={"reason": ev.reason, "node": host, "count": ev.count},
            log_id=uuid.uuid5(ID_NAMESPACE, f"k8s-event-{ev.metadata.uid}"),
            timestamp=when,
        )
        added += row is not None
    return added


def log_budget_alert(db: DbSession, month: str, alert: str, used_usd: float, budget_usd: float) -> None:
    """ใช้ AWS ถึงเกณฑ์ → BUDGET_ALERT ครั้งเดียวต่อเกณฑ์ต่อเดือน"""
    if alert not in ("warn", "over"):
        return
    write_log(
        db, "BUDGET_ALERT", "CRITICAL" if alert == "over" else "WARNING", CLOUD, "budget",
        f"AWS {month}: ${used_usd:.2f} of ${budget_usd:.0f} budget ({alert})",
        metadata={"month": month, "level": alert, "usedUsd": used_usd},
        log_id=uuid.uuid5(ID_NAMESPACE, f"budget-{month}-{alert}"),
    )


def log_burst_toggled(db: DbSession, enabled: bool, reason: Optional[str], user_id: Any) -> None:
    write_log(db, "BURST_TOGGLED", "WARNING" if not enabled else "INFO", CLOUD, "admin",
              f"AWS burst {'enabled' if enabled else 'disabled'}" + (f": {reason}" if reason else ""),
              user_id=user_id, metadata={"enabled": enabled})


def collect(db: DbSession, k8s) -> None:
    """เรียกทุกรอบของ health checker: k8s events + เกณฑ์ budget"""
    if k8s is not None:
        try:
            collect_pod_events(db, k8s)
        except Exception as e:
            logger.warning(f"[logs] cannot read k8s events: {e}")
    from app.services.admin_billing_service import fetch_cost_explorer, get_billing_summary
    try:
        fetch_cost_explorer(db)   # วันละครั้ง ข้ามเองถ้าดึงไปแล้ว
    except Exception as e:
        db.rollback()
        logger.warning(f"[billing] Cost Explorer failed: {e}")
    summary = get_billing_summary(db)
    log_budget_alert(db, summary.month, summary.aws.alert, summary.aws.used_usd, summary.aws.budget_usd)
    db.commit()


# ---------- read ----------

def _query(db: DbSession, category: Optional[str], event_type: Optional[str], severity: Optional[str],
           start: Optional[datetime], end: Optional[datetime]):
    q = db.query(InfrastructureLog)
    if category:
        q = q.filter(InfrastructureLog.category == category.upper())
    if event_type:
        q = q.filter(InfrastructureLog.event_type == event_type.upper())
    if severity:
        q = q.filter(InfrastructureLog.severity == severity.upper())
    if start:
        q = q.filter(InfrastructureLog.timestamp >= start)
    if end:
        q = q.filter(InfrastructureLog.timestamp < end)
    return q


def list_logs(db: DbSession, category: Optional[str] = None, event_type: Optional[str] = None,
              severity: Optional[str] = None, start: Optional[datetime] = None, end: Optional[datetime] = None,
              limit: int = 50, offset: int = 0) -> LogListResponse:
    q = _query(db, category, event_type, severity, start, end)
    total = q.count()
    rows = q.order_by(InfrastructureLog.timestamp.desc()).offset(offset).limit(limit).all()
    return LogListResponse(total=total, items=[
        LogItem(id=r.id, timestamp=r.timestamp, severity=r.severity, category=r.category, event_type=r.event_type,
                source=r.source, message=r.message, anon_id=r.anon_id, room=r.cluster_or_subnet,
                metadata=r.metadata_json or {})
        for r in rows
    ])


def histogram(db: DbSession, category: Optional[str] = None, hours: int = 72, bucket_hours: int = 2,
              now: Optional[datetime] = None, severity: Optional[str] = None,
              event_type: Optional[str] = None) -> LogHistogramResponse:
    """จำนวน log ต่อช่วงเวลา เก่า → ใหม่ (ช่วงละ bucket_hours) + แยกตามประเภท"""
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    rows = _query(db, category, event_type, severity, start, now).with_entities(
        InfrastructureLog.timestamp, InfrastructureLog.event_type).all()
    size = timedelta(hours=bucket_hours)
    counts = [0] * (hours // bucket_hours)
    for ts, _ in rows:
        counts[min(int((ts - start) / size), len(counts) - 1)] += 1
    return LogHistogramResponse(
        start=start, end=now, bucket_hours=bucket_hours,
        buckets=[LogHistogramBucket(t=start + i * size, count=c) for i, c in enumerate(counts)],
        by_type=dict(Counter(t for _, t in rows)),
    )
