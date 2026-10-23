"""
LabImageService.approve_image / reject_image — เรียกภายใน (ไม่มี HTTP endpoint)
"""
import uuid

import pytest

from app.exceptions.domain import ConflictError, LabImageNotFoundError
from app.adapters.r2_adapter import R2DeleteError
from app.models.lab_image import ImageStatus, LabImage
from app.repositories.lab_image_repository import LabImageRepository
from app.services.lab_image_service import LabImageService
from tests.lab_image.conftest import WEBHOOK_SECRET


@pytest.fixture
def service(db, fake_r2):
    return LabImageService(db, LabImageRepository(db), fake_r2)


def _row(db, image_id):
    db.expire_all()
    return db.get(LabImage, uuid.UUID(str(image_id)))


@pytest.fixture
def uploaded(client, create_draft):
    """draft ที่ webhook upload เติมแล้ว (ไฟล์อยู่บน R2 รออนุมัติ)"""
    draft = create_draft()
    response = client.post(
        "/api/webhook/upload-trigger",
        json={"object_key": draft["archiveKey"], "size": 10240, "etag": "abc", "action": "PutObject"},
        headers={"Webhook-Secret": WEBHOOK_SECRET},
    )
    assert response.json()["data"]["updated"] is True
    return draft


def test_endpoints_are_not_exposed(client, uploaded):
    """approve/reject are internal now: no HTTP route exists for them"""
    body = {"labImageId": uploaded["imageId"]}
    assert client.post("/api/webhook/approve-lab-image", json=body).status_code in (404, 405)
    assert client.post("/api/webhook/reject-lab-image", json=body).status_code in (404, 405)


class TestApprove:
    def test_approves_uploaded_image(self, service, db, uploaded):
        """An uploaded PENDING image becomes APPROVED"""
        assert service.approve_image(uuid.UUID(uploaded["imageId"])) is True
        assert _row(db, uploaded["imageId"]).status is ImageStatus.APPROVED

    def test_only_status_changes(self, service, db, uploaded):
        """Approving leaves digest, archive metadata and ownership untouched"""
        before = _row(db, uploaded["imageId"])
        fields = ("image_digest", "archive_key", "archive_etag", "archive_size_bytes",
                  "archive_uploaded_at", "uploaded_by", "course_id", "size_mb")
        snapshot = tuple(getattr(before, f) for f in fields)
        service.approve_image(before.id)
        after = _row(db, uploaded["imageId"])
        assert tuple(getattr(after, f) for f in fields) == snapshot

    def test_second_call_is_idempotent(self, service, uploaded):
        """Approving an already approved image returns False and changes nothing"""
        image_id = uuid.UUID(uploaded["imageId"])
        assert service.approve_image(image_id) is True
        assert service.approve_image(image_id) is False

    def test_other_images_are_not_touched(self, service, db, uploaded, create_draft):
        other = create_draft(tag="lab-02")
        service.approve_image(uuid.UUID(uploaded["imageId"]))
        assert _row(db, other["imageId"]).status is ImageStatus.PENDING

    def test_draft_without_archive_is_refused(self, service, db, create_draft):
        """An image whose file never reached R2 cannot be approved"""
        draft = create_draft()
        with pytest.raises(ConflictError):
            service.approve_image(uuid.UUID(draft["imageId"]))
        assert _row(db, draft["imageId"]).status is ImageStatus.PENDING

    def test_rejected_image_is_refused(self, service, db, uploaded):
        image = _row(db, uploaded["imageId"])
        image.status = ImageStatus.REJECTED
        db.commit()
        with pytest.raises(ConflictError):
            service.approve_image(image.id)
        assert _row(db, uploaded["imageId"]).status is ImageStatus.REJECTED

    def test_unknown_id(self, service):
        with pytest.raises(LabImageNotFoundError):
            service.approve_image(uuid.uuid4())


class TestReject:
    def test_deletes_row_and_r2_object(self, service, db, fake_r2, create_draft):
        """A pending draft is removed from the DB and its archive deleted from R2"""
        draft = create_draft()
        assert service.reject_image(uuid.UUID(draft["imageId"])) == draft["archiveKey"]
        assert _row(db, draft["imageId"]) is None
        assert fake_r2.deleted == [draft["archiveKey"]]

    def test_uploaded_pending_image_can_be_rejected(self, service, db, fake_r2, uploaded):
        service.reject_image(uuid.UUID(uploaded["imageId"]))
        assert _row(db, uploaded["imageId"]) is None
        assert fake_r2.deleted == [uploaded["archiveKey"]]

    def test_only_target_is_deleted(self, service, db, fake_r2, create_draft):
        target, other = create_draft(), create_draft(tag="lab-02")
        service.reject_image(uuid.UUID(target["imageId"]))
        assert _row(db, other["imageId"]) is not None
        assert fake_r2.deleted == [target["archiveKey"]]

    def test_repository_tag_can_be_reused_after_reject(self, service, create_draft):
        draft = create_draft()
        service.reject_image(uuid.UUID(draft["imageId"]))
        assert create_draft()["imageId"] != draft["imageId"]

    def test_second_call_is_not_found(self, service, create_draft):
        draft = create_draft()
        service.reject_image(uuid.UUID(draft["imageId"]))
        with pytest.raises(LabImageNotFoundError):
            service.reject_image(uuid.UUID(draft["imageId"]))

    def test_unknown_id(self, service, fake_r2):
        with pytest.raises(LabImageNotFoundError):
            service.reject_image(uuid.uuid4())
        assert fake_r2.deleted == []

    @pytest.mark.parametrize("status", [ImageStatus.APPROVED, ImageStatus.REJECTED])
    def test_non_pending_is_refused_and_untouched(self, service, db, fake_r2, create_draft, status):
        draft = create_draft()
        _row(db, draft["imageId"]).status = status
        db.commit()
        with pytest.raises(ConflictError):
            service.reject_image(uuid.UUID(draft["imageId"]))
        assert _row(db, draft["imageId"]) is not None
        assert fake_r2.deleted == []

    def test_r2_failure_keeps_row_and_can_retry(self, service, db, fake_r2, create_draft):
        """If R2 delete fails the DB row stays, so the call can be retried"""
        draft = create_draft()
        fake_r2.fail_delete = True
        with pytest.raises(R2DeleteError):
            service.reject_image(uuid.UUID(draft["imageId"]))
        assert _row(db, draft["imageId"]) is not None

        fake_r2.fail_delete = False
        service.reject_image(uuid.UUID(draft["imageId"]))
        assert _row(db, draft["imageId"]) is None

    def test_referenced_image_is_refused_and_untouched(self, service, db, fake_r2, world, create_draft):
        """An image used by a lab is refused: row kept, lab.image_id kept, R2 untouched"""
        from app.models.lab import Lab

        draft = create_draft()
        lab = Lab(course_id=world.course.id, title="Lab 1", order_no=1, image_id=uuid.UUID(draft["imageId"]))
        db.add(lab)
        db.commit()

        with pytest.raises(ConflictError):
            service.reject_image(uuid.UUID(draft["imageId"]))
        assert _row(db, draft["imageId"]) is not None
        db.refresh(lab)
        assert str(lab.image_id) == draft["imageId"]
        assert fake_r2.deleted == []
