from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid
import enum


class ImageStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class LabImage(Base):
    __tablename__ = "lab_images"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True)
    repository = Column(String(255), nullable=False)
    tag = Column(String(100), nullable=False)
    image_digest = Column(String(255), nullable=False, unique=True)
    size_mb = Column(Integer, nullable=False)
    status = Column(Enum(ImageStatus), default=ImageStatus.PENDING, nullable=False)
    upload_link_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    uploader = relationship("User", back_populates="uploaded_images", foreign_keys=[uploaded_by])
    course = relationship("Course", back_populates="lab_images", foreign_keys=[course_id])
    labs = relationship("Lab", back_populates="image")
    
    def __repr__(self):
        return f"<LabImage(id={self.id}, repository='{self.repository}', tag='{self.tag}', status='{self.status.value}')>"
