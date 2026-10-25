from uuid import UUID

from app.models.user import User
from app.schemas.lab_image_schema import (
    LabImageResponse,
    LabImageUploadRequest,
    LabImageUploadResponse,
    R2UploadWebhookPayload,
    R2UploadWebhookResponse,
)
from app.services.lab_image_service import LabImageService


class LabImageController:
    def __init__(self, service: LabImageService):
        self.service = service

    def list_course_images(self, course_id: UUID, user: User) -> list[LabImageResponse]:
        return [
            LabImageResponse.model_validate(image)
            for image in self.service.list_course_images(course_id, user)
        ]

    def delete_image(self, image_id: UUID, user: User) -> int:
        return self.service.delete_image(image_id, user)

    def create_upload(
        self, payload: LabImageUploadRequest, user: User
    ) -> LabImageUploadResponse:
        return self.service.create_upload(payload, user)

    def handle_upload_webhook(
        self, payload: R2UploadWebhookPayload, webhook_secret: str | None
    ) -> R2UploadWebhookResponse:
        self.service.verify_webhook_secret(webhook_secret)
        return self.service.handle_upload_event(payload)
