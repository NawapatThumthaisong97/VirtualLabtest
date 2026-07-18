from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Enum, JSON
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid
import enum


class ServiceType(enum.Enum):
    LAB = "lab"
    COMPUTE = "compute"
    SANDBOX = "sandbox"
    AI_JOB = "ai_job"


class SessionStatus(enum.Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    lab_id = Column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=True)
    service_type = Column(Enum(ServiceType), nullable=False)
    k8s_pod_name = Column(String(255), nullable=True)
    node_name = Column(String(255), nullable=True)
    is_remote = Column(Boolean, default=False, nullable=False)
    is_cloud = Column(Boolean, default=False, nullable=False)
    sky_cluster_name = Column(String(255), nullable=True)
    sky_job_id = Column(Integer, nullable=True)
    image_ref = Column(String(500), nullable=True)
    endpoints = Column(JSON, nullable=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.PENDING, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions", foreign_keys=[user_id])
    lab = relationship("Lab", back_populates="sessions", foreign_keys=[lab_id])
    usage_records = relationship("UsageRecord", back_populates="session")
    
    def __repr__(self):
        return f"<Session(id={self.id}, user_id={self.user_id}, service_type='{self.service_type.value}', status='{self.status.value}')>"
