"""
ฟอร์ม Create lab ของ Instructor Console (สร้าง lab + ผูก image + เอกสารในครั้งเดียว)

- ไม่ส่ง orderNo = ต่อท้ายวิชาให้เอง
- ผูก image ที่ยังสแกนไม่ผ่านได้ แต่ publish ไม่ได้จนกว่า image จะ APPROVED
- อัปโหลดเอกสาร PDF ของ lab ได้เฉพาะผู้สอนวิชานั้น / admin
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.adapters.local_storage import LocalStorage
from app.models.lab_image import ImageStatus, LabImage, ScanStatus

PDF = b"%PDF-1.4\n%test\n"


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path, monkeypatch):
    """เอกสารที่อัปในเทสลง tmp ไม่ปนกับ storage จริง"""
    storage = LocalStorage(str(tmp_path))
    monkeypatch.setattr("app.services.lab_service.local_storage", storage)
    return storage


@pytest.fixture
def image(db, world):
    def _make(status=ImageStatus.PENDING, scan_status=ScanStatus.QUEUED):
        row = LabImage(
            id=uuid.uuid4(), uploaded_by=world.owner.id, course_id=world.course.id,
            repository="vlab/builder-test", tag=f"lab-{uuid.uuid4().hex[:6]}", size_mb=10,
            status=status, scan_status=scan_status, exposed_ports=[8443],
            archive_key=f"lab-images/{uuid.uuid4().hex}_image.tar",
            archive_size_bytes=10 * 1024 * 1024, archive_uploaded_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        return row
    return _make


@pytest.fixture
def create_lab(client, world, auth):
    def _create(expect=201, **overrides):
        body = {"courseId": str(world.course.id), "title": f"Lab {uuid.uuid4().hex[:4]}", **overrides}
        response = client.post("/api/labs", json=body, headers=auth(world.owner))
        assert response.status_code == expect, response.text
        return response.json()["data"] if expect == 201 else response.json()
    return _create


def test_create_without_order_appends_to_course(create_lab):
    first = create_lab()
    second = create_lab()
    assert (first["orderNo"], second["orderNo"]) == (1, 2)
    assert first["status"] == "draft"


def test_explicit_order_still_works_and_next_continues_after_it(create_lab):
    create_lab(orderNo=5)
    assert create_lab()["orderNo"] == 6


def test_draft_lab_can_attach_image_that_is_still_scanning(create_lab, image):
    lab = create_lab(imageId=str(image().id))
    assert lab["status"] == "draft"


def test_publish_blocked_until_image_approved(client, world, auth, db, create_lab, image):
    pending = image()
    lab = create_lab(imageId=str(pending.id))

    blocked = client.patch(f"/api/labs/{lab['id']}", json={"status": "published"}, headers=auth(world.owner))
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error"]["code"] == "lab_image_not_ready"

    pending.status, pending.scan_status = ImageStatus.APPROVED, ScanStatus.PASSED
    db.commit()
    ok = client.patch(f"/api/labs/{lab['id']}", json={"status": "published"}, headers=auth(world.owner))
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["status"] == "published"


def test_cannot_create_published_lab_with_unscanned_image(create_lab, image):
    error = create_lab(expect=400, imageId=str(image().id), status="published")
    assert error["error"]["code"] == "lab_image_not_ready"


def test_published_lab_cannot_swap_to_unscanned_image(client, world, auth, create_lab, image):
    lab = create_lab(status="published")
    response = client.patch(f"/api/labs/{lab['id']}", json={"imageId": str(image().id)}, headers=auth(world.owner))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "lab_image_not_ready"


def test_publish_reading_only_lab_without_image(client, world, auth, create_lab):
    lab = create_lab()
    response = client.patch(f"/api/labs/{lab['id']}", json={"status": "published"}, headers=auth(world.owner))
    assert response.status_code == 200


@pytest.mark.parametrize("who", ["owner", "co_instructor", "admin"])
def test_course_staff_can_upload_pdf_and_students_can_read_it(client, world, auth, create_lab, who):
    lab = create_lab()
    response = client.post(
        f"/api/labs/{lab['id']}/doc",
        files={"document": ("intro.pdf", PDF, "application/pdf")},
        headers=auth(getattr(world, who)),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["docUrl"] == f"labs/{lab['id']}/intro.pdf"

    doc = client.get(f"/api/labs/{lab['id']}/doc", headers=auth(world.student))
    assert doc.status_code == 200
    assert doc.content == PDF


@pytest.mark.parametrize("who", ["student", "outsider"])
def test_non_staff_cannot_upload_doc(client, world, auth, create_lab, who):
    lab = create_lab()
    response = client.post(
        f"/api/labs/{lab['id']}/doc",
        files={"document": ("intro.pdf", PDF, "application/pdf")},
        headers=auth(getattr(world, who)),
    )
    assert response.status_code == 403


def test_doc_must_be_pdf(client, world, auth, create_lab):
    lab = create_lab()
    response = client.post(
        f"/api/labs/{lab['id']}/doc",
        files={"document": ("notes.txt", b"hello", "text/plain")},
        headers=auth(world.owner),
    )
    assert response.status_code == 400
