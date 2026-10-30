import mimetypes
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status as http_status
from app.adapters.storage import content_disposition, get_storage
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
    LabDocUrlResponse,
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
        "data": controller.get_lab_by_course(course_id, current_user, status),
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
        "data": controller.get_lab(lab_id, current_user),
    }


@router.get("/{lab_id}/doc")
def get_lab_doc(
    lab_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller)
):
    """เปิดเอกสารแลป (ต้องเห็น lab นี้ได้) — disk: ส่งไฟล์ตรง / S3: 307 ไป presigned URL อายุสั้น"""
    key = controller.get_lab_doc_key(lab_id, current_user)
    return get_storage().response(key, **_doc_headers(key))


@router.get("/{lab_id}/doc-url", response_model=ApiResponse[LabDocUrlResponse])
def get_lab_doc_url(
    lab_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller),
):
    """URL สำหรับ fetch เอกสารจากหน้าเว็บ (react-pdf) — S3: presigned URL, disk: null (ใช้ /doc เดิม)

    fetch ข้าม origin ตาม redirect ของ /doc ไม่ได้ (Origin กลายเป็น null) จึงแยกเป็น endpoint คืน URL
    """
    key = controller.get_lab_doc_key(lab_id, current_user)
    url = get_storage().presigned_url(key, **_doc_headers(key))
    return {"success": True, "message": "Lab document URL", "data": {"url": url}}


@router.delete("/{lab_id}/doc", response_model=ApiResponse[LabResponse])
def delete_lab_doc(
    lab_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller),
):
    """ถอดเอกสารออกจาก lab (ผู้สอนวิชานั้น / admin) — ลบไฟล์ด้วยถ้าไม่มี lab อื่นใช้"""
    return {
        "success": True,
        "message": "Lab document removed",
        "data": controller.delete_lab_doc(lab_id, current_user),
    }


def _doc_headers(key: str) -> dict:
    filename = key.rsplit("/", 1)[-1]
    media_type, _ = mimetypes.guess_type(filename)
    return {"media_type": media_type or "application/octet-stream", "disposition": content_disposition(filename)}


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
    """สร้าง lab ใหม่ (ผู้สอนวิชานั้น / admin)"""
    return {
        "success": True,
        "message": "Lab created successfully",
        "data": controller.create_lab(payload, current_user),
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
    """อัปเดต lab (ผู้สอนวิชานั้น / admin)"""
    return {
        "success": True,
        "message": "Lab updated successfully",
        "data": controller.update_lab(lab_id, payload, current_user),
    }


@router.post("/{lab_id}/doc", response_model=ApiResponse[LabResponse])
def upload_lab_doc(
    lab_id: UUID,
    document: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller),
):
    """อัปโหลดเอกสาร PDF ของ lab (ผู้สอนวิชานั้น หรือ admin) — แทนไฟล์เดิมถ้ามี"""
    return {
        "success": True,
        "message": "Lab document uploaded successfully",
        "data": controller.save_lab_doc(lab_id, current_user, document.filename or "", document),
    }


@router.delete("/{lab_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_lab(
    lab_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: LabController = Depends(get_controller)
):
    """ลบ lab (ผู้สอนวิชานั้น / admin)"""
    controller.delete_lab(lab_id, current_user)
