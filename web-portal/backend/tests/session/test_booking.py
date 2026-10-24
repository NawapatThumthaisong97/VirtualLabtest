"""
กลุ่ม 13: จองห้องแลป (หน้า /admin/scheduler) — คำขออาจารย์ → approve / reject → คาบทุกสัปดาห์ + เมล
(docs/ADMIN_MONITOR.md PR 6)
"""
import uuid
from datetime import date, time, timedelta

import pytest

from app.configs.settings import settings
from app.exceptions.domain import ConflictError, ForbiddenError, ValidationError
from app.models.booking_request import BookingRequest
from app.models.class_slot import ClassSlot
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.user import User, UserRole
from app.schemas.booking_schema import BookingCreate, ScheduleCreate, ScheduleForm
from app.services import booking_service as bs
from app.services import mail_service

ROOMS = {"LC-123": 30, "LC-207": 2}
# วันจันทร์ในอนาคต คาบจะได้ไม่ชนกับของเทสอื่น
MONDAY = date(2031, 1, 6)


@pytest.fixture
def people(db, world):
    def make(role, email_prefix):
        u = User(email=f"{email_prefix}-{uuid.uuid4().hex[:6]}@dome.tu.ac.th", name=email_prefix.title(), role=role)
        db.add(u)
        db.flush()
        return u
    teacher = make(UserRole.INSTRUCTOR, "teacher")
    db.add(Enrollment(user_id=teacher.id, course_id=world.course.id, role_in_course=RoleInCourse.INSTRUCTOR))
    admin = make(UserRole.ADMIN, "admin")
    db.commit()
    return teacher, admin


def request_body(world, **kw):
    data = dict(course_id=world.course.id, lab_id=world.k8s_lab.id, weekday=0, start_time=time(13), end_time=time(16),
                valid_from=MONDAY, valid_until=MONDAY + timedelta(weeks=3), machines=20, room="LC-123")
    data.update(kw)
    return BookingCreate(**data)


def form(world, **kw):
    data = dict(lab_id=world.k8s_lab.id, room="LC-123", machines=20, first_date=MONDAY, start_time=time(13),
                end_time=time(16), until=MONDAY + timedelta(weeks=3))
    data.update(kw)
    return ScheduleForm(**data)


class TestRequest:
    """Instructor sends a weekly booking request"""

    def test_instructor(self, db, world, people):
        """Instructor of the course -> pending"""
        item = bs.create_request(db, people[0], request_body(world))
        assert (item.status, item.course_name, item.room) == ("pending", world.course.name, "LC-123")

    def test_student_forbidden(self, db, world, people):
        """Not an instructor of the course -> 403"""
        with pytest.raises(ForbiddenError):
            bs.create_request(db, world.user, request_body(world))

    def test_lab_without_image(self, db, world, people):
        """Lab without approved image -> cannot be pre-warmed -> rejected"""
        with pytest.raises(ValidationError):
            bs.create_request(db, people[0], request_body(world, lab_id=world.no_image_lab.id))


class TestApprove:
    """Approve creates weekly slots in the room; conflicts / capacity checked"""

    def test_weekly_slots(self, db, world, people):
        """Mon 13–16 for 4 weeks -> 4 slots in LC-123, request approved, shown on calendar"""
        teacher, admin = people
        b = bs.create_request(db, teacher, request_body(world))
        item = bs.approve(db, b.id, admin, form(world), ROOMS)
        assert (item.status, item.slots_created, item.mail_status) == ("approved", 4, "pending")
        slots = db.query(ClassSlot).filter(ClassSlot.schedule_id == item.class_schedule_id).all()
        assert {s.room for s in slots} == {"LC-123"} and len(slots) == 4
        cal = bs.get_calendar(db, MONDAY.replace(day=1))
        assert [(e.date, e.start, e.end, e.room) for e in cal.events][:1] == [(MONDAY, "13:00", "16:00", "LC-123")]
        assert bs.list_requests(db).pending_count == 0

    def test_room_conflict(self, db, world, people):
        """Same room, overlapping time (other course or same) -> 409 naming the clashing class"""
        teacher, admin = people
        bs.approve(db, bs.create_request(db, teacher, request_body(world)).id, admin, form(world), ROOMS)
        second = bs.create_request(db, teacher, request_body(world))
        with pytest.raises(bs.RoomConflictError, match="LC-123|วิชาเดียวกัน"):
            bs.approve(db, second.id, admin, form(world, start_time=time(15), end_time=time(17)), ROOMS)

    def test_back_to_back_ok(self, db, world, people):
        """Next class starting exactly when the previous ends -> allowed (other room)"""
        teacher, admin = people
        bs.approve(db, bs.create_request(db, teacher, request_body(world)).id, admin, form(world), ROOMS)
        second = bs.create_request(db, teacher, request_body(world))
        item = bs.approve(db, second.id, admin, form(world, start_time=time(16), end_time=time(18)), ROOMS)
        assert item.status == "approved"

    @pytest.mark.parametrize("room,machines", [("LC-207", 3), ("LC-999", 1)])
    def test_capacity_and_unknown_room(self, db, world, people, room, machines):
        """More machines than the room has / room not in cluster -> 422"""
        teacher, admin = people
        b = bs.create_request(db, teacher, request_body(world))
        with pytest.raises(ValidationError):
            bs.approve(db, b.id, admin, form(world, room=room, machines=machines), ROOMS)

    def test_twice(self, db, world, people):
        """Already decided -> 409"""
        teacher, admin = people
        b = bs.create_request(db, teacher, request_body(world))
        bs.reject(db, b.id, admin, "ห้องเต็ม")
        with pytest.raises(ConflictError):
            bs.approve(db, b.id, admin, form(world), ROOMS)

    def test_create_direct(self, db, world, people):
        """Create new event without a request -> approved immediately"""
        item = bs.create_direct(db, people[1], ScheduleCreate(course_id=world.course.id, **form(world).model_dump()), ROOMS)
        assert (item.status, item.slots_created) == ("approved", 4)


class TestMail:
    """Decision mail to course instructors; redirect while testing"""

    def test_sent(self, db, world, people, monkeypatch):
        """Approve -> mail to instructor with room + time; mail_status sent"""
        sent = []
        monkeypatch.setattr(bs, "send_mail", lambda to, subject, body: sent.append((to, subject, body)) or True)
        teacher, admin = people
        b = bs.approve(db, bs.create_request(db, teacher, request_body(world)).id, admin, form(world), ROOMS)
        bs.send_decision_mail(b.id, db=db)
        [(to, subject, body)] = sent
        assert to == [teacher.email] and "จองห้องแลปให้แล้ว" in subject and "LC-123" in body and "13:00–16:00" in body
        assert db.get(BookingRequest, b.id).mail_status == "sent"

    def test_reject_reason_and_failure(self, db, world, people, monkeypatch):
        """Reject -> reason in mail; SMTP error -> mail_status failed, booking stays rejected"""
        def boom(to, subject, body):
            assert "ห้องเต็ม" in body
            raise OSError("smtp down")
        monkeypatch.setattr(bs, "send_mail", boom)
        teacher, admin = people
        b = bs.reject(db, bs.create_request(db, teacher, request_body(world)).id, admin, "ห้องเต็ม")
        bs.send_decision_mail(b.id, db=db)
        row = db.get(BookingRequest, b.id)
        assert (row.status, row.mail_status, row.mail_error) == ("rejected", "failed", "smtp down")

    def test_redirect(self, monkeypatch):
        """MAIL_REDIRECT_TO -> sent only there, real recipients written in the body"""
        captured = {}

        class FakeSMTP:
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self): pass
            def login(self, u, p): captured["login"] = u
            def send_message(self, msg): captured["msg"] = msg

        monkeypatch.setattr(mail_service.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(settings, "SMTP_USER", "sender@gmail.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-pass")
        monkeypatch.setattr(settings, "MAIL_REDIRECT_TO", "tester@dome.tu.ac.th")
        assert mail_service.send_mail(["real@dome.tu.ac.th"], "s", "hello") is True
        msg = captured["msg"]
        assert msg["To"] == "tester@dome.tu.ac.th" and "Virtual Lab Team" in msg["From"]
        assert "ผู้รับจริง: real@dome.tu.ac.th" in msg.get_content()

    def test_not_configured(self, monkeypatch):
        """No SMTP_USER -> not sent (skipped)"""
        monkeypatch.setattr(settings, "SMTP_USER", None)
        assert mail_service.send_mail(["a@b.c"], "s", "b") is False
