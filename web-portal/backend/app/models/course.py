from sqlalchemy import Column, String, DateTime, ForeignKey, UUID
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid


class Course(Base):

    __tablename__ = "courses"
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    lecturer_name = Column(String(255), nullable=False)
    banner_color = Column(String(7), nullable=True)  
    created_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    creator = relationship("User", back_populates="created_courses", foreign_keys=[created_by])
    enrollments = relationship("Enrollment", back_populates="course")
    labs = relationship("Lab", back_populates="course")
    lab_images = relationship("LabImage", back_populates="course")
    course_quotas = relationship("Quota", back_populates="course", foreign_keys="Quota.course_id")
    announcements = relationship("Announcement", back_populates="course")
    
    def __repr__(self):
        return f"<Course(id={self.id}, code='{self.code}', name='{self.name}', lecturer='{self.lecturer_name}')>"
