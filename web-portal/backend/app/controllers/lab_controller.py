from pathlib import Path
from uuid import UUID

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

    def get_lab_by_course(
        self, course_id: UUID, user_id: UUID, status: LabStatus | None = None
    ) -> list[LabResponse]:
        rows = self.service.get_lab_by_course_for_user(course_id, user_id, status)
        return [
            LabResponse.model_validate(lab).model_copy(
                update={"progress_status": progress}
            )
            for lab, progress in rows
        ]

    def get_lab(self, lab_id: UUID) -> LabDetailResponse:
        lab = self.service.get_lab_by_id(lab_id)
        return LabDetailResponse.model_validate(lab)

    def get_lab_doc_path(self, lab_id: UUID) -> Path:
        return self.service.get_lab_doc_path(lab_id)

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
