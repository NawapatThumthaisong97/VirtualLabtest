from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid

class File(Base):
    __tablename__ = "files"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    size_mb = Column(Integer, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    uploader = relationship("User", back_populates="uploaded_files", foreign_keys=[uploaded_by])
    course = relationship("Course", back_populates="files", foreign_keys=[course_id])
    
    def __repr__(self):
        return f"<File(id={self.id}, filename='{self.filename}', file_type='{self.file_type}', size_mb={self.size_mb})>"