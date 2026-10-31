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
from app.models.lab import RunTarget
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


class TestOnlineMode:
    """Online class: no room, one machine per enrolled student, slots run on AWS"""

    def test_request_counts_students(self, db, world, people):
        """Online request ignores room / machines from the form -> machines = enrolled students"""
        item = bs.create_request(db, people[0], request_body(world, mode="online", room="LC-123", machines=99))
        assert (item.mode, item.room, item.machines) == ("online", None, 1)

    def test_approve_online_slots_are_aws(self, db, world, people):
        """Approve online -> weekly slots without a room, run_target AWS, calendar says online"""
        teacher, admin = people
        b = bs.create_request(db, teacher, request_body(world, mode="online"))
        item = bs.approve(db, b.id, admin, form(world, mode="online", room=None, machines=None), ROOMS)
        slots = db.query(ClassSlot).filter(ClassSlot.schedule_id == item.class_schedule_id).all()
        assert len(slots) == 4
        assert {(s.room, s.run_target, s.expected_seats) for s in slots} == {(None, RunTarget.AWS, 1)}
        assert {e.mode for e in bs.get_calendar(db, MONDAY.replace(day=1)).events} == {"online"}

    def test_onsite_slots_stay_kubernetes(self, db, world, people):
        """On-site (default) -> run_target KUBERNETES as before"""
        item = bs.create_direct(db, people[1], ScheduleCreate(course_id=world.course.id, **form(world).model_dump()), ROOMS)
        slots = db.query(ClassSlot).filter(ClassSlot.schedule_id == item.class_schedule_id).all()
        assert item.mode == "onsite" and {s.run_target for s in slots} == {RunTarget.KUBERNETES}

    def test_online_same_course_still_conflicts(self, db, world, people):
        """Online class overlapping another class of the same course -> 409 (no room, but course check stays)"""
        teacher, admin = people
        onsite = bs.create_direct(db, admin, ScheduleCreate(course_id=world.course.id, **form(world).model_dump()), ROOMS)
        assert onsite.status == "approved"
        with pytest.raises(bs.RoomConflictError, match="วิชาเดียวกัน"):
            bs.create_direct(db, admin, ScheduleCreate(course_id=world.course.id,
                                                        **form(world, mode="online", room=None).model_dump()), ROOMS)

    def test_online_needs_students(self, db, world, people):
        """No enrolled students -> online class rejected (nothing to pre-launch)"""
        db.query(Enrollment).filter(Enrollment.course_id == world.course.id,
                                    Enrollment.role_in_course == RoleInCourse.STUDENT).delete()
        db.commit()
        with pytest.raises(ValidationError, match="online"):
            bs.create_request(db, people[0], request_body(world, mode="online"))

    def test_onsite_needs_room(self, db, world, people):
        """On-site approve without a room -> 422"""
        teacher, admin = people
        b = bs.create_request(db, teacher, request_body(world))
        with pytest.raises(ValidationError, match="ห้อง"):
            bs.approve(db, b.id, admin, form(world, room=None), ROOMS)

    def test_online_mail(self, db, world, people):
        """Approval mail for online class says online and when machines are released"""
        teacher, admin = people
        b = bs.create_request(db, teacher, request_body(world, mode="online"))
        bs.approve(db, b.id, admin, form(world, mode="online", room=None, machines=None), ROOMS)
        subject, body = bs._mail_text(db, db.get(BookingRequest, b.id))
        assert "online" in body and "LC-123" not in body and "คืนเครื่อง" in body


class TestCancelSlot:
    """Admin cancels one class (e.g. created at the wrong time)"""

    def _slot(self, db, item):
        return db.query(ClassSlot).filter(ClassSlot.schedule_id == item.class_schedule_id).order_by(ClassSlot.starts_at).first()

    def test_cancel(self, db, world, people):
        """Cancelled -> CANCELLED, gone from calendar, the same time can be booked again"""
        admin = people[1]
        item = bs.create_direct(db, admin, ScheduleCreate(course_id=world.course.id, **form(world, until=MONDAY).model_dump()), ROOMS)
        slot = self._slot(db, item)
        result = bs.cancel_slot(db, slot.id, admin)

        assert result["status"] == "cancelled" and result["released"] == []
        assert admin.email in slot.note
        assert bs.get_calendar(db, MONDAY.replace(day=1)).events == []
        again = bs.create_direct(db, admin, ScheduleCreate(course_id=world.course.id, **form(world, until=MONDAY).model_dump()), ROOMS)
        assert again.status == "approved"

    def test_twice_and_unknown(self, db, world, people):
        """Cancel twice -> 409, unknown slot -> 404"""
        from app.exceptions.domain import NotFoundError
        admin = people[1]
        item = bs.create_direct(db, admin, ScheduleCreate(course_id=world.course.id, **form(world, until=MONDAY).model_dump()), ROOMS)
        slot = self._slot(db, item)
        bs.cancel_slot(db, slot.id, admin)
        with pytest.raises(ConflictError):
            bs.cancel_slot(db, slot.id, admin)
        with pytest.raises(NotFoundError):
            bs.cancel_slot(db, uuid.uuid4(), admin)


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


class TestAllowList:
    """MAIL_ALLOWED_RECIPIENTS: never mail someone not on the list, even without redirect"""

    @pytest.fixture
    def smtp(self, monkeypatch):
        sent = []

        class FakeSMTP:
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self): pass
            def login(self, u, p): pass
            def send_message(self, msg): sent.append(msg["To"])

        monkeypatch.setattr(mail_service.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(settings, "SMTP_USER", "sender@gmail.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-pass")
        monkeypatch.setattr(settings, "MAIL_REDIRECT_TO", None)
        return sent

    def test_empty_list_sends_nobody(self, smtp, monkeypatch):
        """No redirect + empty allow list -> nothing sent, error (mail_status failed)"""
        monkeypatch.setattr(settings, "MAIL_ALLOWED_RECIPIENTS", "")
        with pytest.raises(ValueError, match="no allowed recipient"):
            mail_service.send_mail(["kittipong.som@dome.tu.ac.th"], "s", "b")
        assert smtp == []

    def test_only_listed(self, smtp, monkeypatch):
        """Exact address and @domain rules; others dropped"""
        monkeypatch.setattr(settings, "MAIL_ALLOWED_RECIPIENTS", "peraphat.ekd@dome.tu.ac.th, @staff.example.com")
        mail_service.send_mail(["peraphat.ekd@dome.tu.ac.th", "kittipong.som@dome.tu.ac.th", "a@staff.example.com"], "s", "b")
        assert smtp == ["peraphat.ekd@dome.tu.ac.th, a@staff.example.com"]

    def test_star_and_redirect(self, smtp, monkeypatch):
        """'*' allows everyone; redirect target always allowed"""
        monkeypatch.setattr(settings, "MAIL_ALLOWED_RECIPIENTS", "*")
        mail_service.send_mail(["x@y.z"], "s", "b")
        monkeypatch.setattr(settings, "MAIL_ALLOWED_RECIPIENTS", "")
        monkeypatch.setattr(settings, "MAIL_REDIRECT_TO", "tester@dome.tu.ac.th")
        mail_service.send_mail(["kittipong.som@dome.tu.ac.th"], "s", "b")
        assert smtp == ["x@y.z", "tester@dome.tu.ac.th"]
