"""
POST /api/webhook/reject-lab-image — ลบ lab image ที่ยัง PENDING ทั้งแถว DB และไฟล์บน R2
"""
import uuid

import pytest

from app.models.lab_image import ImageStatus, LabImage
from tests.lab_image.conftest import APPROVE_SECRET, WEBHOOK_SECRET

ENDPOINT = "/api/webhook/reject-lab-image"
HEADERS = {"Webhook-Secret": APPROVE_SECRET}


def _row(db, image_id):
    db.expire_all()
    return db.get(LabImage, uuid.UUID(str(image_id)))


def _reject(client, image_id, headers=HEADERS):
    return client.post(ENDPOINT, json={"labImageId": str(image_id)}, headers=headers)


class TestRejectSecret:
    def test_missing_wrong_or_upload_secret_is_401(self, client, db, fake_r2, create_draft):
        """Without the approve secret nothing is deleted (neither DB nor R2)"""
        draft = create_draft()
        for headers in ({}, {"Webhook-Secret": "nope"}, {"Webhook-Secret": WEBHOOK_SECRET}):
            assert _reject(client, draft["imageId"], headers).status_code == 401
        assert _row(db, draft["imageId"]) is not None
        assert fake_r2.deleted == []


class TestReject:
    def test_deletes_row_and_r2_object(self, client, db, fake_r2, create_draft):
        """A pending draft is removed from the DB and its archive deleted from R2"""
        draft = create_draft()
        response = _reject(client, draft["imageId"])

        assert response.status_code == 200
        assert response.json()["data"] == {
            "imageId": draft["imageId"],
            "archiveKey": draft["archiveKey"],
            "deleted": True,
        }
        assert _row(db, draft["imageId"]) is None
        assert fake_r2.deleted == [draft["archiveKey"]]

    def test_uploaded_pending_image_can_be_rejected(self, client, db, fake_r2, create_draft):
        """A pending image whose upload webhook already arrived is also deletable"""
        draft = create_draft()
        client.post(
            "/api/webhook/upload-trigger",
            json={"object_key": draft["archiveKey"], "size": 10, "etag": "a"},
            headers={"Webhook-Secret": WEBHOOK_SECRET},
        )
        assert _reject(client, draft["imageId"]).status_code == 200
        assert _row(db, draft["imageId"]) is None
        assert fake_r2.deleted == [draft["archiveKey"]]

    def test_only_target_is_deleted(self, client, db, fake_r2, create_draft):
        """Other images and their R2 objects are left alone"""
        target, other = create_draft(), create_draft(tag="lab-02")
        _reject(client, target["imageId"])
        assert _row(db, other["imageId"]) is not None
        assert fake_r2.deleted == [target["archiveKey"]]

    def test_repository_tag_can_be_reused_after_reject(self, client, create_draft):
        """After rejection the same repository:tag can request a fresh presign"""
        draft = create_draft()
        _reject(client, draft["imageId"])
        again = create_draft()
        assert again["imageId"] != draft["imageId"]

    def test_second_call_is_404(self, client, create_draft):
        """The row is gone, so repeating the call returns 404"""
        draft = create_draft()
        _reject(client, draft["imageId"])
        assert _reject(client, draft["imageId"]).status_code == 404

    def test_unknown_id_is_404(self, client, fake_r2):
        assert _reject(client, uuid.uuid4()).status_code == 404
        assert fake_r2.deleted == []

    @pytest.mark.parametrize("payload", [{}, {"labImageId": "not-a-uuid"}])
    def test_invalid_body_is_400(self, client, payload):
        assert client.post(ENDPOINT, json=payload, headers=HEADERS).status_code == 400


class TestRejectRefusals:
    @pytest.mark.parametrize("status", [ImageStatus.APPROVED, ImageStatus.REJECTED])
    def test_non_pending_is_409_and_untouched(self, client, db, fake_r2, create_draft, status):
        """Only PENDING images can be deleted; the R2 object is not touched"""
        draft = create_draft()
        _row(db, draft["imageId"]).status = status
        db.commit()

        assert _reject(client, draft["imageId"]).status_code == 409
        assert _row(db, draft["imageId"]) is not None
        assert fake_r2.deleted == []

    def test_r2_failure_keeps_row(self, client, db, fake_r2, create_draft):
        """If R2 delete fails the DB row stays, so the call can be retried"""
        draft = create_draft()
        fake_r2.fail_delete = True
        response = _reject(client, draft["imageId"])

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "r2_delete_failed"
        assert _row(db, draft["imageId"]) is not None

        fake_r2.fail_delete = False
        assert _reject(client, draft["imageId"]).status_code == 200
        assert _row(db, draft["imageId"]) is None

    def test_referenced_image_is_409_and_untouched(self, client, db, fake_r2, world, create_draft):
        """An image used by a lab is refused: row kept, lab.image_id kept, R2 untouched"""
        from app.models.lab import Lab

        draft = create_draft()
        lab = Lab(course_id=world.course.id, title="Lab 1", order_no=1, image_id=uuid.UUID(draft["imageId"]))
        db.add(lab)
        db.commit()

        assert _reject(client, draft["imageId"]).status_code == 409
        assert _row(db, draft["imageId"]) is not None
        db.refresh(lab)
        assert str(lab.image_id) == draft["imageId"]
        assert fake_r2.deleted == []
