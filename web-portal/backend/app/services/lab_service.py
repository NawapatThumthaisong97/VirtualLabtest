from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.adapters.local_storage import local_storage
from app.exceptions.domain import (
    CourseNotFoundError,
    DuplicateOrderNoError,
    ForbiddenError,
    InvalidLabImageError,
    LabDocNotFoundError,
    LabImageNotReadyError,
    LabNotFoundError,
    ValidationError,
)
from app.models.enrollment import RoleInCourse
from app.models.lab import Lab, LabStatus
from app.models.lab_image import ImageStatus, LabImage
from app.models.lab_progress import ProgressStatus
from app.models.user import User, UserRole
from app.repositories.lab_repository import LabRepository
from app.repositories.rbac_repository import RBACRepository
from app.schemas import LabCreateRequest, LabUpdateRequest, LabResponse


class LabService:
    def __init__(self, db: Session, lab_repo: LabRepository):
        self.db = db
        self.lab_repo = lab_repo

    # GET
    def get_lab_by_course(
        self, course_id: UUID, status: LabStatus | None = None
    ) -> list[Lab]:
        return self.lab_repo.find_by_course(course_id, status)

    def get_lab_by_course_for_user(
        self, course_id: UUID, user_id: UUID, status: LabStatus | None = None
    ) -> list[tuple[Lab, ProgressStatus | None]]:
        return self.lab_repo.find_by_course_with_progress(course_id, user_id, status)

    def get_lab_by_id(self, lab_id: UUID) -> Lab:
        lab = self.lab_repo.find_by_id(lab_id)
        if lab is None:
            raise LabNotFoundError(f"Lab {lab_id} not found")
        return lab

    def get_lab_doc_path(self, lab_id: UUID) -> Path:
        """
        คืน path ของไฟล์เอกสารแลปบน disk

        แยก 2 กรณีที่ต่างกันแต่ตอบ 404 เหมือนกัน: แลปยังไม่ได้แนบเอกสาร
        กับแนบไว้แล้วแต่ไฟล์หายไปจาก storage — ข้อความ error ต่างกันเพื่อให้
        admin ไล่ปัญหาได้ว่าลืมอัปโหลด หรือไฟล์ถูกลบ
        """
        lab = self.get_lab_by_id(lab_id)

        if not lab.doc_url:
            raise LabDocNotFoundError(f"Lab {lab_id} has no document attached")

        path = local_storage.resolve(lab.doc_url)
        if not path.is_file():
            raise LabDocNotFoundError(
                f"Document file missing from storage: {lab.doc_url}"
            )
        return path

    def _ensure_image_in_course(self, image_id: UUID | None, course_id: UUID) -> None:
        """image ต้องมีอยู่และเป็นของวิชาเดียวกับ lab

        ไม่เช็คไว้ image_id ที่ไม่มีจะชน FK แล้วถูกรายงานผิดเป็น duplicate order_no
        ส่วน image ของวิชาอื่นจะผูกได้เงียบๆ ทั้งที่อาจารย์วิชานี้ไม่ได้เป็นเจ้าของ
        """
        if image_id is None:
            return
        image = self.db.get(LabImage, image_id)
        if image is None or image.course_id != course_id:
            raise InvalidLabImageError(f"Lab image {image_id} does not belong to this course")

    def _ensure_publishable(self, lab: Lab) -> None:
        """publish ได้เมื่อไม่มี image (lab อ่านอย่างเดียว) หรือ image สแกนผ่านแล้ว (APPROVED)

        ฟอร์มอาจารย์ผูก image ตั้งแต่ตอนอัปโหลด .tar (ยังสแกนไม่จบ) เลยต้องกันตรงนี้
        ไม่งั้น publish แล้วนักศึกษากด Start ได้ทั้งที่ image ยังไม่มีใน registry
        """
        if lab.status != LabStatus.PUBLISHED or lab.image_id is None:
            return
        image = self.db.get(LabImage, lab.image_id)
        if image is None or image.status != ImageStatus.APPROVED:
            raise LabImageNotReadyError("Lab image has not passed the security scan yet")

    def ensure_can_manage(self, user: User, course_id: UUID) -> None:
        """admin ทุกวิชา / instructor ต้องเป็นผู้สร้างหรือ enroll เป็นผู้สอนวิชานี้ (เทียบ id ไม่ใช้ชื่อ)"""
        repo = RBACRepository(self.db)
        course = repo.find_active_course(course_id)
        if course is None:
            raise CourseNotFoundError(f"Course {course_id} not found")
        if user.role == UserRole.ADMIN:
            return
        if course.created_by == user.id or repo.is_enrolled(user.id, course_id, RoleInCourse.INSTRUCTOR):
            return
        raise ForbiddenError("ไม่ได้เป็นผู้สอนของวิชานี้")

    def can_manage(self, user: User, course_id: UUID) -> bool:
        """แบบไม่ raise — ใช้ตัดสินว่าจะให้เห็น lab ที่ยังไม่ published ไหม"""
        try:
            self.ensure_can_manage(user, course_id)
            return True
        except (CourseNotFoundError, ForbiddenError):
            return False

    # POST
    def create_lab(self, payload: LabCreateRequest) -> Lab:
        self._ensure_image_in_course(payload.image_id, payload.course_id)
        data = payload.model_dump()
        if data["order_no"] is None:
            data["order_no"] = self.lab_repo.next_order_no(payload.course_id)
        lab = Lab(**data)
        self._ensure_publishable(lab)
        try:
            self.lab_repo.save(lab)
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise DuplicateOrderNoError(
                f"order_no {lab.order_no} already exists in course {lab.course_id}"
            ) from e
        return lab

    # PATCH
    def update_lab(self, lab_id: UUID, payload: LabUpdateRequest) -> Lab:
        lab = self.lab_repo.find_by_id(lab_id)
        if lab is None:
            raise LabNotFoundError(f"Lab {lab_id} not found")

        data = payload.model_dump(exclude_unset=True)
        # run_target เป็น NOT NULL ส่ง null มา = ไม่แก้ (ไม่งั้น commit พังเป็น 500)
        if data.get("run_target", ...) is None:
            data.pop("run_target", None)
        if "image_id" in data:
            self._ensure_image_in_course(data["image_id"], lab.course_id)
        for key, value in data.items():
            setattr(lab, key, value)
        # เช็กหลัง setattr: ครอบทั้ง publish ตอนนี้ และเปลี่ยน image ของ lab ที่ publish อยู่แล้ว
        try:
            self._ensure_publishable(lab)
        except LabImageNotReadyError:
            self.db.rollback()
            raise

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise DuplicateOrderNoError(
                f"order_no {lab.order_no} already exists in course {lab.course_id}"
            ) from e
        return lab

    DOC_MAX_BYTES = 50 * 1024 * 1024

    def save_lab_doc(self, lab_id: UUID, user: User, filename: str, source) -> Lab:
        """บันทึกเอกสาร PDF ของ lab ลง local storage แล้วชี้ doc_url ไปที่ไฟล์นั้น

        key มี lab_id อยู่แล้ว ไฟล์ชื่อเดียวกันของคนละ lab จึงไม่ทับกัน
        อัปไฟล์ใหม่ซ้ำ = แทนของเดิม (doc_url มีได้ไฟล์เดียว)
        """
        lab = self.get_lab_by_id(lab_id)
        self.ensure_can_manage(user, lab.course_id)

        safe_filename = Path(filename or "").name
        if not safe_filename.lower().endswith(".pdf"):
            raise ValidationError("Only PDF documents are supported")

        source.file.seek(0, 2)
        size = source.file.tell()
        source.file.seek(0)
        if size == 0:
            raise ValidationError("Document is empty")
        if size > self.DOC_MAX_BYTES:
            raise ValidationError("Document is larger than 50 MB")

        key = f"labs/{lab.id}/{safe_filename}"
        local_storage.save(key, source.file)
        lab.doc_url = key
        self.db.commit()
        return lab

    # DELETE
    def delete_lab(self, lab_id: UUID) -> None:
        # Find object entity that we want to delete then pass to soft-delete as entity parameter
        lab = self.lab_repo.find_by_id(lab_id)
        if lab is None:
            raise LabNotFoundError(f"Lab {lab_id} not found")
        self.lab_repo.soft_delete(lab)
        self.db.commit()
