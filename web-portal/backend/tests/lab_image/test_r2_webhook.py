"""
POST /api/webhook/upload-trigger — รับ event จาก Cloudflare Worker หลังไฟล์ขึ้น R2
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.configs.settings import settings
from app.models.lab_image import ImageStatus, LabImage
from tests.lab_image.conftest import WEBHOOK_SECRET

ENDPOINT = "/api/webhook/upload-trigger"
SECRET_HEADER = {"Webhook-Secret": WEBHOOK_SECRET}


def _event(object_key, **overrides):
    """payload เหมือนที่ cloudflare-worker/index.js ส่ง"""
    payload = {
        "account_id": "acct",
        "object_key": object_key,
        "action": "PutObject",
        "bucket": "virtual-lab-lab-image",
        "size": 734003200,
        "etag": '"abc123"',
        "event_time": "2026-10-23T10:00:00.000Z",
    }
    payload.update(overrides)
    return payload


def _row(db, image_id) -> LabImage:
    db.expire_all()
    return db.get(LabImage, uuid.UUID(image_id))


class TestWebhookSecret:
    """Webhook secret check"""

    def test_missing_secret_is_401(self, client, create_draft):
        """Request without the Webhook-Secret header is rejected"""
        draft = create_draft()
        assert client.post(ENDPOINT, json=_event(draft["archiveKey"])).status_code == 401

    def test_wrong_secret_is_401(self, client, create_draft, db):
        """A wrong secret is rejected and the row stays untouched"""
        draft = create_draft()
        response = client.post(
            ENDPOINT, json=_event(draft["archiveKey"]), headers={"Webhook-Secret": "nope"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_webhook_secret"
        assert _row(db, draft["imageId"]).archive_uploaded_at is None

    def test_unset_secret_rejects_everything(self, client, create_draft, monkeypatch):
        """Fail closed: with R2_WEBHOOK_SECRET unset even a header with the right-looking value is rejected"""
        draft = create_draft()
        monkeypatch.setattr(settings, "R2_WEBHOOK_SECRET", None)
        response = client.post(ENDPOINT, json=_event(draft["archiveKey"]), headers=SECRET_HEADER)
        assert response.status_code == 401

    def test_jwt_is_not_required(self, client, create_draft):
        """The webhook authenticates by secret only, no Authorization header needed"""
        draft = create_draft()
        response = client.post(ENDPOINT, json=_event(draft["archiveKey"]), headers=SECRET_HEADER)
        assert response.status_code == 200


class TestWebhookUpdate:
    """Webhook fills archive metadata"""

    def test_fills_archive_fields(self, client, db, create_draft):
        """etag, size and upload time from the event are saved on the matching row"""
        draft = create_draft()
        response = client.post(ENDPOINT, json=_event(draft["archiveKey"]), headers=SECRET_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert body["data"] == {
            "updated": True,
            "imageId": draft["imageId"],
            "objectKey": draft["archiveKey"],
        }
        image = _row(db, draft["imageId"])
        assert image.archive_etag == "abc123"  # quotes stripped
        assert image.archive_size_bytes == 734003200
        assert image.size_mb == 700  # replaces the client's estimate
        assert image.archive_uploaded_at == datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)

    def test_does_not_approve_or_set_digest(self, client, db, create_draft):
        """The webhook never changes status, digest or ownership"""
        draft = create_draft()
        before = _row(db, draft["imageId"])
        uploader, course = before.uploaded_by, before.course_id
        client.post(ENDPOINT, json=_event(draft["archiveKey"]), headers=SECRET_HEADER)

        image = _row(db, draft["imageId"])
        assert image.status is ImageStatus.PENDING
        assert image.image_digest is None
        assert (image.uploaded_by, image.course_id) == (uploader, course)

    def test_replay_is_idempotent(self, client, db, create_draft):
        """Queue redelivery of the same event leaves the same values"""
        draft = create_draft()
        for _ in range(3):
            response = client.post(ENDPOINT, json=_event(draft["archiveKey"]), headers=SECRET_HEADER)
            assert response.status_code == 200
        image = _row(db, draft["imageId"])
        assert (image.archive_etag, image.archive_size_bytes) == ("abc123", 734003200)
        assert db.query(LabImage).count() == 1

    def test_latest_event_wins(self, client, db, create_draft):
        """A later event for the same key (object overwritten) replaces the stored values"""
        draft = create_draft()
        client.post(ENDPOINT, json=_event(draft["archiveKey"]), headers=SECRET_HEADER)
        client.post(
            ENDPOINT,
            json=_event(draft["archiveKey"], etag="new-etag", size=1048576),
            headers=SECRET_HEADER,
        )
        image = _row(db, draft["imageId"])
        assert (image.archive_etag, image.archive_size_bytes, image.size_mb) == ("new-etag", 1048576, 1)

    def test_missing_event_time_uses_now(self, client, db, create_draft):
        """Without event_time the upload timestamp falls back to the current time"""
        draft = create_draft()
        client.post(
            ENDPOINT,
            json=_event(draft["archiveKey"], event_time=None),
            headers=SECRET_HEADER,
        )
        uploaded_at = _row(db, draft["imageId"]).archive_uploaded_at
        assert uploaded_at is not None
        assert abs((datetime.now(timezone.utc) - uploaded_at).total_seconds()) < 60

    def test_unknown_key_is_ignored_with_200(self, client, db, create_draft):
        """A key we never issued returns 200 updated=false so the Worker acks instead of retrying"""
        draft = create_draft()
        response = client.post(ENDPOINT, json=_event("some/other/file.tar"), headers=SECRET_HEADER)
        assert response.status_code == 200
        assert response.json()["data"]["updated"] is False
        assert _row(db, draft["imageId"]).archive_uploaded_at is None

    def test_only_matching_row_changes(self, client, db, create_draft):
        """With several drafts, only the one whose archive key matches is updated"""
        first = create_draft(tag="lab-01")
        second = create_draft(tag="lab-02")
        client.post(ENDPOINT, json=_event(first["archiveKey"]), headers=SECRET_HEADER)
        assert _row(db, first["imageId"]).archive_uploaded_at is not None
        assert _row(db, second["imageId"]).archive_uploaded_at is None

    @pytest.mark.parametrize("payload", [{}, {"object_key": ""}, {"size": -1, "object_key": "k"}])
    def test_invalid_payload_is_400(self, client, payload):
        """A payload without a usable object_key or with a negative size is rejected"""
        response = client.post(ENDPOINT, json=payload, headers=SECRET_HEADER)
        assert response.status_code == 400
