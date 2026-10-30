from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.storage import get_storage
from app.exceptions.domain import NotFoundError, ValidationError
from app.models.course_document import CourseDocument
from app.models.user import User

DOC_MAX_BYTES = 50 * 1024 * 1024


class CourseDocumentService:
    """เอกสารรวมของวิชา (PDF) — สิทธิ์เช็กที่ route ด้วย verify_permission + course_policy แล้ว"""

    def __init__(self, db: Session, storage=None):
        self.db = db
        self.storage = storage or get_storage()

    def list(self, course_id: UUID) -> list[CourseDocument]:
        query = (
            select(CourseDocument)
            .where(CourseDocument.course_id == course_id, CourseDocument.deleted_at.is_(None))
            .order_by(CourseDocument.created_at)
        )
        return list(self.db.execute(query).scalars().all())

    def get(self, course_id: UUID, document_id: UUID) -> CourseDocument:
        doc = self.db.get(CourseDocument, document_id)
        # course_id ต้องตรงด้วย ไม่งั้นคนที่อ่านวิชา A ได้ เอา id เอกสารวิชา B มาเปิดผ่าน URL ของวิชา A
        if doc is None or doc.course_id != course_id or doc.deleted_at is not None:
            raise NotFoundError(f"Document {document_id} not found")
        return doc

    def get_existing(self, course_id: UUID, document_id: UUID) -> CourseDocument:
        """เอกสารที่มีไฟล์อยู่จริงใน storage (disk / S3) — ไฟล์หาย = 404 แยกข้อความไว้ไล่ปัญหา"""
        doc = self.get(course_id, document_id)
        if not self.storage.exists(doc.file_key):
            raise NotFoundError(f"Document file missing from storage: {doc.file_key}")
        return doc

    def upload(self, course_id: UUID, user: User, title: str, filename: str, source) -> CourseDocument:
        title = (title or "").strip() or Path(filename or "").stem.strip()
        if not title:
            raise ValidationError("Document name is required")
        if len(title) > 255:
            raise ValidationError("Document name is longer than 255 characters")
        if not (filename or "").lower().endswith(".pdf"):
            raise ValidationError("Only PDF documents are supported")

        source.file.seek(0, 2)
        size = source.file.tell()
        source.file.seek(0)
        if size == 0:
            raise ValidationError("Document is empty")
        if size > DOC_MAX_BYTES:
            raise ValidationError("Document is larger than 50 MB")

        doc_id = uuid4()
        key = f"course-docs/{course_id}/{doc_id}.pdf"
        self.storage.save(key, source.file, "application/pdf")
        doc = CourseDocument(
            id=doc_id, course_id=course_id, title=title, file_key=key, size_bytes=size, uploaded_by=user.id
        )
        self.db.add(doc)
        self.db.commit()
        return doc

    def delete(self, course_id: UUID, document_id: UUID) -> None:
        """soft delete — ไฟล์ยังอยู่ใน storage (กู้ได้ถ้าลบผิด)"""
        from datetime import datetime, timezone

        doc = self.get(course_id, document_id)
        doc.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
