from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import CamelModel
from app.models.session import ServiceType, SessionStatus, SessionEndReason


class CreateSessionRequest(CamelModel):
    """Request schema สำหรับสร้าง session ใหม่"""
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "labId": "550e8400-e29b-41d4-a716-446655440000",
            }
        },
    )

    lab_id: UUID = Field(..., description="Lab ID ที่ต้องการสร้าง session")


class CreateSessionResponse(BaseModel):
    """Response schema หลังสร้าง session สำเร็จ"""
    session_id: UUID = Field(..., description="Session ID ที่สร้างขึ้น")
    cluster_name: Optional[str] = Field(None, description="ชื่อ cluster ของ SkyPilot (null = ได้ warm pod)")
    launch_mode: str = Field("skypilot", description="skypilot = launch ใหม่ / warm_pod = ใช้ pod ที่รอไว้บนเครื่องนี้")
    run_target: Optional[str] = Field(None, description="ที่ที่ launch จริง kubernetes / aws (lab AUTO เลือกตามเครื่องที่กด)")
    node_name: Optional[str] = Field(None, description="เครื่องที่ pod รันอยู่ (warm_pod)")
    lab_id: UUID = Field(..., description="Lab ID")
    lab_title: str = Field(..., description="Lab title")
    image_repository: str = Field(..., description="Docker image repository")
    image_tag: str = Field(..., description="Docker image tag")
    endpoints: dict[str, str] = Field(..., description="Service endpoints")
    status: str = Field(..., description="Session status")
    started_at: datetime = Field(..., description="เวลาเริ่ม session")
    expires_at: Optional[datetime] = Field(None, description="เวลาที่ lab จะถูกปิดอัตโนมัติ (lifespan_minutes)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "770e8400-e29b-41d4-a716-446655440002",
                "cluster_name": "music-lab-1735650000",
                "lab_id": "550e8400-e29b-41d4-a716-446655440000",
                "lab_title": "Lab 1: Setup Environment",
                "image_repository": "skypilot/music-lab",
                "image_tag": "lab-01",
                "endpoints": {
                    "8080": "http://100.125.244.48:32080",
                    "5173": "http://100.125.244.48:31472",
                    "8443": "http://100.125.244.48:32462"
                },
                "status": "running",
                "started_at": "2024-01-15T10:30:00Z"
            }
        }


class SessionResponse(BaseModel):
    """Response schema สำหรับข้อมูล session"""
    id: UUID
    user_id: UUID
    lab_id: Optional[UUID]
    lab_image_id: Optional[UUID]  # ✅ เปลี่ยนจาก image_ref
    service_type: ServiceType
    k8s_pod_name: Optional[str]
    node_name: Optional[str]
    is_remote: bool
    is_cloud: bool
    sky_cluster_name: Optional[str]
    sky_job_id: Optional[int]
    endpoints: Optional[dict]
    status: SessionStatus
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    expires_at: Optional[datetime]
    end_reason: Optional[SessionEndReason] = None

    class Config:
        from_attributes = True
        use_enum_values = True


class SessionDetailResponse(SessionResponse):
    """Response schema สำหรับข้อมูล session แบบละเอียด (อาจมี relationship อื่นๆ)"""
    pass
