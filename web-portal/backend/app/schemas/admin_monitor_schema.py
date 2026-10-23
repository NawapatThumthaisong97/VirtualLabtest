"""
Admin Monitor Schemas
JSON ของการ์ดหน้า admin overview (docs/ADMIN_MONITOR.md) ส่งออกเป็น camelCase
"""
from datetime import datetime
from typing import Literal, Optional

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
