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
        self, course_id: UUID, status: LabStatus | None = None
    ) -> list[LabResponse]:
        labs = self.service.get_lab_by_course(course_id, status)
        return [LabResponse.model_validate(lab) for lab in labs]

    def get_lab(self, lab_id: UUID) -> LabDetailResponse:
        lab = self.service.get_lab_by_id(lab_id)
        return LabDetailResponse.model_validate(lab)

    def get_lab_doc_path(self, lab_id: UUID) -> Path:
        return self.service.get_lab_doc_path(lab_id)

    def create_lab(self, payload: LabCreateRequest) -> LabResponse:
        lab = self.service.create_lab(payload)
        return LabResponse.model_validate(lab)

    def update_lab(self, lab_id: UUID, payload: LabUpdateRequest) -> LabResponse:
        lab = self.service.update_lab(lab_id, payload)
        return LabResponse.model_validate(lab)

    def delete_lab(self, lab_id: UUID) -> None:
        return self.service.delete_lab(lab_id)
