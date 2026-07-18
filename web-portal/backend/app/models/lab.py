from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid
import enum


class LabStatus(enum.Enum):
    """Enum สำหรับสถานะของ Lab"""
    DRAFT = "draft"
    PUBLISHED = "published"


class Lab(Base):

    __tablename__ = "labs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    order_no = Column(Integer, nullable=False)
    doc_url = Column(String(500), nullable=True)
    image_id = Column(UUID(as_uuid=True), ForeignKey("lab_images.id"), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(LabStatus), default=LabStatus.DRAFT, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    course = relationship("Course", back_populates="labs", foreign_keys=[course_id])
    image = relationship("LabImage", back_populates="labs", foreign_keys=[image_id])
    lab_progresses = relationship("LabProgress", back_populates="lab")
    sessions = relationship("Session", back_populates="lab")
    
    # Constraint - order_no unique ต่อ course
    __table_args__ = (
        UniqueConstraint('course_id', 'order_no', name='unique_course_order'),
    )
    
    def __repr__(self):
        return f"<Lab(id={self.id}, course_id={self.course_id}, title='{self.title}', status='{self.status.value}')>"
