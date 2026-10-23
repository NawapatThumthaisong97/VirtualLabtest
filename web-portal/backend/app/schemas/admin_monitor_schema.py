"""
Admin Monitor Schemas
JSON ของการ์ดหน้า admin overview (docs/ADMIN_MONITOR.md) ส่งออกเป็น camelCase
"""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelModel

RoomStatus = Literal["ok", "warn", "down"]


class RoomMapItem(CamelModel):
    """ห้องแลป 1 ห้อง = worker ที่มี label vlab/room เดียวกัน (คอม 1 เครื่อง = 1 worker)"""
    room: str = Field(..., description="ชื่อห้องจาก label vlab/room หรือ unassigned")
    status: RoomStatus = Field(..., description="down = ไม่มีเครื่อง Ready, warn = Ready ไม่ครบ, ok = ครบ")
    pcs_total: int
    pcs_ready: int
    pcs_in_use: int = Field(..., description="เครื่องที่มี session RUNNING อย่างน้อย 1 ตัว")
    nodes: list[str]


class ControlPlane(CamelModel):
    node: Optional[str]
    ready: bool


class ClusterMapItem(CamelModel):
    id: str
    type: Literal["k3s", "cloud"]
    status: Literal["ok", "warn", "down", "unknown"] = Field(
        ..., description="unknown = ยังไม่มี health check (AWS จนกว่าจะมี /admin/system/status)"
    )
    control_plane: Optional[ControlPlane] = None
    rooms: Optional[list[RoomMapItem]] = None
    region: Optional[str] = None
    instances_running: Optional[int] = Field(None, description="session บน AWS ที่ RUNNING / PENDING")


class InfraMapResponse(CamelModel):
    clusters: list[ClusterMapItem]


class RoomSlot(CamelModel):
    """คาบที่กำลังใช้ห้องนี้ (จาก sessions.class_slot_id ของคนที่นั่งอยู่)"""
    course: str
    starts_at: datetime
    ends_at: datetime
    status: str


class RoomUsageItem(CamelModel):
    room: str
    pcs_in_use: int
    pcs_total: int
    state: Literal["launched", "idle"] = Field(
        ..., description="launched = มีคนใช้อยู่, idle = ว่าง (queue จะมีเมื่อ slot ผูกห้องได้ — PR จองห้อง)"
    )
    slot: Optional[RoomSlot] = None


class RoomUsageResponse(CamelModel):
    rooms: list[RoomUsageItem]


ServiceHealth = Literal["ok", "degraded", "down"]


class ServiceStatus(CamelModel):
    """service 1 ตัวในการ์ด System status: ผลล่าสุด + แถบ 24 ชั่วโมง"""
    key: str
    name: str
    version: Optional[str] = None
    status: ServiceHealth
    latency_ms: Optional[int] = None
    detail: Optional[str] = Field(None, description="สาเหตุตอน degraded / down เช่น NotReady: worker-pete (worker)")
    checked_at: datetime
    hourly: list[Literal["ok", "degraded", "down", "nodata"]] = Field(
        ..., description="24 ช่อง เก่า → ใหม่ ช่องละ 1 ชม. = status แย่สุดในชั่วโมงนั้น, nodata = ไม่ได้ตรวจ"
    )


class SystemStatusResponse(CamelModel):
    checked_at: Optional[datetime] = Field(None, description="ตรวจล่าสุดเมื่อไหร่ (None = ยังไม่เคยตรวจ)")
    services: list[ServiceStatus]


# ---------- Billing (PR 3) ----------

class AwsBilling(CamelModel):
    budget_usd: float
    used_usd: float = Field(..., description="ใช้ไปเดือนนี้ (session ที่จบแล้ว + ที่ยังรันอยู่ นับถึงตอนนี้)")
    forecast_usd: float = Field(..., description="คาดทั้งเดือน = used / วันที่ผ่านไป × วันทั้งเดือน")
    used_pct: float
    alert: Literal["none", "warn", "over"] = Field(..., description="warn = ถึง AWS_BUDGET_ALERT_PCT, over = เกิน budget")
    source: Literal["estimate", "cost-explorer"] = Field(..., description="estimate = ชั่วโมง × hourlyPriceUsd")
    hourly_price_usd: float
    instances_running: int
    session_hours: float


class OnPremBilling(CamelModel):
    session_hours: float = Field(..., description="ชั่วโมงอย่างเดียว ไม่คิดค่าไฟ")


class BillingShare(CamelModel):
    """สัดส่วนจากชั่วโมง (ไม่ใช่เงิน)"""
    on_prem_pct: float
    aws_pct: float


class BillingSummaryResponse(CamelModel):
    month: str
    aws: AwsBilling
    on_prem: OnPremBilling
    share: BillingShare
    days_remaining: int
    days_total: int
    burst_enabled: bool


class BillingMonth(CamelModel):
    month: str
    on_prem_hours: float
    aws_hours: float
    aws_usd: float


class BillingMonthlyResponse(CamelModel):
    months: list[BillingMonth]


class CloudControlResponse(CamelModel):
    burst_enabled: bool
    reason: Optional[str] = None
    changed_by: Optional[UUID] = None
    changed_at: Optional[datetime] = None


class CloudControlUpdate(CamelModel):
    burst_enabled: bool
    reason: Optional[str] = Field(None, max_length=500)


# ---------- Logs (PR 5) ----------

class LogItem(CamelModel):
    id: UUID
    timestamp: datetime
    severity: str
    category: str = Field(..., description="CLUSTER / CLOUD")
    event_type: str = Field(..., description="SESSION_FAILED, CLOUD_LAUNCH_FAILED, NODE_NOT_READY, NODE_READY, "
                                             "HEALTH_DOWN, HEALTH_RECOVERED, POD_EVENT, BUDGET_ALERT, BURST_TOGGLED")
    source: str
    message: str
    anon_id: Optional[str] = None
    room: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class LogListResponse(CamelModel):
    total: int
    items: list[LogItem]


class LogHistogramBucket(CamelModel):
    t: datetime
    count: int


class LogHistogramResponse(CamelModel):
    start: datetime
    end: datetime
    bucket_hours: int
    buckets: list[LogHistogramBucket]
    by_type: dict[str, int]
