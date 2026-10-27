from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.configs.db import Base
import uuid


class CourseDocument(Base):
    """เอกสารของวิชาที่ไม่ผูกกับ lab (เอกสารของ lab ยังอยู่ที่ labs.doc_url ตัวเดียว)"""

    __tablename__ = "course_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    # key ใน local storage: course-docs/<course_id>/<id>.pdf (ชื่อไฟล์ไม่ใช้ชื่อที่อัปมา กันชนกัน)
    file_key = Column(String(500), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    uploader = relationship("User", foreign_keys=[uploaded_by])

    def __repr__(self):
        return f"<CourseDocument(id={self.id}, course_id={self.course_id}, title='{self.title}')>"
