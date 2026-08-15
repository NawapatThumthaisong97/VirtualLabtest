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
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    order_no = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    doc_url = Column(String(500), nullable=True)
    image_id = Column(UUID(as_uuid=True), ForeignKey("lab_images.id", ondelete="RESTRICT"), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(LabStatus), default=LabStatus.DRAFT, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(Timezone=True), onupdate=func.now() , nullable=True )
    deleted_at = Column(DateTime(Timezone=True), nullable=True , index=True)
    
    course = relationship("Course", back_populates="labs", foreign_keys=[course_id])
    image = relationship("LabImage", back_populates="labs", foreign_keys=[image_id])
    lab_progresses = relationship("LabProgress", back_populates="lab")
    sessions = relationship("Session", back_populates="lab")
    
    # Constraint - เราทําให้เมื่อ delete ไปแล้ว order จะรันซํ้าซ้อนต้องแก้ให้มันจําได้เลยว่า เลขนี้ต้องไม่มี deleted_at นะเพราะถ้ามีแสดงว่ามันมีเคยลบไปแล้ว
    __table_args__ = (
        Index('unique_course_order','course_id', 'order_no', unique=True , postgresql_where=("deleted_at IS NULL")),
    )
    
    def __repr__(self):
        status = self.status.value if self.status else None
        return f"<Lab(id={self.id}, course_id={self.course_id}, title='{self.title}', status='{self.status.value}')>"
