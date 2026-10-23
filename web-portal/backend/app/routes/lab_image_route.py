from fastapi import APIRouter, Depends, Header, status as http_status
from sqlalchemy.orm import Session

from app.adapters.r2_adapter import r2_adapter
from app.configs.db import get_db
from app.controllers.lab_image_controller import LabImageController
from app.middlewares.auth import get_current_user
from app.middlewares.request_validation import require_non_empty_body
from app.models.user import User
from app.repositories.lab_image_repository import LabImageRepository
from app.schemas.lab_image_schema import (
    LabImageApproveRequest,
    LabImageApproveResponse,
    LabImageUploadRequest,
    LabImageUploadResponse,
    R2UploadWebhookPayload,
    R2UploadWebhookResponse,
)
from app.schemas.response import ApiResponse
from app.services.lab_image_service import LabImageService

router = APIRouter()


def get_controller(db: Session = Depends(get_db)) -> LabImageController:
    return LabImageController(LabImageService(db, LabImageRepository(db), r2_adapter))


@router.post(
    "/lab-image",
    response_model=ApiResponse[LabImageUploadResponse],
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_non_empty_body)],
)
def create_lab_image_upload(
    payload: LabImageUploadRequest,
    current_user: User = Depends(get_current_user),
    controller: LabImageController = Depends(get_controller),
):
    """สร้าง draft lab image แล้วคืน presigned PUT URL สำหรับอัปโหลด .tar ขึ้น R2

    ต้องเป็น instructor ที่สอนวิชา courseId ใน body (หรือ admin)
    """
    return {
        "success": True,
        "message": "Upload URL created",
        "data": controller.create_upload(payload, current_user),
    }


@router.post(
    "/webhook/upload-trigger",
    response_model=ApiResponse[R2UploadWebhookResponse],
)
def r2_upload_webhook(
    payload: R2UploadWebhookPayload,
    webhook_secret: str | None = Header(default=None, alias="Webhook-Secret"),
    controller: LabImageController = Depends(get_controller),
):
    """รับ event จาก Cloudflare Worker (R2 PutObject / CompleteMultipartUpload)

    ยืนยันตัวตนด้วย header Webhook-Secret เท่านั้น (ไม่ใช้ JWT)
    """
    data = controller.handle_upload_webhook(payload, webhook_secret)
    return {
        "success": True,
        "message": "Upload event recorded" if data.updated else "No matching lab image",
        "data": data,
    }


@router.post(
    "/webhook/approve-lab-image",
    response_model=ApiResponse[LabImageApproveResponse],
)
def approve_lab_image_webhook(
    payload: LabImageApproveRequest,
    webhook_secret: str | None = Header(default=None, alias="Webhook-Secret"),
    controller: LabImageController = Depends(get_controller),
):
    """อนุมัติ lab image (PENDING -> APPROVED) ตาม labImageId

    ยืนยันตัวตนด้วย header Webhook-Secret เท่านั้น (ไม่ใช้ JWT) ใช้ secret
    LAB_IMAGE_APPROVE_WEBHOOK_SECRET คนละชุดกับ webhook ของ Cloudflare
    """
    data = controller.approve_image(payload, webhook_secret)
    return {
        "success": True,
        "message": "Lab image approved" if data.updated else "Lab image already approved",
        "data": data,
    }
