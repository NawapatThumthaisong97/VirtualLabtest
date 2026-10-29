from uuid import UUID

from app.exceptions.domain import ForbiddenError, LabNotFoundError
from app.models.lab import LabStatus
from app.schemas.lab_schema import (
    LabCreateRequest,
    LabDetailResponse,
    LabResponse,
    LabUpdateRequest,
)
from app.services.lab_service import LabService


class LabController:
    def __init__(self, service: LabService):
        self.service = service

    # ผู้สอนวิชานั้น / admin เห็นทุก lab, คนที่ลงทะเบียนวิชาเห็นเฉพาะ published, คนนอกวิชาไม่เห็นเลย
    # lab ที่ซ่อนตอบเหมือนไม่มี lab นั้น (ไม่บอกว่ามี draft อยู่)
    def get_lab_by_course(
        self, course_id: UUID, user, status: LabStatus | None = None
    ) -> list[LabResponse]:
        if not self.service.can_manage(user, course_id):
            if not self.service.is_enrolled(user, course_id):
                raise ForbiddenError("ไม่ได้ลงทะเบียนวิชานี้")
            if status not in (None, LabStatus.PUBLISHED):
                return []
            status = LabStatus.PUBLISHED
        rows = self.service.get_lab_by_course_for_user(course_id, user.id, status)
        return [
            LabResponse.model_validate(lab).model_copy(
                update={"progress_status": progress}
            )
            for lab, progress in rows
        ]

    def _get_visible_lab(self, lab_id: UUID, user):
        lab = self.service.get_lab_by_id(lab_id)
        if self.service.can_manage(user, lab.course_id):
            return lab
        if lab.status != LabStatus.PUBLISHED or not self.service.is_enrolled(user, lab.course_id):
            raise LabNotFoundError(f"Lab {lab_id} not found")
        return lab

    def get_lab(self, lab_id: UUID, user) -> LabDetailResponse:
        return LabDetailResponse.model_validate(self._get_visible_lab(lab_id, user))

    def get_lab_doc_key(self, lab_id: UUID, user) -> str:
        self._get_visible_lab(lab_id, user)
        return self.service.get_lab_doc_key(lab_id)

    def delete_lab_doc(self, lab_id: UUID, user) -> LabResponse:
        return LabResponse.model_validate(self.service.delete_lab_doc(lab_id, user))

    # สร้าง / แก้ / ลบ lab ได้เฉพาะผู้สอนวิชานั้นหรือ admin (เดิมแค่ login ก็ทำได้ นักศึกษาแก้ lab ได้)
    def create_lab(self, payload: LabCreateRequest, user) -> LabResponse:
        self.service.ensure_can_manage(user, payload.course_id)
        lab = self.service.create_lab(payload)
        return LabResponse.model_validate(lab)

    def update_lab(self, lab_id: UUID, payload: LabUpdateRequest, user) -> LabResponse:
        self.service.ensure_can_manage(user, self.service.get_lab_by_id(lab_id).course_id)
        lab = self.service.update_lab(lab_id, payload)
        return LabResponse.model_validate(lab)

    def save_lab_doc(self, lab_id: UUID, user, filename: str, source) -> LabResponse:
        lab = self.service.save_lab_doc(lab_id, user, filename, source)
        return LabResponse.model_validate(lab)

    def delete_lab(self, lab_id: UUID, user) -> None:
        self.service.ensure_can_manage(user, self.service.get_lab_by_id(lab_id).course_id)
        return self.service.delete_lab(lab_id)
