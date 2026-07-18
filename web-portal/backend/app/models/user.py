from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid
import enum


class UserRole(enum.Enum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


class User(Base):

    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    student_id = Column(String(50), unique=True, nullable=True, index=True)
    role = Column(Enum(UserRole), default=UserRole.STUDENT, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    enrollments = relationship("Enrollment", back_populates="user")
    created_courses = relationship("Course", back_populates="creator", foreign_keys="Course.created_by")
    uploaded_images = relationship("LabImage", back_populates="uploader")
    lab_progresses = relationship("LabProgress", back_populates="user")
    sessions = relationship("Session", back_populates="user")
    user_quotas = relationship("Quota", back_populates="user", foreign_keys="Quota.user_id")
    authored_announcements = relationship("Announcement", back_populates="author")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', name='{self.name}', role={self.role.value})>"


