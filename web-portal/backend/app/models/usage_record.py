from sqlalchemy import Column, BigInteger, Integer, Numeric, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True)
    cpu_seconds = Column(BigInteger, nullable=False)
    gpu_seconds = Column(BigInteger, nullable=False)
    ram_mb_hours = Column(Numeric(precision=12, scale=2), nullable=False)
    is_cloud_burst = Column(Boolean, default=False, nullable=False)
    est_cost_thb = Column(Numeric(precision=10, scale=2), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    session = relationship("Session", back_populates="usage_records", foreign_keys=[session_id])
    
    def __repr__(self):
        return f"<UsageRecord(id={self.id}, session_id={self.session_id}, cost={self.est_cost_thb})>"
