from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid
import enum


class ServiceType(enum.Enum):
    """
    Service types สำหรับ sessions:
    
    - LAB: Lab assignment ที่นักเรียนทำ (ผูกกับ lab_id)
    - COMPUTE_SERVICE: General compute/sandbox ที่ไม่ผูกกับ lab
    - AI_TRAINING: AI/ML model training jobs (มักใช้ GPU, รันนาน, ต้อง checkpoint)
    """
    LAB = "lab"
    COMPUTE_SERVICE = "compute_service"
    AI_TRAINING = "ai_training"


class SessionStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    lab_id = Column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=True)
    lab_image_id = Column(UUID(as_uuid=True), ForeignKey("lab_images.id"), nullable=True)
    service_type = Column(Enum(ServiceType), nullable=False)
    k8s_pod_name = Column(String(255), nullable=True)   # ****** Must Check
    node_name = Column(String(255), nullable=True)      # ****** Must Check
    is_remote = Column(Boolean, default=False, nullable=False)
    is_cloud = Column(Boolean, default=False, nullable=False)
    sky_cluster_name = Column(String(255), nullable=True)
    sky_job_id = Column(Integer, nullable=True)
    endpoints = Column(JSONB, nullable=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.PENDING, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions", foreign_keys=[user_id])
    lab = relationship("Lab", back_populates="sessions", foreign_keys=[lab_id])
    lab_image = relationship("LabImage", back_populates="sessions", foreign_keys=[lab_image_id])
    usage_records = relationship("UsageRecord", back_populates="session")
    
    def __repr__(self):
        return f"<Session(id={self.id}, user_id={self.user_id}, service_type='{self.service_type.value}', status='{self.status.value}')>"
