from sqlalchemy import Column, String, DateTime, ForeignKey, UUID
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.configs.db import Base
import uuid


class CourseImage(Base):
    """
    Course Image Model
    เก็บ S3 URL ของรูปภาพ Course
    1 Course มี 1 รูปภาพ
    """

    __tablename__ = "course_images"
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    course_id = Column(PG_UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True, unique=True)
    
    # S3 URL ของรูปภาพ
    image_url = Column(String(2048), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    def __repr__(self):
        return f"<CourseImage(id={self.id}, course_id={self.course_id}, url='{self.image_url[:50]}...')>"
