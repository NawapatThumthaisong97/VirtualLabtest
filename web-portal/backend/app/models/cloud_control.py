from sqlalchemy import Column, Integer, Boolean, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from app.configs.db import Base


class CloudControl(Base):
    """สวิตช์เปิด/ปิด burst ขึ้น AWS มีแถวเดียว (id = 1) — admin ปิดเมื่อใช้เกิน budget (PATCH /admin/cloud/controls)

    ปิด = กด Start จากนอกห้องแลปได้ 409 ไม่สร้าง EC2 (เครื่องแลปยังใช้ K3s ได้ตามปกติ)
    ยังไม่มีแถว = เปิด
    """
    __tablename__ = "cloud_controls"

    id = Column(Integer, primary_key=True, default=1)
    burst_enabled = Column(Boolean, nullable=False, default=True)
    reason = Column(Text, nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_cloud_controls_single_row"),)
