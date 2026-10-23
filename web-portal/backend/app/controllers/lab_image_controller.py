from app.models.user import User
from app.schemas.lab_image_schema import (
    LabImageApproveRequest,
    LabImageApproveResponse,
    LabImageRejectRequest,
    LabImageRejectResponse,
    LabImageUploadRequest,
    LabImageUploadResponse,
    R2UploadWebhookPayload,
    R2UploadWebhookResponse,
)
from app.services.lab_image_service import LabImageService


class LabImageController:
    def __init__(self, service: LabImageService):
        self.service = service

    def create_upload(
        self, payload: LabImageUploadRequest, user: User
    ) -> LabImageUploadResponse:
        return self.service.create_upload(payload, user)

    def handle_upload_webhook(
        self, payload: R2UploadWebhookPayload, webhook_secret: str | None
    ) -> R2UploadWebhookResponse:
        self.service.verify_webhook_secret(webhook_secret)
        return self.service.handle_upload_event(payload)

    def approve_image(
        self, payload: LabImageApproveRequest, webhook_secret: str | None
    ) -> LabImageApproveResponse:
        self.service.verify_approve_secret(webhook_secret)
        return self.service.approve_image(payload)

    def reject_image(
        self, payload: LabImageRejectRequest, webhook_secret: str | None
    ) -> LabImageRejectResponse:
        # ผู้ตัดสินใจ approve/reject เป็นฝั่งเดียวกัน จึงใช้ secret ชุดเดียวกัน
        self.service.verify_approve_secret(webhook_secret)
        return self.service.reject_image(payload)
