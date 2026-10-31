"""
Prelaunch Service — คาบ online: เปิด EC2 รอไว้ให้นักศึกษาทุกคนที่ลงทะเบียนก่อนคาบ (docs/AWS_PRELAUNCH.md)

prewarm scheduler เรียก sync_prelaunch ทุกรอบ (PRELAUNCH_ENABLED) ทำ 2 อย่าง
1. slot online (run_target AWS) ที่จะเริ่มใน PRELAUNCH_LEAD_MINUTES: นักศึกษาที่ยังไม่มีเครื่อง → สร้าง record PENDING
   แล้ว launch ใน thread (launch 1 เครื่องใช้ ~1.5–2 นาที รอใน scheduler ไม่ได้) ไม่เกิน PRELAUNCH_MAX_PARALLEL
2. เครื่องที่เปิดรอไว้แต่ไม่มีใครรับภายใน PRELAUNCH_CLAIM_MINUTES หลังคาบเริ่ม → STOPPED / PRELAUNCH_UNCLAIMED + sky down

นักศึกษามารับเครื่องที่ SessionService.create_session (claimed_at) — ไฟล์นี้ไม่ยุ่งกับเครื่องที่รับแล้ว
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DbSession, joinedload

from app.configs.db import SessionLocal
from app.configs.settings import settings
from app.models.class_slot import ClassSlot, ClassSlotStatus
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import Lab, RunTarget
from app.models.lab_image import LabImage
from app.models.session import Session as SessionModel, SessionEndReason, SessionStatus
from app.repositories.lab_image_repository import LabImageRepository
from app.repositories.lab_repository import LabRepository
from app.repositories.session_repository import SessionRepository
from app.services import admin_billing_service, session_service
from app.utils.logger import logger

LIVE_STATUSES = (ClassSlotStatus.SCHEDULED, ClassSlotStatus.PREWARMING, ClassSlotStatus.READY)
ACTIVE = (SessionStatus.PENDING, SessionStatus.RUNNING)

# งานยาว (launch / down) วิ่งใน thread ของ pool นี้ ไม่ใช่ใน thread ของ scheduler
_executor: Optional[ThreadPoolExecutor] = None


def _run_in_background(fn: Callable[[], None]) -> None:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=max(1, settings.PRELAUNCH_MAX_PARALLEL),
                                       thread_name_prefix="prelaunch")
    _executor.submit(fn)


def safety_minutes() -> int:
    """autostop ของเครื่องที่ยังไม่มีคนรับ: ถ้า backend ตาย เครื่องลบตัวเองหลังเลยเวลารับไปแล้ว 5 นาที"""
    return settings.PRELAUNCH_LEAD_MINUTES + settings.PRELAUNCH_CLAIM_MINUTES + 5


def _service(db: DbSession) -> "session_service.SessionService":
    return session_service.SessionService(db, SessionRepository(db), LabRepository(db), LabImageRepository(db))


def launch_slots(db: DbSession, now: datetime) -> list[ClassSlot]:
    """slot online ที่อยู่ในช่วงเปิดเครื่องรอ: starts_at - lead <= now < starts_at"""
    lead = timedelta(minutes=settings.PRELAUNCH_LEAD_MINUTES)
    return (
        db.query(ClassSlot)
        .options(joinedload(ClassSlot.lab_image))
        .filter(
            ClassSlot.deleted_at.is_(None),
            ClassSlot.status.in_(LIVE_STATUSES),
            ClassSlot.run_target == RunTarget.AWS,
            ClassSlot.starts_at <= now + lead,
            ClassSlot.starts_at > now,
        )
        .all()
    )


def _students(db: DbSession, course_id: UUID) -> list[UUID]:
    return [uid for (uid,) in db.query(Enrollment.user_id).filter(
        Enrollment.course_id == course_id, Enrollment.role_in_course == RoleInCourse.STUDENT)]


def _covered_users(db: DbSession, slot: ClassSlot) -> set[UUID]:
    """คนที่ไม่ต้องเปิดเครื่องให้แล้ว: มีเครื่องเปิดอยู่ / กำลังเปิดของ lab นี้ หรือเคยรับเครื่องของคาบนี้ไปแล้ว"""
    active = db.query(SessionModel.user_id).filter(
        SessionModel.lab_id == slot.lab_id,
        SessionModel.status.in_(ACTIVE),
        SessionModel.deleted_at.is_(None),
    )
    claimed = db.query(SessionModel.user_id).filter(
        SessionModel.class_slot_id == slot.id,
        SessionModel.claimed_at.isnot(None),
    )
    return {uid for (uid,) in active} | {uid for (uid,) in claimed}


def _inflight(db: DbSession) -> int:
    return db.query(SessionModel).filter(
        SessionModel.prelaunched_at.isnot(None),
        SessionModel.status == SessionStatus.PENDING,
        SessionModel.deleted_at.is_(None),
    ).count()


def _launch_job(session_id: UUID, task, lab_image_id: UUID) -> Callable[[], None]:
    """งานใน thread: launch เครื่องของ record ที่สร้างไว้แล้ว (DB session แยกของ thread เอง)"""
    def run() -> None:
        db = SessionLocal()
        try:
            session = db.get(SessionModel, session_id)
            lab_image = db.get(LabImage, lab_image_id)
            _service(db)._run_sky_launch(session, task, lab_image, lifetime_minutes=safety_minutes())
            logger.info(f"[prelaunch] ready {session.sky_cluster_name} for user {session.user_id}")
        except Exception as e:
            # _run_sky_launch ตั้ง FAILED + down ให้แล้ว รอบหน้า scheduler จะเปิดให้ใหม่ (ถ้ายังไม่ถึงเวลาเริ่มคาบ)
            logger.warning(f"[prelaunch] launch failed for session {session_id}: {e}")
        finally:
            db.close()
    return run


def _down_job(cluster_name: str) -> Callable[[], None]:
    def run() -> None:
        try:
            sky = session_service.sky
            session_service.sky_call(lambda: sky.get(sky.down(cluster_name)))
        except Exception as e:
            # ลบไม่ได้ก็ไม่เป็นไรมาก autostop (safety_minutes) จะลบเองอยู่ดี
            logger.warning(f"[prelaunch] cannot down unclaimed {cluster_name}: {e}")
    return run


def _expire_unclaimed(db: DbSession, now: datetime, background: Callable, result: dict) -> None:
    """คาบเริ่มไปแล้วเกิน PRELAUNCH_CLAIM_MINUTES → เครื่องที่ยังไม่มีคนรับ คืนเครื่อง

    PENDING (ยัง launch ไม่เสร็จ) ข้ามไปก่อน รอบถัดไปค่อยจัดการตอนเป็น RUNNING
    ไม่งั้น thread ที่ launch อยู่จะเขียนทับเป็น RUNNING ทีหลัง
    """
    deadline = now - timedelta(minutes=settings.PRELAUNCH_CLAIM_MINUTES)
    rows = (
        db.query(SessionModel)
        .join(ClassSlot, SessionModel.class_slot_id == ClassSlot.id)
        .filter(
            SessionModel.prelaunched_at.isnot(None),
            SessionModel.claimed_at.is_(None),
            SessionModel.status == SessionStatus.RUNNING,
            SessionModel.deleted_at.is_(None),
            ClassSlot.starts_at <= deadline,
        )
        .all()
    )
    svc = _service(db)
    for session in rows:
        svc._end_session(session, SessionStatus.STOPPED, SessionEndReason.PRELAUNCH_UNCLAIMED)
        background(_down_job(session.sky_cluster_name))
        result["expired"].append(session.sky_cluster_name)


def _move(slot: ClassSlot, status: ClassSlotStatus, changed: dict) -> None:
    if slot.status != status:
        changed[str(slot.id)] = f"{slot.status.name} -> {status.name}"
        slot.status = status


def sync_prelaunch(db: DbSession, now: Optional[datetime] = None,
                   background: Callable[[Callable[[], None]], None] = _run_in_background) -> dict:
    """1 รอบของคาบ online: คืนเครื่องที่หมดเวลารับ แล้วเปิดเครื่องที่ยังขาด

    background = ที่รันงานยาว (เทสส่งตัวที่รันทันทีมาแทน thread pool)
    """
    now = now or datetime.now(timezone.utc)
    result: dict = {"launched": [], "expired": [], "errors": [], "slots": {}}

    _expire_unclaimed(db, now, background, result)

    slots = launch_slots(db, now)
    if slots and not admin_billing_service.is_burst_enabled(db):
        # admin ปิด burst (เช่นใช้เกิน budget) → ไม่เปิดเครื่องรอ นักศึกษากด Start เองจะเจอข้อความเดียวกัน
        result["errors"].append("cloud burst disabled")
        slots = []

    budget = max(0, settings.PRELAUNCH_MAX_PARALLEL - _inflight(db))
    svc = _service(db)
    for slot in slots:
        lab = db.get(Lab, slot.lab_id) if slot.lab_id else None
        if lab is None or slot.lab_image is None:
            result["errors"].append(f"slot {slot.id}: no lab / image")
            continue
        students = _students(db, slot.course_id)
        missing = [uid for uid in students if uid not in _covered_users(db, slot)]
        for user_id in missing:
            if budget <= 0:
                break
            try:
                session, task = svc._new_sky_session(
                    user_id, lab, slot.lab_image, RunTarget.AWS, None,
                    class_slot_id=slot.id, prelaunched_at=now, autostop_minutes=safety_minutes())
            except Exception as e:
                # เช่นขอ ECR token ไม่ได้ — คนถัดไปก็จะพังแบบเดียวกัน รอรอบหน้า
                result["errors"].append(f"slot {slot.id}: {e}")
                break
            background(_launch_job(session.id, task, slot.lab_image.id))
            result["launched"].append(session.sky_cluster_name)
            budget -= 1

        ready = db.query(SessionModel).filter(
            SessionModel.class_slot_id == slot.id,
            SessionModel.prelaunched_at.isnot(None),
            SessionModel.status == SessionStatus.RUNNING,
        ).count()
        _move(slot, ClassSlotStatus.READY if students and ready >= len(students) else ClassSlotStatus.PREWARMING,
              result["slots"])

    # คาบ online ที่จบแล้ว (prewarm scheduler ทำให้แค่ตอนเปิด PREWARM_ENABLED)
    for slot in db.query(ClassSlot).filter(
        ClassSlot.deleted_at.is_(None),
        ClassSlot.status.in_(LIVE_STATUSES),
        ClassSlot.run_target == RunTarget.AWS,
        ClassSlot.ends_at <= now,
    ):
        _move(slot, ClassSlotStatus.DONE, result["slots"])
    db.commit()
    return result
