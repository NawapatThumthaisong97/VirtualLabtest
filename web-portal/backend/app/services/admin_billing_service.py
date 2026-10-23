"""
Admin Billing Service — การ์ด Billing หน้า admin (docs/ADMIN_MONITOR.md PR 3)

- record_usage: เขียน usage_records ตอน session จบ (ชั่วโมงที่รัน + ค่า AWS ประมาณ = ชั่วโมง × AWS_HOURLY_PRICE_USD)
- on-prem แสดงเป็นชั่วโมงอย่างเดียว ไม่คิดค่าไฟ (Pete 2026-10-23)
- session ที่ยังรันอยู่นับสด ๆ ถึงตอนนี้ ไม่ต้องรอจบ
- สวิตช์ burst (cloud_controls): ปิด = กด Start จากนอกห้องแลปได้ 409 ไม่สร้าง EC2
ยอดจริงจาก Cost Explorer มาใน PR 4 — ตอนนี้ source = "estimate"
"""
import calendar
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as DbSession

from app.configs.settings import settings
from app.models.cloud_control import CloudControl
from app.models.lab_image import LabImage
from app.models.session import Session as SessionModel, SessionStatus
from app.models.usage_record import UsageRecord
from app.schemas.admin_monitor_schema import (
    AwsBilling,
    BillingMonth,
    BillingMonthlyResponse,
    BillingShare,
    BillingSummaryResponse,
    CloudControlResponse,
    OnPremBilling,
)

# เดือนของ billing นับตามเวลาไทย
BILLING_TZ = ZoneInfo("Asia/Bangkok")


def _amount(requirement: Optional[str], default: float) -> float:
    """"2+" / "4" / "0.5" → ตัวเลข"""
    match = re.search(r"\d+(?:\.\d+)?", requirement or "")
    return float(match.group()) if match else default


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """sessions.started_at / ended_at บางที่เก็บเป็น naive UTC (datetime.utcnow)"""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def record_usage(db: DbSession, session: SessionModel) -> Optional[UsageRecord]:
    """บันทึกการใช้งานของ session ที่เพิ่งจบ (ไม่ commit — คนเรียก commit พร้อมสถานะ session)

    เรียกซ้ำได้: session ที่มี record แล้วข้าม — EC2 ที่ launch พังกลางทางก็นับ เพราะเสียเงินไปแล้ว
    """
    if db.query(UsageRecord.id).filter(UsageRecord.session_id == session.id).first() is not None:
        return None
    started, ended = _utc(session.started_at), _utc(session.ended_at)
    seconds = max(int((ended - started).total_seconds()), 0) if started and ended else 0
    image = db.get(LabImage, session.lab_image_id) if session.lab_image_id else None
    cpus = _amount(image.cpu_requirement if image else None, 2)
    memory_gb = _amount(image.memory_requirement if image else None, 4)
    hours = seconds / 3600
    record = UsageRecord(
        session_id=session.id,
        cpu_seconds=int(seconds * cpus),
        gpu_seconds=0,
        ram_mb_hours=round(hours * memory_gb * 1024, 2),
        is_cloud_burst=bool(session.is_cloud),
        est_cost_thb=0,
        duration_seconds=seconds,
        est_cost_usd=round(hours * settings.AWS_HOURLY_PRICE_USD, 4) if session.is_cloud else 0,
    )
    db.add(record)
    return record


# ---------- burst switch ----------

def get_cloud_control(db: DbSession) -> CloudControlResponse:
    row = db.get(CloudControl, 1)
    if row is None:
        return CloudControlResponse(burst_enabled=True)
    return CloudControlResponse(burst_enabled=row.burst_enabled, reason=row.reason,
                                changed_by=row.changed_by, changed_at=row.changed_at)


def is_burst_enabled(db: DbSession) -> bool:
    row = db.get(CloudControl, 1)
    return row is None or row.burst_enabled


def set_burst(db: DbSession, enabled: bool, reason: Optional[str], user_id: Optional[UUID]) -> CloudControlResponse:
    row = db.get(CloudControl, 1)
    if row is None:
        row = CloudControl(id=1)
        db.add(row)
    row.burst_enabled = enabled
    row.reason = reason
    row.changed_by = user_id
    row.changed_at = datetime.now(timezone.utc)
    db.commit()
    return get_cloud_control(db)


# ---------- summary ----------

def _month_range(month: date) -> tuple[datetime, datetime]:
    """[ต้นเดือน, ต้นเดือนถัดไป) เวลาไทย → UTC"""
    start = datetime(month.year, month.month, 1, tzinfo=BILLING_TZ)
    days = calendar.monthrange(month.year, month.month)[1]
    return start.astimezone(timezone.utc), (start + timedelta(days=days)).astimezone(timezone.utc)


def _usage(db: DbSession, start: datetime, end: datetime, now: datetime) -> dict:
    """ชั่วโมง on-prem / AWS + $ AWS ในช่วง [start, end): session ที่จบแล้ว (usage_records) + ที่ยังรันอยู่ (นับถึง now)"""
    totals = {"on_prem_hours": 0.0, "aws_hours": 0.0, "aws_usd": 0.0}
    records = (
        db.query(UsageRecord)
        .filter(UsageRecord.recorded_at >= start, UsageRecord.recorded_at < end)
        .all()
    )
    for r in records:
        hours = (r.duration_seconds or 0) / 3600
        if r.is_cloud_burst:
            totals["aws_hours"] += hours
            totals["aws_usd"] += float(r.est_cost_usd or 0)
        else:
            totals["on_prem_hours"] += hours

    if start <= now < end:
        running = (
            db.query(SessionModel)
            .filter(SessionModel.status.in_([SessionStatus.RUNNING, SessionStatus.PENDING]),
                    SessionModel.deleted_at.is_(None))
            .all()
        )
        for s in running:
            started = _utc(s.started_at)
            if started is None:
                continue
            hours = max((now - max(started, start)).total_seconds(), 0) / 3600
            if s.is_cloud:
                totals["aws_hours"] += hours
                totals["aws_usd"] += hours * settings.AWS_HOURLY_PRICE_USD
            else:
                totals["on_prem_hours"] += hours
    return totals


def get_billing_summary(db: DbSession, month: Optional[date] = None,
                        now: Optional[datetime] = None) -> BillingSummaryResponse:
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(BILLING_TZ)
    month = month or local_now.date().replace(day=1)
    start, end = _month_range(month)
    totals = _usage(db, start, end, now)

    days_total = calendar.monthrange(month.year, month.month)[1]
    current = start <= now < end
    if current:
        elapsed_days = max((now - start).total_seconds() / 86400, 1 / 24)
        days_remaining = days_total - local_now.day
        forecast = totals["aws_usd"] / elapsed_days * days_total
    else:
        days_remaining = 0 if now >= end else days_total
        forecast = totals["aws_usd"]

    budget = settings.AWS_MONTHLY_BUDGET_USD
    used_pct = totals["aws_usd"] / budget * 100 if budget > 0 else 0
    if used_pct >= 100:
        alert = "over"
    elif used_pct >= settings.AWS_BUDGET_ALERT_PCT:
        alert = "warn"
    else:
        alert = "none"

    all_hours = totals["on_prem_hours"] + totals["aws_hours"]
    instances = (
        db.query(SessionModel)
        .filter(SessionModel.is_cloud.is_(True),
                SessionModel.status.in_([SessionStatus.RUNNING, SessionStatus.PENDING]),
                SessionModel.deleted_at.is_(None))
        .count()
    )
    return BillingSummaryResponse(
        month=f"{month.year:04d}-{month.month:02d}",
        aws=AwsBilling(
            budget_usd=budget,
            used_usd=round(totals["aws_usd"], 2),
            forecast_usd=round(forecast, 2),
            used_pct=round(used_pct, 1),
            alert=alert,
            source="estimate",
            hourly_price_usd=settings.AWS_HOURLY_PRICE_USD,
            instances_running=instances if current else 0,
            session_hours=round(totals["aws_hours"], 2),
        ),
        on_prem=OnPremBilling(session_hours=round(totals["on_prem_hours"], 2)),
        share=BillingShare(
            on_prem_pct=round(totals["on_prem_hours"] / all_hours * 100, 1) if all_hours else 0,
            aws_pct=round(totals["aws_hours"] / all_hours * 100, 1) if all_hours else 0,
        ),
        days_remaining=days_remaining,
        days_total=days_total,
        burst_enabled=is_burst_enabled(db),
    )


def get_billing_monthly(db: DbSession, months: int = 6, now: Optional[datetime] = None) -> BillingMonthlyResponse:
    """ย้อนหลัง months เดือนถึงเดือนนี้ เก่า → ใหม่ เดือนที่ไม่มีการใช้งานได้ 0"""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(BILLING_TZ).date().replace(day=1)
    result = []
    for back in range(months - 1, -1, -1):
        year, month = divmod(local.year * 12 + local.month - 1 - back, 12)
        first = date(year, month + 1, 1)
        totals = _usage(db, *_month_range(first), now)
        result.append(BillingMonth(
            month=f"{first.year:04d}-{first.month:02d}",
            on_prem_hours=round(totals["on_prem_hours"], 2),
            aws_hours=round(totals["aws_hours"], 2),
            aws_usd=round(totals["aws_usd"], 2),
        ))
    return BillingMonthlyResponse(months=result)
