"""
Activity Logging ของหน้า home — กิจกรรมล่าสุดของคนที่ login จากตารางที่มีอยู่แล้ว (ไม่มีตารางใหม่)

นักศึกษา: lab ที่รันอยู่ (บนสุด) → ประวัติเปิด / ปิด lab (sessions) → lab ที่ทำเสร็จ (lab_progress)
อาจารย์ / admin: image สแกนผ่าน / ไม่ผ่าน → lab ที่ยังเป็น draft → จำนวนครั้งที่นักศึกษาเปิด lab วันนี้ (ต่อวิชา)

คืนเป็นข้อมูลดิบ (kind + เวลา + ตัวเลข) ให้ frontend จัดข้อความเอง จะได้แปลภาษา / รูปแบบเวลาได้ที่เดียว
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.models.courses import Course
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import Lab, LabStatus
from app.models.lab_image import ImageStatus, LabImage, ScanStatus
from app.models.lab_progress import LabProgress, ProgressStatus
from app.models.session import Session, SessionStatus
from app.models.user import User, UserRole

ACTIVE = (SessionStatus.PENDING, SessionStatus.RUNNING)


@dataclass
class Activity:
    kind: str
    at: datetime | None
    course_code: str
    title: str
    lab_id: UUID | None = None
    course_id: UUID | None = None
    detail: dict = field(default_factory=dict)


def _sort_key(item: Activity) -> datetime:
    return item.at or datetime.min.replace(tzinfo=timezone.utc)


class ActivityService:
    def __init__(self, db: DbSession):
        self.db = db

    def for_user(self, user: User, limit: int) -> list[Activity]:
        if user.role in (UserRole.INSTRUCTOR, UserRole.ADMIN):
            return self._instructor(user, limit)
        return self._student(user, limit)

    # ---------- นักศึกษา ----------
    def _student(self, user: User, limit: int) -> list[Activity]:
        rows = self.db.execute(
            select(Session, Lab, Course)
            .join(Lab, Session.lab_id == Lab.id)
            .join(Course, Lab.course_id == Course.id)
            .where(Session.user_id == user.id, Session.deleted_at.is_(None))
            .order_by(func.coalesce(Session.ended_at, Session.started_at).desc().nullsfirst())
            .limit(limit * 2)
        ).all()

        running: list[Activity] = []
        history: list[Activity] = []
        for session, lab, course in rows:
            base = dict(course_code=course.code, title=lab.title, lab_id=lab.id, course_id=course.id)
            if session.status in ACTIVE:
                running.append(Activity(
                    kind="session_running", at=session.started_at,
                    detail={"expires_at": session.expires_at, "pending": session.status == SessionStatus.PENDING},
                    **base,
                ))
                continue
            minutes = None
            if session.started_at and session.ended_at:
                minutes = max(0, int((session.ended_at - session.started_at).total_seconds() // 60))
            history.append(Activity(
                kind="session_failed" if session.status == SessionStatus.FAILED else "session_ended",
                at=session.ended_at or session.started_at,
                detail={
                    "started_at": session.started_at,
                    "minutes": minutes,
                    "end_reason": session.end_reason.value if session.end_reason else None,
                },
                **base,
            ))

        finished = self.db.execute(
            select(LabProgress, Lab, Course)
            .join(Lab, LabProgress.lab_id == Lab.id)
            .join(Course, Lab.course_id == Course.id)
            .where(LabProgress.user_id == user.id, LabProgress.status == ProgressStatus.FINISHED)
            .order_by(LabProgress.finished_at.desc().nullslast())
            .limit(limit)
        ).all()
        history += [
            Activity(kind="lab_finished", at=progress.finished_at, course_code=course.code, title=lab.title,
                     lab_id=lab.id, course_id=course.id)
            for progress, lab, course in finished
        ]

        # lab ที่รันอยู่ขึ้นก่อนเสมอ (สิ่งที่นักศึกษาต้องกลับไปทำต่อ) ที่เหลือเรียงใหม่ → เก่า
        history.sort(key=_sort_key, reverse=True)
        return (running + history)[:limit]

    # ---------- อาจารย์ / admin ----------
    def _course_ids(self, user: User) -> list[UUID]:
        query = select(Course.id).where(Course.deleted_at.is_(None))
        if user.role != UserRole.ADMIN:
            taught = select(Enrollment.course_id).where(
                Enrollment.user_id == user.id, Enrollment.role_in_course == RoleInCourse.INSTRUCTOR
            )
            query = query.where(or_(Course.created_by == user.id, Course.id.in_(taught)))
        return list(self.db.scalars(query))

    def _instructor(self, user: User, limit: int) -> list[Activity]:
        course_ids = self._course_ids(user)
        if not course_ids:
            return []
        items: list[Activity] = []

        # image ที่สแกนจบแล้ว — ผ่าน: lab ที่ผูกอยู่ publish ได้ / ไม่ผ่าน: ต้องอัปใหม่
        images = self.db.execute(
            select(LabImage, Course)
            .join(Course, LabImage.course_id == Course.id)
            .where(LabImage.course_id.in_(course_ids), LabImage.scan_status.in_([ScanStatus.PASSED, ScanStatus.FAILED]))
            .order_by(LabImage.scan_finished_at.desc().nullslast())
            .limit(limit)
        ).all()
        for image, course in images:
            passed = image.status == ImageStatus.APPROVED
            items.append(Activity(
                kind="image_passed" if passed else "image_failed", at=image.scan_finished_at,
                course_code=course.code, title=f"{image.repository}:{image.tag}", course_id=course.id,
            ))

        drafts = self.db.execute(
            select(Lab, Course)
            .join(Course, Lab.course_id == Course.id)
            .where(Lab.course_id.in_(course_ids), Lab.status == LabStatus.DRAFT, Lab.deleted_at.is_(None))
            .order_by(Lab.created_at.desc())
            .limit(limit)
        ).all()
        items += [
            Activity(kind="lab_draft", at=lab.created_at, course_code=course.code, title=lab.title,
                     lab_id=lab.id, course_id=course.id)
            for lab, course in drafts
        ]

        # นักศึกษาเปิด lab วันนี้กี่ครั้ง (ต่อวิชา) — วันตามเวลาไทย (UTC+7)
        bangkok = timezone(timedelta(hours=7))
        today = datetime.now(bangkok).replace(hour=0, minute=0, second=0, microsecond=0)
        launches = self.db.execute(
            select(Course.id, Course.code, func.count(Session.id), func.max(Session.started_at))
            .join(Lab, Lab.course_id == Course.id)
            .join(Session, Session.lab_id == Lab.id)
            .where(Course.id.in_(course_ids), Session.started_at >= today, Session.user_id != user.id)
            .group_by(Course.id, Course.code)
        ).all()
        items += [
            Activity(kind="launch_count", at=last, course_code=code, title=code, course_id=course_id,
                     detail={"count": count})
            for course_id, code, count, last in launches
        ]

        items.sort(key=_sort_key, reverse=True)
        return items[:limit]
