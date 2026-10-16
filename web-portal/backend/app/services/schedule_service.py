"""
Schedule Service
แปลงตารางเรียนประจำสัปดาห์ (class_schedules) เป็นรอบเรียนจริงรายวัน (class_slots)
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.exceptions.domain import ValidationError
from app.models.class_schedule import ClassSchedule
from app.models.class_slot import ClassSlot

# ตารางเรียนเป็นเวลาไทย แต่ class_slots เก็บเป็น UTC ไม่ hardcode +7 เผื่อวันหนึ่งใช้ timezone อื่น
SCHEDULE_TZ = ZoneInfo("Asia/Bangkok")


def _class_dates(schedule: ClassSchedule) -> list[date]:
    """ทุกวันตั้งแต่ valid_from ถึง valid_until (รวมทั้งสองวัน) ที่ตรงกับ weekday"""
    first = schedule.valid_from + timedelta(days=(schedule.weekday - schedule.valid_from.weekday()) % 7)
    days = []
    day = first
    while day <= schedule.valid_until:
        days.append(day)
        day += timedelta(weeks=1)
    return days


def _to_utc(day: date, t) -> datetime:
    return datetime.combine(day, t, tzinfo=SCHEDULE_TZ).astimezone(timezone.utc)


def generate_slots(db: Session, schedule: ClassSchedule) -> list[ClassSlot]:
    """สร้าง class_slots ของทุกคาบใน schedule คืนเฉพาะ slot ที่สร้างใหม่

    เรียกซ้ำได้: คาบที่มี slot อยู่แล้ว (เทียบ schedule_id + starts_at) จะข้าม รวมถึง slot ที่ถูก
    soft delete ไปแล้ว ไม่งั้นคาบที่อาจารย์ลบทิ้งจะโผล่กลับมาทุกครั้งที่ generate
    """
    if schedule.default_lab_image_id is None:
        # class_slots.lab_image_id เป็น NOT NULL ไม่รู้ image ก็ pre-warm ไม่ได้
        raise ValidationError(f"Schedule {schedule.id} has no default_lab_image_id")

    existing = {
        starts_at.astimezone(timezone.utc)
        for (starts_at,) in db.query(ClassSlot.starts_at).filter(ClassSlot.schedule_id == schedule.id)
    }

    created = []
    for day in _class_dates(schedule):
        starts_at = _to_utc(day, schedule.start_time)
        if starts_at in existing:
            continue
        created.append(ClassSlot(
            schedule_id=schedule.id,
            course_id=schedule.course_id,
            lab_image_id=schedule.default_lab_image_id,
            starts_at=starts_at,
            ends_at=_to_utc(day, schedule.end_time),
            expected_seats=schedule.expected_seats,
            created_by=schedule.created_by,
        ))

    db.add_all(created)
    db.commit()
    return created
