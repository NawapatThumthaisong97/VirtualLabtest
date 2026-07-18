from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import enum


class ProgressStatus(enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class LabProgress(Base):
    __tablename__ = "lab_progress"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True, nullable=False)
    lab_id = Column(UUID(as_uuid=True), ForeignKey("labs.id"), primary_key=True, nullable=False)
    status = Column(Enum(ProgressStatus), default=ProgressStatus.NOT_STARTED, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    user = relationship("User", back_populates="lab_progresses", foreign_keys=[user_id])
    lab = relationship("Lab", back_populates="lab_progresses", foreign_keys=[lab_id])
    
    def __repr__(self):
        return f"<LabProgress(user_id={self.user_id}, lab_id={self.lab_id}, status='{self.status.value}')>"
