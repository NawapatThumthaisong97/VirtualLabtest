"""
InfrastructureLog Model
สำหรับเก็บบันทึก Critical Infrastructure Error Logs และ Security Boundary Violation Events
พร้อมระบบ Masking ข้อมูลส่วนตัว (PII) และการแปลง user_id เป็น HMAC-SHA256 anon_id
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import JSON
from sqlalchemy.sql import func

from app.configs.db import Base


class InfrastructureLog(Base):
    """
    เก็บบันทึกเหตุการณ์ระดับโครงสร้างพื้นฐานและการละเมิดความปลอดภัย (SIEM-Ready)
    มี Composite Indexes สำหรับค้นหาตามช่วงเวลา, หมวดหมู่ และระดับความรุนแรง
    """
    __tablename__ = "infrastructure_logs"
    __table_args__ = (
        Index("ix_infra_logs_timestamp_severity", "timestamp", "severity"),
        Index("ix_infra_logs_category_severity", "category", "severity"),
        Index("ix_infra_logs_cluster_subnet", "cluster_or_subnet"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    severity = Column(String(50), nullable=False)
    category = Column(String(50), nullable=False)
    event_type = Column(String(100), nullable=False)
    source = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    anon_id = Column(String(64), nullable=True, index=True)
    cluster_or_subnet = Column(String(255), nullable=True)
    metadata_json = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<InfrastructureLog(id={self.id}, event_type='{self.event_type}', severity='{self.severity}')>"
