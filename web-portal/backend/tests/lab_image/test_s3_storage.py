"""
ไฟล์ของเว็บบน S3 (STORAGE_BACKEND=s3) — ใช้ FakeS3Client ไม่ต่อ AWS จริง

- อัป PDF ของ lab / เอกสารวิชา / รูปปก ไปที่ key เดิมที่ DB เก็บ (prefix labs/ course-docs/ courses/)
- เปิดไฟล์: backend เช็กสิทธิ์แล้วตอบ 307 ไป presigned URL ที่บอก S3 ให้ตอบ content-type / ชื่อไฟล์
- doc-url คืน URL ให้ react-pdf fetch ตรง, ลบเอกสาร / อัปทับ ลบไฟล์เก่าที่ไม่มีใครใช้
"""
import pytest

from app.adapters.s3_storage import S3Storage
from app.adapters.storage import content_disposition
from app.exceptions.domain import ValidationError
from tests.fakes import FakeS3Client

PDF = b"%PDF-1.4\n%s3\n"
BUCKET = "vlab-web-storage-test"


@pytest.fixture
def s3(monkeypatch):
    client = FakeS3Client()
    monkeypatch.setattr("app.adapters.storage._storage", S3Storage(BUCKET, "ap-southeast-1", client=client, presign_seconds=120))
    return client


# ---------- adapter ----------

def test_save_exists_delete_and_presign():
    client = FakeS3Client()
    storage = S3Storage(BUCKET, "ap-southeast-1", client=client, presign_seconds=60)
    import io

    storage.save("labs/x/a.pdf", io.BytesIO(PDF), "application/pdf")
    assert client.objects["labs/x/a.pdf"] == (PDF, "application/pdf")
    assert storage.exists("labs/x/a.pdf") and not storage.exists("labs/x/missing.pdf")

    url = storage.presigned_url("labs/x/a.pdf", media_type="application/pdf", disposition="inline; filename=\"a.pdf\"")
    assert url.startswith(f"https://{BUCKET}.")
    assert client.presigned[-1] == {
        "operation": "get_object", "expires_in": 60, "Bucket": BUCKET, "Key": "labs/x/a.pdf",
        "ResponseContentType": "application/pdf", "ResponseContentDisposition": "inline; filename=\"a.pdf\"",
    }

    storage.delete("labs/x/a.pdf")
    assert not storage.exists("labs/x/a.pdf")


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs/key", "labs/../../x", ""])
def test_rejects_weird_keys(key):
    with pytest.raises(ValidationError):
        S3Storage(BUCKET, "ap-southeast-1", client=FakeS3Client()).exists(key)


def test_content_disposition_keeps_thai_name():
    header = content_disposition("เอกสาร บทที่ 1.pdf")
    assert header.startswith('inline; filename="')
    assert "filename*=UTF-8''%E0%B9%80" in header


# ---------- ผ่าน API ----------

@pytest.fixture
def published_lab(client, world, auth):
    response = client.post(
        "/api/labs", json={"courseId": str(world.course.id), "title": "S3 lab", "status": "published"}, headers=auth(world.owner)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def upload_doc(client, auth, user, lab_id, name="guide.pdf"):
    return client.post(f"/api/labs/{lab_id}/doc", files={"document": (name, PDF, "application/pdf")}, headers=auth(user))


def test_lab_doc_goes_to_s3_and_opens_by_redirect(s3, client, world, auth, published_lab):
    lab_id = published_lab["id"]
    assert upload_doc(client, auth, world.owner, lab_id).status_code == 200
    assert s3.objects[f"labs/{lab_id}/guide.pdf"] == (PDF, "application/pdf")

    opened = client.get(f"/api/labs/{lab_id}/doc", headers=auth(world.student), follow_redirects=False)
    assert opened.status_code == 307
    assert opened.headers["location"].startswith(f"https://{BUCKET}.")
    assert opened.headers["cache-control"] == "no-store"
    assert s3.presigned[-1]["ResponseContentType"] == "application/pdf"
    assert s3.presigned[-1]["expires_in"] == 120

    url = client.get(f"/api/labs/{lab_id}/doc-url", headers=auth(world.student)).json()["data"]["url"]
    assert url.startswith(f"https://{BUCKET}.")


def test_doc_url_hidden_like_doc(s3, client, world, auth, published_lab):
    upload_doc(client, auth, world.owner, published_lab["id"])
    response = client.get(f"/api/labs/{published_lab['id']}/doc-url", headers=auth(world.outsider))
    assert response.status_code == 404


def test_replacing_lab_doc_deletes_old_object(s3, client, world, auth, published_lab):
    lab_id = published_lab["id"]
    upload_doc(client, auth, world.owner, lab_id, "v1.pdf")
    upload_doc(client, auth, world.owner, lab_id, "v2.pdf")
    assert f"labs/{lab_id}/v1.pdf" in s3.deleted
    assert f"labs/{lab_id}/v2.pdf" in s3.objects


def test_delete_lab_doc(s3, client, world, auth, published_lab):
    lab_id = published_lab["id"]
    upload_doc(client, auth, world.owner, lab_id)
    assert client.delete(f"/api/labs/{lab_id}/doc", headers=auth(world.student)).status_code == 403
    response = client.delete(f"/api/labs/{lab_id}/doc", headers=auth(world.owner))
    assert response.status_code == 200 and response.json()["data"]["docUrl"] is None
    assert f"labs/{lab_id}/guide.pdf" not in s3.objects
    assert client.get(f"/api/labs/{lab_id}/doc", headers=auth(world.owner)).status_code == 404


def test_shared_doc_is_kept_when_one_lab_drops_it(s3, client, db, world, auth, published_lab):
    # seed SE301: สาม lab ชี้ workbook ไฟล์เดียว — ถอดจาก lab หนึ่งต้องไม่ลบไฟล์ของอีกสอง
    from app.models.lab import Lab

    lab_id = published_lab["id"]
    upload_doc(client, auth, world.owner, lab_id)
    other = client.post(
        "/api/labs", json={"courseId": str(world.course.id), "title": "twin", "docUrl": f"labs/{lab_id}/guide.pdf"},
        headers=auth(world.owner),
    ).json()["data"]
    assert db.get(Lab, other["id"]) is not None
    client.delete(f"/api/labs/{lab_id}/doc", headers=auth(world.owner))
    assert f"labs/{lab_id}/guide.pdf" in s3.objects


def test_course_document_on_s3(s3, client, world, auth):
    created = client.post(
        f"/api/courses/{world.course.id}/documents", data={"title": "บทนำ"},
        files={"document": ("intro.pdf", PDF, "application/pdf")}, headers=auth(world.owner),
    ).json()
    assert s3.objects[f"course-docs/{world.course.id}/{created['id']}.pdf"][1] == "application/pdf"
    opened = client.get(
        f"/api/courses/{world.course.id}/documents/{created['id']}/file", headers=auth(world.student), follow_redirects=False
    )
    assert opened.status_code == 307
    assert "filename*=UTF-8''%E0%B8%9A" in s3.presigned[-1]["ResponseContentDisposition"]


def test_course_image_upload_open_and_delete(s3, client, world, auth):
    # สิทธิ์ storage:images:push:course ต้อง enroll เป็นผู้สอน (ผู้สร้างวิชาเฉย ๆ ไม่พอ — พฤติกรรม RBAC เดิม)
    png = b"\x89PNG\r\n\x1a\nfake"
    uploaded = client.post(
        f"/api/courses/{world.course.id}/image", files={"image": ("cover.png", png, "image/png")},
        headers=auth(world.co_instructor),
    )
    assert uploaded.status_code == 200, uploaded.text
    assert s3.objects[f"courses/{world.course.id}/cover.png"] == (png, "image/png")

    opened = client.get(f"/api/courses/{world.course.id}/image", headers=auth(world.student), follow_redirects=False)
    assert opened.status_code == 307 and s3.presigned[-1]["ResponseContentType"] == "image/png"

    assert client.delete(f"/api/courses/{world.course.id}/image", headers=auth(world.student)).status_code == 403
    deleted = client.delete(f"/api/courses/{world.course.id}/image", headers=auth(world.co_instructor))
    assert deleted.status_code == 200
    assert f"courses/{world.course.id}/cover.png" not in s3.objects
