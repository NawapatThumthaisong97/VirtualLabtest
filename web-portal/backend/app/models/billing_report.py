"""
BillingReport Model
บันทึกประวัติการส่งออกรายงานสรุปค่าใช้จ่าย สำหรับฝ่ายบริหารและการตรวจสอบย้อนหลัง
รองรับกลไก Soft-Delete ผ่านฟิลด์ deleted_at
"""

from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid


class BillingReport(Base):
    __tablename__ = "billing_reports"
    __table_args__ = (
        Index("ix_billing_reports_created_at", "created_at"),
        Index("ix_billing_reports_deleted_at", "deleted_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String(255), nullable=False)
    group_by = Column(String(50), nullable=False)  # course, cluster, anon_id
    export_format = Column(String(10), nullable=False)  # csv, pdf
    file_name = Column(String(255), nullable=False)
    total_cost_thb = Column(Numeric(precision=12, scale=2), nullable=False, default=0.0)
    total_records = Column(Integer, nullable=False, default=0)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    @property
    def is_deleted(self) -> bool:
        """ตรวจสอบว่ารายงานถูก Soft-Delete แล้วหรือไม่"""
        return self.deleted_at is not None

    def __repr__(self) -> str:
        return f"<BillingReport(id={self.id}, title='{self.title}', format='{self.export_format}', cost={self.total_cost_thb})>"
