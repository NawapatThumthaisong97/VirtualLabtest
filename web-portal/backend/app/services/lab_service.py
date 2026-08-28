from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.exceptions.domain import DuplicateOrderNoError, LabNotFoundError
from app.models.lab import Lab, LabStatus
from app.repositories.lab_repository import LabRepository
from app.schemas import LabCreateRequest, LabUpdateRequest, LabResponse


class LabService:
    def __init__(self, db: Session, lab_repo: LabRepository):
        self.db = db
        self.lab_repo = lab_repo

    #GET
    def get_lab_by_course(
        self, course_id: UUID, status: LabStatus | None = None
    ) -> list[Lab]:
        return self.lab_repo.find_by_course(course_id, status)

    #POST
    def create_lab(self, payload: LabCreateRequest) -> Lab:
        lab = Lab(**payload.model_dump())
        try:
            self.lab_repo.save(lab)
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise DuplicateOrderNoError(
                f"order_no {lab.order_no} already exists in course {lab.course_id}"
            ) from e
        return lab

    #PATCH
    def update_lab(self, lab_id: UUID, payload: LabUpdateRequest) -> Lab:
        lab = self.lab_repo.find_by_id(lab_id)
        if lab is None:
            raise LabNotFoundError(f"Lab {lab_id} not found")

        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(lab, key, value)

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise DuplicateOrderNoError(
                f"order_no {lab.order_no} already exists in course {lab.course_id}"
            ) from e
        return lab

    #DELETE
    def delete_lab(self, lab_id: UUID) -> None:
        # Find object entity that we want to delete then pass to soft-delete as entity parameter
        lab = self.lab_repo.find_by_id(lab_id)
        if lab is None:
            raise LabNotFoundError(f"Lab {lab_id} not found")
        self.lab_repo.soft_delete(lab)
        self.db.commit()
