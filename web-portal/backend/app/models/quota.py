from sqlalchemy import Column, Integer, Numeric, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid
import enum


class QuotaPeriod(enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    SEMESTER = "semester"


class Quota(Base):
    __tablename__ = "quotas"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    compute_hours_limit = Column(Numeric(precision=10, scale=2), nullable=False)
    storage_mb_limit = Column(Integer, nullable=False)
    period = Column(Enum(QuotaPeriod), nullable=False)
    
    user = relationship("User", back_populates="user_quotas", foreign_keys=[user_id])
    course = relationship("Course", back_populates="course_quotas", foreign_keys=[course_id])
    
    def __repr__(self):
        return f"<Quota(id={self.id}, user_id={self.user_id}, course_id={self.course_id}, period='{self.period.value}')>"
