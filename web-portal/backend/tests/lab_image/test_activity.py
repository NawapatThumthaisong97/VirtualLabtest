"""
GET /api/v1/me/activity — กล่อง Activity Logging หน้า home

นักศึกษา: lab ที่รันอยู่ขึ้นก่อน แล้วตามด้วยประวัติ / lab ที่ทำเสร็จ เรียงใหม่ → เก่า, เห็นแต่ของตัวเอง
อาจารย์: image สแกนผ่าน / ไม่ผ่าน, lab draft, จำนวนครั้งที่นักศึกษาเปิด lab วันนี้ — เฉพาะวิชาที่สอน
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.lab import Lab, LabStatus
from app.models.lab_image import ImageStatus, LabImage, ScanStatus
from app.models.lab_progress import LabProgress, ProgressStatus
from app.models.session import ServiceType, Session, SessionEndReason, SessionStatus

NOW = datetime.now(timezone.utc)


@pytest.fixture
def lab(db, world):
    def _make(title="Lab A", status=LabStatus.PUBLISHED, course=None):
        row = Lab(course_id=(course or world.course).id, title=title, order_no=len(title) + int(uuid.uuid4().int % 1000), status=status)
        db.add(row)
        db.commit()
        return row
    return _make


def session(db, user, lab, status, started, ended=None, reason=None):
    db.add(Session(
        user_id=user.id, lab_id=lab.id, service_type=ServiceType.LAB, status=status,
        started_at=started, ended_at=ended, end_reason=reason, expires_at=started + timedelta(hours=2),
    ))
    db.commit()


def activity(client, auth, user, limit=10):
    response = client.get(f"/api/v1/me/activity?limit={limit}", headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_student_running_first_then_newest(client, db, world, auth, lab):
    a, b, c = lab("Old"), lab("Running"), lab("Done")
    session(db, world.student, a, SessionStatus.STOPPED, NOW - timedelta(hours=5), NOW - timedelta(hours=4), SessionEndReason.USER_DELETE)
    session(db, world.student, b, SessionStatus.RUNNING, NOW - timedelta(hours=6))
    db.add(LabProgress(user_id=world.student.id, lab_id=c.id, status=ProgressStatus.FINISHED, finished_at=NOW - timedelta(hours=1)))
    db.commit()

    items = activity(client, auth, world.student)
    assert [(i["kind"], i["title"]) for i in items] == [
        ("session_running", "Running"), ("lab_finished", "Done"), ("session_ended", "Old"),
    ]
    assert items[2]["detail"]["minutes"] == 60
    assert items[2]["detail"]["end_reason"] == "user_delete"
    assert items[0]["courseCode"] == world.course.code


def test_student_failed_launch_and_limit(client, db, world, auth, lab):
    for n in range(4):
        session(db, world.student, lab(f"L{n}"), SessionStatus.FAILED, NOW - timedelta(minutes=n), NOW - timedelta(minutes=n),
                SessionEndReason.LAUNCH_FAILED)
    items = activity(client, auth, world.student, limit=3)
    assert len(items) == 3 and {i["kind"] for i in items} == {"session_failed"}


def test_student_sees_only_own_sessions(client, db, world, auth, lab):
    session(db, world.co_instructor, lab("Someone else"), SessionStatus.RUNNING, NOW)
    assert activity(client, auth, world.student) == []


def test_instructor_feed_for_taught_courses(client, db, world, auth, lab):
    lab("Draft one", status=LabStatus.DRAFT)
    db.add(LabImage(
        id=uuid.uuid4(), uploaded_by=world.owner.id, course_id=world.course.id, repository="vlab/act", tag="v1", size_mb=1,
        status=ImageStatus.APPROVED, scan_status=ScanStatus.PASSED, scan_finished_at=NOW, exposed_ports=[8443],
        archive_key=f"lab-images/{uuid.uuid4().hex}.tar",
    ))
    db.commit()
    published = lab("Open lab")
    session(db, world.student, published, SessionStatus.RUNNING, NOW - timedelta(minutes=5))

    kinds = {i["kind"]: i for i in activity(client, auth, world.owner)}
    assert kinds["image_passed"]["title"] == "vlab/act:v1"
    assert kinds["lab_draft"]["title"] == "Draft one"
    assert kinds["launch_count"]["detail"]["count"] == 1
    assert activity(client, auth, world.outsider) == []


def test_default_limit_is_two(client, db, world, auth, lab):
    for n in range(5):
        lab(f"Draft {n}", status=LabStatus.DRAFT)
    response = client.get("/api/v1/me/activity", headers=auth(world.owner))
    assert len(response.json()["data"]) == 2
