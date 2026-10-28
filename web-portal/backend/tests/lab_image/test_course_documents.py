"""
เอกสารของวิชาที่ไม่ผูกกับ lab (Instructor Console → Add new document → ไม่ผูก lab)

- ผู้สอนวิชา / admin อัปโหลด + ลบได้, นักศึกษาที่ลงเรียนดู + ดาวน์โหลดได้
- คนนอกวิชาดูไม่ได้ และเอา id เอกสารวิชาอื่นมาเปิดผ่าน URL วิชานี้ไม่ได้
"""
import uuid

import pytest

from app.adapters.local_storage import LocalStorage
from app.models.courses import Course

PDF = b"%PDF-1.4\n%course-doc\n"


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    monkeypatch.setattr("app.adapters.storage._storage", storage)
    return storage


@pytest.fixture
def upload(client, world, auth):
    def _upload(user=None, title="Syllabus", filename="syllabus.pdf", content=PDF, course=None, expect=201):
        course = course or world.course
        response = client.post(
            f"/api/courses/{course.id}/documents",
            data={"title": title},
            files={"document": (filename, content, "application/pdf")},
            headers=auth(user or world.owner),
        )
        assert response.status_code == expect, response.text
        return response.json()
    return _upload


@pytest.mark.parametrize("who", ["owner", "co_instructor", "admin"])
def test_staff_upload_and_enrolled_student_lists_and_downloads(client, world, auth, upload, who):
    doc = upload(user=getattr(world, who))
    assert doc["title"] == "Syllabus"
    assert doc["sizeBytes"] == len(PDF)

    listed = client.get(f"/api/courses/{world.course.id}/documents", headers=auth(world.student))
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [doc["id"]]

    file = client.get(f"/api/courses/{world.course.id}/documents/{doc['id']}/file", headers=auth(world.student))
    assert file.status_code == 200
    assert file.content == PDF


def test_title_defaults_to_filename(upload):
    assert upload(title="", filename="week-01 slides.pdf")["title"] == "week-01 slides"


@pytest.mark.parametrize("who", ["student", "outsider"])
def test_non_staff_cannot_upload(upload, world, who):
    upload(user=getattr(world, who), expect=403)


def test_outsider_cannot_list(client, world, auth, upload):
    upload()
    response = client.get(f"/api/courses/{world.course.id}/documents", headers=auth(world.outsider))
    assert response.status_code == 403


def test_document_of_other_course_not_reachable_through_this_course(client, db, world, auth, upload):
    other = Course(code=f"O{uuid.uuid4().hex[:6]}", name="Other", lecturer_name="x", created_by=world.owner.id)
    db.add(other)
    db.commit()
    doc = upload(course=other)
    response = client.get(f"/api/courses/{world.course.id}/documents/{doc['id']}/file", headers=auth(world.student))
    assert response.status_code == 404


def test_only_pdf(upload):
    upload(filename="notes.txt", content=b"hello", expect=400)


def test_delete_hides_document(client, world, auth, upload):
    doc = upload()
    deleted = client.delete(f"/api/courses/{world.course.id}/documents/{doc['id']}", headers=auth(world.owner))
    assert deleted.status_code == 204
    listed = client.get(f"/api/courses/{world.course.id}/documents", headers=auth(world.owner))
    assert listed.json() == []


def test_student_cannot_delete(client, world, auth, upload):
    doc = upload()
    response = client.delete(f"/api/courses/{world.course.id}/documents/{doc['id']}", headers=auth(world.student))
    assert response.status_code == 403
