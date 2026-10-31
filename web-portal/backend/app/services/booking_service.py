"""
Booking Service — จองห้องแลปรายสัปดาห์ (หน้า /admin/scheduler, docs/ADMIN_MONITOR.md PR 6)

อาจารย์ส่งคำขอ (API) → admin Approve: class_schedule + class_slots ทุกสัปดาห์ถึง until (prewarm ทำงานก่อนคาบเอง)
หรือ Reject + เหตุผล → เมลแจ้งอาจารย์ของวิชา (ส่งทีหลังใน background ส่งไม่ผ่านไม่ยกเลิกการจอง)
ห้องเดียวกัน / วิชาเดียวกันเวลาทับกันไม่ได้ → 409 บอกคาบที่ชน
"""
import calendar as _calendar
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.configs.db import SessionLocal
from app.configs.settings import settings
from app.exceptions.domain import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.booking_request import BookingRequest
from app.models.class_schedule import ClassSchedule
from app.models.class_slot import ClassSlot, ClassSlotStatus
from app.models.courses import Course
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import Lab, RunTarget
from app.models.lab_image import ImageStatus, LabImage
from app.models.user import User
from app.schemas.booking_schema import (
    BookingCreate,
    BookingItem,
    BookingListResponse,
    CalendarEvent,
    CalendarResponse,
    OptionCourse,
    OptionLab,
    OptionRoom,
    ScheduleCreate,
    ScheduleForm,
    SchedulerOptions,
)
from app.services import prelaunch_service
from app.services.mail_service import send_mail
from app.services.schedule_service import SCHEDULE_TZ, _class_dates, _to_utc, generate_slots
from app.utils.logger import logger

WEEKDAY_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
TZ = ZoneInfo("Asia/Bangkok")


class RoomConflictError(ConflictError):
    code = "room_conflict"


def _role(user: User) -> str:
    return (user.role.value if hasattr(user.role, "value") else str(user.role)).lower()


def _instructors(db: DbSession, course_id: UUID) -> list[User]:
    return (
        db.query(User)
        .join(Enrollment, Enrollment.user_id == User.id)
        .filter(Enrollment.course_id == course_id, Enrollment.role_in_course == RoleInCourse.INSTRUCTOR)
        .all()
    )


def _lab_of_course(db: DbSession, lab_id: UUID, course_id: UUID) -> Lab:
    lab = db.get(Lab, lab_id)
    if lab is None or lab.course_id != course_id or lab.deleted_at is not None:
        raise ValidationError("Lab นี้ไม่อยู่ในวิชาที่เลือก")
    image = db.get(LabImage, lab.image_id) if lab.image_id else None
    if image is None or image.status != ImageStatus.APPROVED:
        raise ValidationError("Lab นี้ยังไม่มี image ที่อนุมัติแล้ว — pre-warm ไม่ได้ จองไม่ได้")
    return lab


def _enrolled_students(db: DbSession, course_id: UUID) -> int:
    return (db.query(Enrollment.user_id)
            .filter(Enrollment.course_id == course_id, Enrollment.role_in_course == RoleInCourse.STUDENT)
            .count())


def _room_and_machines(db: DbSession, course_id: UUID, mode: str, room: Optional[str],
                       machines: Optional[int], room_required: bool) -> tuple[Optional[str], int]:
    """onsite: ใช้ห้อง / จำนวนเครื่องตามฟอร์ม — online: ไม่มีห้อง เครื่อง = นักศึกษาที่ลงทะเบียนทุกคน"""
    if mode == "online":
        students = _enrolled_students(db, course_id)
        if students == 0:
            raise ValidationError("คาบ online ต้องมีนักศึกษาลงทะเบียนวิชานี้ก่อน (ระบบเปิดเครื่องให้ทุกคนที่ลงทะเบียน)")
        return None, students
    if room_required and not room:
        raise ValidationError("คาบ on-site ต้องเลือกห้อง")
    if machines is None:
        raise ValidationError("คาบ on-site ต้องระบุจำนวนเครื่อง")
    return room, machines


def _check_times(start, end, first: date, until: date) -> None:
    if end <= start:
        raise ValidationError("เวลาจบต้องหลังเวลาเริ่ม")
    if until < first:
        raise ValidationError("วันที่สิ้นสุดต้องไม่ก่อนวันเริ่ม")


def _to_item(db: DbSession, b: BookingRequest, slots_created: Optional[int] = None) -> BookingItem:
    requester = db.get(User, b.requested_by)
    course = db.get(Course, b.course_id)
    lab = db.get(Lab, b.lab_id)
    return BookingItem(
        id=b.id, status=b.status, requester_name=requester.name if requester else "-",
        requester_email=requester.email if requester else "-", course_id=b.course_id,
        course_name=course.name if course else "-", lab_id=b.lab_id, lab_title=lab.title if lab else "-",
        weekday=b.weekday, start_time=b.start_time, end_time=b.end_time, valid_from=b.valid_from,
        valid_until=b.valid_until, machines=b.machines, room=b.room, mode=b.mode, note=b.note,
        decision_note=b.decision_note,
        class_schedule_id=b.class_schedule_id, slots_created=slots_created, mail_status=b.mail_status,
        created_at=b.created_at,
    )


# ---------- อาจารย์ ----------

def create_request(db: DbSession, user: User, body: BookingCreate) -> BookingItem:
    """อาจารย์ของวิชา (หรือ admin) ส่งคำขอ → pending"""
    if _role(user) != "admin" and user.id not in {u.id for u in _instructors(db, body.course_id)}:
        raise ForbiddenError("ขอจองได้เฉพาะอาจารย์ของวิชานี้")
    _lab_of_course(db, body.lab_id, body.course_id)
    _check_times(body.start_time, body.end_time, body.valid_from, body.valid_until)
    room, machines = _room_and_machines(db, body.course_id, body.mode, body.room, body.machines,
                                        room_required=False)
    b = BookingRequest(
        requested_by=user.id, course_id=body.course_id, lab_id=body.lab_id, weekday=body.weekday,
        start_time=body.start_time, end_time=body.end_time, valid_from=body.valid_from,
        valid_until=body.valid_until, machines=machines, room=room, mode=body.mode, note=body.note,
        status="pending",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return _to_item(db, b)


def my_requests(db: DbSession, user: User) -> list[BookingItem]:
    rows = (db.query(BookingRequest).filter(BookingRequest.requested_by == user.id)
            .order_by(BookingRequest.created_at.desc()).all())
    return [_to_item(db, b) for b in rows]


# ---------- admin ----------

def list_requests(db: DbSession, status: Optional[str] = "pending") -> BookingListResponse:
    q = db.query(BookingRequest)
    if status:
        q = q.filter(BookingRequest.status == status)
    rows = q.order_by(BookingRequest.created_at).all()
    pending = db.query(BookingRequest).filter(BookingRequest.status == "pending").count()
    return BookingListResponse(items=[_to_item(db, b) for b in rows], pending_count=pending)


def _get(db: DbSession, booking_id: UUID) -> BookingRequest:
    b = db.get(BookingRequest, booking_id)
    if b is None:
        raise NotFoundError("ไม่พบคำขอจอง")
    return b


def _conflicts(db: DbSession, room: Optional[str], course_id: UUID,
               times: list[tuple[datetime, datetime]]) -> Optional[str]:
    """คาบแรกที่ชน (ห้องเดียวกัน หรือวิชาเดียวกัน) เป็นข้อความ — ไม่ชน = None

    room = None (คาบ online) เช็กแค่วิชาเดียวกัน — ห้ามเทียบ room == None เพราะจะชนกับทุกคาบที่ไม่มีห้อง
    """
    if not times:
        return None
    start, end = min(t[0] for t in times), max(t[1] for t in times)
    same = ClassSlot.course_id == course_id
    if room is not None:
        same = same | (ClassSlot.room == room)
    existing = (
        db.query(ClassSlot, Course)
        .join(Course, ClassSlot.course_id == Course.id)
        .filter(ClassSlot.deleted_at.is_(None), ClassSlot.status != ClassSlotStatus.CANCELLED,
                ClassSlot.starts_at < end, ClassSlot.ends_at > start, same)
        .all()
    )
    for slot, course in existing:
        for s, e in times:
            if slot.starts_at < e and slot.ends_at > s:
                where = f"ห้อง {slot.room}" if room is not None and slot.room == room else "วิชาเดียวกัน"
                local = slot.starts_at.astimezone(TZ)
                return (f"{where} มีคาบ {course.name} วัน{WEEKDAY_TH[local.weekday()]} "
                        f"{local:%d/%m/%Y %H:%M}–{slot.ends_at.astimezone(TZ):%H:%M} อยู่แล้ว")
    return None


def _schedule(db: DbSession, b: BookingRequest, admin: User, form: ScheduleForm,
              room_capacity: Optional[dict[str, int]]) -> int:
    """สร้าง class_schedule + slots ให้คำขอ b (commit) คืนจำนวนคาบ"""
    lab = _lab_of_course(db, form.lab_id, b.course_id)
    _check_times(form.start_time, form.end_time, form.first_date, form.until)
    room, machines = _room_and_machines(db, b.course_id, form.mode, form.room, form.machines,
                                        room_required=True)
    if room is not None and room_capacity is not None:
        if room not in room_capacity:
            raise ValidationError(f"ไม่มีห้อง {room} (ห้องที่มี: {', '.join(sorted(room_capacity)) or '-'})")
        if machines > room_capacity[room]:
            raise ValidationError(f"ห้อง {room} มี {room_capacity[room]} เครื่อง ขอ {machines}")

    schedule = ClassSchedule(
        course_id=b.course_id, weekday=form.first_date.weekday(), start_time=form.start_time,
        end_time=form.end_time, valid_from=form.first_date, valid_until=form.until,
        default_lab_image_id=lab.image_id, expected_seats=machines, created_by=admin.id, room=room,
        mode=form.mode,
    )
    times = [(_to_utc(d, form.start_time), _to_utc(d, form.end_time)) for d in _class_dates(schedule)]
    if not times:
        raise ValidationError("ช่วงวันที่ไม่มีวันที่ตรงกับวันในสัปดาห์ที่เลือก")
    conflict = _conflicts(db, room, b.course_id, times)
    if conflict:
        raise RoomConflictError(conflict)

    b.lab_id, b.room, b.machines, b.mode = form.lab_id, room, machines, form.mode
    b.weekday, b.start_time, b.end_time = schedule.weekday, form.start_time, form.end_time
    b.valid_from, b.valid_until = form.first_date, form.until
    b.status, b.decided_by, b.decided_at = "approved", admin.id, datetime.now(timezone.utc)
    b.decision_note, b.mail_status = form.note, "pending"
    db.add(schedule)
    try:
        db.flush()
        b.class_schedule_id = schedule.id
        slots = generate_slots(db, schedule)   # commit ทั้ง schedule + slots + สถานะคำขอ
        for slot in slots:
            slot.lab_id = lab.id
        db.commit()
    except IntegrityError as e:
        # ชนพร้อมกันกับคนอื่น (เช็กข้างบนแล้วแต่ยังแข่งกันได้) — exclusion constraint กันไว้
        db.rollback()
        raise RoomConflictError(f"ห้อง {room or '-'} หรือวิชานี้มีคาบเวลาทับกัน: {e.orig}") from e
    return len(slots)


def approve(db: DbSession, booking_id: UUID, admin: User, form: ScheduleForm,
            room_capacity: Optional[dict[str, int]]) -> BookingItem:
    b = _get(db, booking_id)
    if b.status != "pending":
        raise ConflictError(f"คำขอนี้ {b.status} ไปแล้ว")
    count = _schedule(db, b, admin, form, room_capacity)
    return _to_item(db, b, slots_created=count)


def reject(db: DbSession, booking_id: UUID, admin: User, reason: str) -> BookingItem:
    b = _get(db, booking_id)
    if b.status != "pending":
        raise ConflictError(f"คำขอนี้ {b.status} ไปแล้ว")
    b.status, b.decided_by, b.decided_at = "rejected", admin.id, datetime.now(timezone.utc)
    b.decision_note, b.mail_status = reason, "pending"
    db.commit()
    return _to_item(db, b)


def create_direct(db: DbSession, admin: User, form: ScheduleCreate,
                  room_capacity: Optional[dict[str, int]]) -> BookingItem:
    """Create new event: admin สร้างเอง = คำขอที่ approved ทันที (เก็บประวัติเหมือนคำขอ + ส่งเมลถึงอาจารย์)"""
    if db.get(Course, form.course_id) is None:
        raise NotFoundError("ไม่พบวิชา")
    # machines / room จริงตั้งใน _schedule (online นับนักศึกษาเอง) ตรงนี้ใส่ไว้ให้ผ่าน NOT NULL ก่อน
    b = BookingRequest(
        requested_by=admin.id, course_id=form.course_id, lab_id=form.lab_id, weekday=form.first_date.weekday(),
        start_time=form.start_time, end_time=form.end_time, valid_from=form.first_date, valid_until=form.until,
        machines=form.machines or 1, room=form.room, mode=form.mode, status="pending",
    )
    db.add(b)
    db.flush()
    try:
        count = _schedule(db, b, admin, form, room_capacity)
    except Exception:
        db.rollback()
        raise
    return _to_item(db, b, slots_created=count)


def cancel_slot(db: DbSession, slot_id: UUID, admin: User) -> dict:
    """ยกเลิกคาบ 1 คาบ (เช่นสร้างผิดเวลา) → CANCELLED: scheduler ไม่สนใจ ไม่นับว่าชนเวลา ไม่ขึ้นปฏิทิน

    คาบ online ที่เปิดเครื่องรอไว้แล้ว: เครื่องที่ยังไม่มีคนรับ → คืนเครื่องทันที (เครื่องที่นักศึกษารับไปแล้วไม่แตะ)
    """
    slot = db.get(ClassSlot, slot_id)
    if slot is None or slot.deleted_at is not None:
        raise NotFoundError("ไม่พบคาบนี้")
    if slot.status in (ClassSlotStatus.CANCELLED, ClassSlotStatus.DONE):
        raise ConflictError(f"คาบนี้ {slot.status.name} ไปแล้ว")
    slot.status = ClassSlotStatus.CANCELLED
    note = f"ยกเลิกโดย {admin.email} {datetime.now(TZ):%d/%m/%Y %H:%M}"
    slot.note = f"{slot.note}\n{note}" if slot.note else note
    db.commit()
    released = prelaunch_service.release_unclaimed(db, slot.id)
    logger.info(f"[booking] slot {slot.id} cancelled by {admin.email}, released {released}")
    return {"slotId": str(slot.id), "status": slot.status.value, "released": released}


# ---------- เมล ----------

def _mail_text(db: DbSession, b: BookingRequest) -> tuple[str, str]:
    course = db.get(Course, b.course_id)
    lab = db.get(Lab, b.lab_id)
    when = (f"ทุกวัน{WEEKDAY_TH[b.weekday]} {b.start_time:%H:%M}–{b.end_time:%H:%M} น. "
            f"ตั้งแต่ {b.valid_from:%d/%m/%Y} ถึง {b.valid_until:%d/%m/%Y}")
    head = f"วิชา: {course.name if course else '-'}\nLab: {lab.title if lab else '-'}\nเวลา: {when}\n"
    if b.status == "approved":
        subject = f"[Virtual Lab] จองห้องแลปให้แล้ว — {course.name if course else ''}"
        if b.mode == "online":
            where = f"รูปแบบ: online (ไม่ใช้ห้อง)\nจำนวนเครื่อง: {b.machines} (นักศึกษาที่ลงทะเบียนทุกคน)\n"
            prepare = ("ระบบจะเปิดเครื่องบน AWS รอไว้ให้นักศึกษาทุกคนก่อนเริ่มคาบประมาณ "
                       f"{settings.PRELAUNCH_LEAD_MINUTES} นาที นักศึกษาที่ไม่กด Start ภายใน "
                       f"{settings.PRELAUNCH_CLAIM_MINUTES} นาทีหลังเริ่มคาบ ระบบจะคืนเครื่อง "
                       "(กดทีหลังได้ แต่ต้องรอเปิดเครื่องใหม่ราว 2 นาที)")
        else:
            where = f"ห้อง: {b.room}\nจำนวนเครื่อง: {b.machines}\n"
            prepare = "ระบบจะเตรียม lab ลงเครื่องในห้องให้ก่อนเริ่มคาบประมาณ 30 นาที"
        body = (f"เรียน อาจารย์\n\nVirtual Lab Team จองคาบให้แล้วครับ\n\n{head}{where}"
                + (f"หมายเหตุ: {b.decision_note}\n" if b.decision_note else "")
                + f"\n{prepare}\n\nVirtual Lab Team")
    else:
        subject = f"[Virtual Lab] ไม่สามารถจองห้องแลปได้ — {course.name if course else ''}"
        body = (f"เรียน อาจารย์\n\nขออภัยครับ คำขอจองห้องแลปไม่ได้รับการอนุมัติ\n\n{head}"
                f"เหตุผล: {b.decision_note}\n\nVirtual Lab Team")
    return subject, body


def send_decision_mail(booking_id: UUID, db: Optional[DbSession] = None) -> None:
    """ส่งเมลแจ้งผลถึงอาจารย์ของวิชา + ผู้ขอ บันทึก mail_status (background task ไม่ส่ง db = เปิด session เอง)"""
    own = db is None
    db = db or SessionLocal()
    try:
        b = db.get(BookingRequest, booking_id)
        if b is None:
            return
        to = {u.email for u in _instructors(db, b.course_id)}
        requester = db.get(User, b.requested_by)
        if requester and _role(requester) != "admin":
            to.add(requester.email)
        subject, body = _mail_text(db, b)
        try:
            b.mail_status = "sent" if send_mail(sorted(to), subject, body) else "skipped"
            b.mail_error = None
        except Exception as e:
            logger.warning(f"[booking] mail failed for {booking_id}: {e}")
            b.mail_status, b.mail_error = "failed", str(e)[:1000]
        db.commit()
    finally:
        if own:
            db.close()


# ---------- ปฏิทิน / ตัวเลือก ----------

def get_calendar(db: DbSession, month: date) -> CalendarResponse:
    """คาบทั้งเดือน (เวลาไทย) สำหรับปฏิทิน — title = วิชา – lab"""
    first = datetime(month.year, month.month, 1, tzinfo=SCHEDULE_TZ)
    end = first + timedelta(days=_calendar.monthrange(month.year, month.month)[1])
    rows = (
        db.query(ClassSlot, Course, Lab)
        .join(Course, ClassSlot.course_id == Course.id)
        .outerjoin(Lab, ClassSlot.lab_id == Lab.id)
        .filter(ClassSlot.deleted_at.is_(None), ClassSlot.status != ClassSlotStatus.CANCELLED,
                ClassSlot.starts_at >= first.astimezone(timezone.utc), ClassSlot.starts_at < end.astimezone(timezone.utc))
        .order_by(ClassSlot.starts_at)
        .all()
    )
    events = []
    for slot, course, lab in rows:
        s, e = slot.starts_at.astimezone(TZ), slot.ends_at.astimezone(TZ)
        events.append(CalendarEvent(
            id=slot.id, title=f"{course.name} – {lab.title}" if lab else course.name, date=s.date(),
            start=f"{s:%H:%M}", end=f"{e:%H:%M}", room=slot.room, course_id=course.id, course_name=course.name,
            machines=slot.expected_seats, status=slot.status.value,
            mode="online" if slot.run_target == RunTarget.AWS else "onsite",
        ))
    return CalendarResponse(month=f"{month.year:04d}-{month.month:02d}", events=events)


def get_options(db: DbSession, room_capacity: Optional[dict[str, int]]) -> SchedulerOptions:
    courses = db.query(Course).order_by(Course.name).all()
    labs = db.query(Lab).filter(Lab.deleted_at.is_(None)).order_by(Lab.course_id, Lab.order_no).all()
    approved = {i.id for i in db.query(LabImage.id).filter(LabImage.status == ImageStatus.APPROVED)}
    return SchedulerOptions(
        courses=[OptionCourse(id=c.id, code=c.code, name=c.name,
                              instructors=[u.name for u in _instructors(db, c.id)]) for c in courses],
        labs=[OptionLab(id=lab.id, course_id=lab.course_id, title=lab.title, has_image=lab.image_id in approved)
              for lab in labs],
        rooms=[OptionRoom(room=r, pcs_total=n) for r, n in sorted((room_capacity or {}).items())],
    )
