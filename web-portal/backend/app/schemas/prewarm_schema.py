from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PrewarmNodeStatus(BaseModel):
    """สถานะการ pull image บน worker 1 เครื่อง"""
    node: str
    state: Literal["waiting", "pulling", "pulled", "error"] = Field(
        ..., description="waiting = ยังไม่มี pod / pulling / pulled = image อยู่บน node แล้ว / error"
    )
    reason: Optional[str] = Field(None, description="waiting reason ของ container เช่น ErrImagePull")
    pulled_in_seconds: Optional[float] = Field(
        None, description="เวลาตั้งแต่สร้าง pod จน container ขึ้น (รวมเวลา pull)"
    )
    node_ready: bool = Field(
        ..., description="node Ready อยู่ไหม (pod ของ node ที่หลุดยังรายงาน pulled ค่าเดิมค้างไว้)"
    )


class PrewarmResponse(BaseModel):
    """DaemonSet pre-pull 1 ตัว (1 image)"""
    name: str
    image: Optional[str]
    created_at: Optional[datetime]
    desired: int = Field(..., description="จำนวน worker ที่ต้องมี pod")
    ready: int = Field(..., description="จำนวน worker ที่ pull เสร็จแล้ว")
    all_pulled: bool = Field(
        ..., description="worker ที่ Ready ทุกเครื่อง pull แล้ว และไม่มีเครื่องที่เพิ่งหลุด (= slot READY)"
    )
    nodes: list[PrewarmNodeStatus]


class ScheduleSlot(BaseModel):
    """คาบที่ scheduler ยังต้องดูแล 1 คาบ"""
    id: str
    course_code: Optional[str]
    image: str
    starts_at: datetime
    ends_at: datetime
    prewarm_at: datetime = Field(..., description="starts_at - PREWARM_LEAD_MINUTES = เวลาที่จะเริ่ม pre-pull (+ warm pod)")
    status: str = Field(..., description="SCHEDULED / PREWARMING / READY")
    active: bool = Field(..., description="อยู่ในช่วง prewarm_at ถึง ends_at แล้ว (scheduler ดูแลอยู่ตอนนี้)")
    note: Optional[str]


class ScheduleTarget(BaseModel):
    """PREWARM_TARGETS จาก .env (pre-pull อย่างเดียว ไม่มี warm pod)"""
    image: str
    start_at: datetime
    end_at: datetime
    active: bool


class PrewarmScheduleResponse(BaseModel):
    """scheduler จะทำงานเมื่อไหร่ กับอะไร"""
    enabled: bool = Field(..., description="PREWARM_ENABLED และ interval > 0 (loop ใน backend รันอยู่)")
    interval_seconds: int
    lead_minutes: int
    warm_pod_enabled: bool
    now: datetime
    slots: list[ScheduleSlot]
    targets: list[ScheduleTarget]


class WarmPodResponse(BaseModel):
    """warm pod 1 ตัว (1 เครื่อง)"""
    pod: str
    node: Optional[str]
    lab_image_id: Optional[str]
    state: Optional[str] = Field(None, description="free = ว่าง / claimed = แจกให้ session แล้ว")
    session_id: Optional[str]
    phase: Optional[str]
    ready: bool
