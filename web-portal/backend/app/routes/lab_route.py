from uuid import UUID

from fastapi import APIRouter, Depends, Query, status as http_status
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.controllers.lab_controller import LabController
from app.models.lab import LabStatus
from app.repositories.lab_repository import LabRepository
from app.schemas.lab_schema import LabCreateRequest, LabResponse, LabUpdateRequest
from app.services.lab_service import LabService

router = APIRouter()

def get_controller(db: Session = Depends(get_db)) -> LabController:
    return LabController(LabService(db, LabRepository(db)))


@router.get("", response_model=list[LabResponse])
def list_labs(
    course_id: UUID = Query(..., alias="courseId"),
    status: LabStatus | None = Query(None),
    controller: LabController = Depends(get_controller),
):
    return controller.get_lab_by_course(course_id, status)


@router.post("", response_model=LabResponse, status_code=http_status.HTTP_201_CREATED)
def create_lab(
    payload: LabCreateRequest, controller: LabController = Depends(get_controller)
):
    return controller.create_lab(payload)


@router.patch("/{lab_id}", response_model=LabResponse)
def update_lab(
    lab_id: UUID,
    payload: LabUpdateRequest,
    controller: LabController = Depends(get_controller),
):
    return controller.update_lab(lab_id, payload)


@router.delete("/{lab_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_lab(lab_id: UUID, controller: LabController = Depends(get_controller)):
    controller.delete_lab(lab_id)
