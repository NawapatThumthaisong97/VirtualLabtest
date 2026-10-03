import mimetypes
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status as http_status
from fastapi.responses import FileResponse
from app.middlewares.request_validation import require_non_empty_body
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.controllers.lab_controller import LabController
from app.middlewares.auth import get_current_user
from app.models.lab import LabStatus
from app.models.user import User
from app.repositories.lab_repository import LabRepository
from app.schemas.lab_schema import (
    LabCreateRequest,
    LabDetailResponse,
    LabResponse,
    LabUpdateRequest,
)
from app.schemas.response import ApiResponse
from app.services.lab_service import LabService

router = APIRouter()


def get_controller(db: Session = Depends(get_db)) -> LabController:
    return LabController(LabService(db, LabRepository(db)))


@router.get("", response_model=ApiResponse[list[LabResponse]])
def list_labs(
    course_id: UUID = Query(..., alias="courseId"),
    status: LabStatus | None = Query(None),
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller),
):
    """lab ในวิชา พร้อม progressStatus ของคนที่เรียก (ต้อง login)"""
    return {
        "success": True,
        "message": "Labs retrieved successfully",
        "data": controller.get_lab_by_course(course_id, current_user.id, status),
    }


@router.get("/{lab_id}", response_model=ApiResponse[LabDetailResponse])
def get_lab(
    lab_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller)
):
    """ดึงข้อมูล lab (ต้อง login)"""
    return {
        "success": True,
        "message": "Lab retrieved successfully",
        "data": controller.get_lab(lab_id),
    }


@router.get("/{lab_id}/doc")
def get_lab_doc(
    lab_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller)
):
    """ส่งไฟล์เอกสารแลปออกไปตรง ๆ (ต้อง login)"""
    path = controller.get_lab_doc_path(lab_id)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )


@router.post(
    "",
    response_model=ApiResponse[LabResponse],
    status_code=http_status.HTTP_201_CREATED,
)
def create_lab(
    payload: LabCreateRequest,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller)
):
    """สร้าง lab ใหม่ (ต้อง login)"""
    return {
        "success": True,
        "message": "Lab created successfully",
        "data": controller.create_lab(payload),
    }


@router.patch(
    "/{lab_id}",
    response_model=ApiResponse[LabResponse],
    dependencies=[Depends(require_non_empty_body)],
)
def update_lab(
    lab_id: UUID,
    payload: LabUpdateRequest,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller),
):
    """อัปเดต lab (ต้อง login)"""
    return {
        "success": True,
        "message": "Lab updated successfully",
        "data": controller.update_lab(lab_id, payload),
    }


@router.delete("/{lab_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_lab(
    lab_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller)
):
    """ลบ lab (ต้อง login)"""
    controller.delete_lab(lab_id)
