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
