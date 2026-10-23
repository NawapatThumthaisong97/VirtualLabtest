from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from app.configs.db import Base


class HealthCheck(Base):
    """ผลตรวจ service 1 ครั้ง (job ใน backend ทุก HEALTH_CHECK_INTERVAL_SECONDS) — การ์ด System status หน้า admin

    เก็บแค่ HEALTH_CHECK_RETENTION_DAYS วัน (job ลบของเก่าทุกรอบ) 5 service × ทุก 5 นาที × 7 วัน ≈ 10,000 แถว
    """
    __tablename__ = "health_checks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    service = Column(String(32), nullable=False)         # backend / k8s / registry / skypilot / aws
    status = Column(String(16), nullable=False)          # ok / degraded / down
    latency_ms = Column(Integer, nullable=True)
    version = Column(String(64), nullable=True)
    detail = Column(Text, nullable=True)                 # สาเหตุตอน degraded / down หรือข้อมูลเสริม
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_health_checks_service_checked_at", "service", "checked_at"),
        Index("ix_health_checks_checked_at", "checked_at"),
    )

    def __repr__(self):
        return f"<HealthCheck(service={self.service}, status={self.status}, checked_at={self.checked_at})>"
