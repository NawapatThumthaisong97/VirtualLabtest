"""
POST /api/webhook/approve-lab-image — อนุมัติ lab image ด้วย Webhook-Secret
"""
import uuid

import pytest

from app.configs.settings import settings
from app.models.lab_image import ImageStatus, LabImage
from tests.lab_image.conftest import APPROVE_SECRET, WEBHOOK_SECRET

ENDPOINT = "/api/webhook/approve-lab-image"
UPLOAD_ENDPOINT = "/api/webhook/upload-trigger"
HEADERS = {"Webhook-Secret": APPROVE_SECRET}


def _row(db, image_id) -> LabImage:
    db.expire_all()
    return db.get(LabImage, uuid.UUID(str(image_id)))


@pytest.fixture
def uploaded(client, create_draft):
    """draft ที่ webhook upload เติมแล้ว (ไฟล์อยู่บน R2 รออนุมัติ)"""
    draft = create_draft()
    response = client.post(
        UPLOAD_ENDPOINT,
        json={"object_key": draft["archiveKey"], "size": 10240, "etag": "abc", "action": "PutObject"},
        headers={"Webhook-Secret": WEBHOOK_SECRET},
    )
    assert response.json()["data"]["updated"] is True
    return draft


class TestApproveSecret:
    """Approve webhook secret check"""

    def test_missing_secret_is_401(self, client, uploaded, db):
        """Request without the Webhook-Secret header is rejected and nothing changes"""
        response = client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]})
        assert response.status_code == 401
        assert _row(db, uploaded["imageId"]).status is ImageStatus.PENDING

    def test_wrong_secret_is_401(self, client, uploaded):
        """A wrong secret is rejected"""
        response = client.post(
            ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers={"Webhook-Secret": "nope"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_webhook_secret"

    def test_upload_webhook_secret_is_not_accepted(self, client, uploaded, db):
        """Regression: the Cloudflare upload secret cannot approve images, the two secrets are separate"""
        response = client.post(
            ENDPOINT,
            json={"labImageId": uploaded["imageId"]},
            headers={"Webhook-Secret": WEBHOOK_SECRET},
        )
        assert response.status_code == 401
        assert _row(db, uploaded["imageId"]).status is ImageStatus.PENDING

    def test_approve_secret_does_not_work_on_upload_webhook(self, client, uploaded):
        """The approve secret cannot be used to post upload events either"""
        response = client.post(
            UPLOAD_ENDPOINT, json={"object_key": uploaded["archiveKey"]}, headers=HEADERS
        )
        assert response.status_code == 401

    def test_unset_secret_rejects_everything(self, client, uploaded, monkeypatch):
        """Fail closed: with the approve secret unset every request is rejected"""
        monkeypatch.setattr(settings, "LAB_IMAGE_APPROVE_WEBHOOK_SECRET", None)
        response = client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers=HEADERS)
        assert response.status_code == 401

    def test_jwt_is_not_required(self, client, uploaded):
        """Authenticates by secret only, no Authorization header needed"""
        response = client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers=HEADERS)
        assert response.status_code == 200


class TestApprove:
    """Approve lab image"""

    def test_approves_uploaded_image(self, client, db, uploaded):
        """An uploaded PENDING image becomes APPROVED"""
        response = client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers=HEADERS)

        assert response.status_code == 200
        assert response.json()["data"] == {
            "imageId": uploaded["imageId"],
            "status": "approved",
            "updated": True,
        }
        assert _row(db, uploaded["imageId"]).status is ImageStatus.APPROVED

    def test_only_status_changes(self, client, db, uploaded):
        """Approving leaves digest, archive metadata and ownership untouched"""
        before = _row(db, uploaded["imageId"])
        snapshot = (before.image_digest, before.archive_key, before.archive_etag,
                    before.archive_size_bytes, before.archive_uploaded_at,
                    before.uploaded_by, before.course_id, before.size_mb)
        client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers=HEADERS)

        after = _row(db, uploaded["imageId"])
        assert (after.image_digest, after.archive_key, after.archive_etag,
                after.archive_size_bytes, after.archive_uploaded_at,
                after.uploaded_by, after.course_id, after.size_mb) == snapshot

    def test_second_call_is_idempotent(self, client, uploaded):
        """Approving an already approved image returns 200 with updated=false"""
        client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers=HEADERS)
        response = client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers=HEADERS)

        assert response.status_code == 200
        assert response.json()["data"]["updated"] is False
        assert response.json()["data"]["status"] == "approved"

    def test_other_images_are_not_touched(self, client, db, uploaded, create_draft):
        """Only the image with the given id is approved"""
        other = create_draft(tag="lab-02")
        client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers=HEADERS)
        assert _row(db, other["imageId"]).status is ImageStatus.PENDING


class TestApproveRejections:
    """Approve refusals"""

    def test_draft_without_archive_is_409(self, client, db, create_draft):
        """An image whose file never reached R2 cannot be approved"""
        draft = create_draft()
        response = client.post(ENDPOINT, json={"labImageId": draft["imageId"]}, headers=HEADERS)
        assert response.status_code == 409
        assert _row(db, draft["imageId"]).status is ImageStatus.PENDING

    def test_rejected_image_is_409(self, client, db, uploaded):
        """A rejected image cannot be approved through this endpoint"""
        image = _row(db, uploaded["imageId"])
        image.status = ImageStatus.REJECTED
        db.commit()
        response = client.post(ENDPOINT, json={"labImageId": uploaded["imageId"]}, headers=HEADERS)
        assert response.status_code == 409
        assert _row(db, uploaded["imageId"]).status is ImageStatus.REJECTED

    def test_unknown_id_is_404(self, client):
        """An id that does not exist returns 404"""
        response = client.post(ENDPOINT, json={"labImageId": str(uuid.uuid4())}, headers=HEADERS)
        assert response.status_code == 404

    @pytest.mark.parametrize("payload", [{}, {"labImageId": "not-a-uuid"}, {"labImageId": None}])
    def test_invalid_body_is_400(self, client, payload):
        """A missing or malformed labImageId is rejected"""
        response = client.post(ENDPOINT, json=payload, headers=HEADERS)
        assert response.status_code == 400
