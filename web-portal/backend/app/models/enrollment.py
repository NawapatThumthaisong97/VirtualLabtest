from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid
import enum


class RoleInCourse(enum.Enum):
    STUDENT = "student"
    TA = "ta"
    INSTRUCTOR = "instructor"


class Enrollment(Base):

    __tablename__ = "enrollments"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True, nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), primary_key=True, nullable=False)
    role_in_course = Column(Enum(RoleInCourse), default=RoleInCourse.STUDENT, nullable=False)
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    user = relationship("User", back_populates="enrollments", foreign_keys=[user_id])
    course = relationship("Course", back_populates="enrollments", foreign_keys=[course_id])
    
    def __repr__(self):
        return f"<Enrollment(user_id={self.user_id}, course_id={self.course_id}, role='{self.role_in_course.value}')>"
