"""
Prewarm Scheduler
งานพื้นหลังที่ทำให้ DaemonSet pre-pull ตรงกับคาบเรียนที่กำลังจะเริ่มหรือกำลังเรียนอยู่

ทุกรอบ:
1. รวม image ที่ต้องมีบนทุก worker ตอนนี้ (desired) จาก
   - class_slots ที่ starts_at - PREWARM_LEAD_MINUTES <= now < ends_at (เฉพาะ run_target KUBERNETES)
   - settings.PREWARM_TARGETS (ตั้งเองใน .env ไว้ทดลอง)
2. เทียบกับ DaemonSet ที่มีอยู่ สร้างตัวที่ขาด ลบตัวที่ไม่มีคาบไหนใช้แล้ว
   (2 คาบคนละ image = 2 DaemonSet คาบไหนจบก็ลบของคาบนั้น ถ้าใช้ image เดียวกัน ลบตอนคาบสุดท้ายจบ)
   ลบ DaemonSet แล้ว image ยังอยู่บน node
3. เลื่อน status ของ slot: PREWARMING (ยัง pull ไม่ครบ) / READY (ครบทุก worker) / DONE (เลย ends_at)

backend หลายตัวกัน reconcile ซ้อนกันด้วย advisory lock แบบเดียวกับ session_reconciler
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.configs.db import SessionLocal, engine
from app.configs.settings import settings
from app.models.class_slot import ClassSlot, ClassSlotStatus
from app.models.lab import RunTarget
from app.services.kubernetes_service import get_kubernetes_service
from app.services.prewarm_service import PrewarmService
from app.utils.logger import logger

# ห้ามชนกับ session_reconciler (880_001)
ADVISORY_LOCK_KEY = 880_002

LIVE_STATUSES = (ClassSlotStatus.SCHEDULED, ClassSlotStatus.PREWARMING, ClassSlotStatus.READY)


def slot_image(slot: ClassSlot) -> str:
    """image เต็มแบบเดียวกับที่ pod ของ lab จะ pull ตอน launch (ดู SessionService._build_k8s_task)

    ต้องตรงกันทุกตัวอักษร ไม่งั้น pull ไว้คนละชื่อ cache ไม่ช่วยอะไร
    """
    registry = os.getenv("DOCKER_REGISTRY_HOST", "100.127.74.48:5001")
    return f"{registry}/{slot.lab_image.full_image_name}"


def active_slots(db: Session, now: datetime) -> list[ClassSlot]:
    """slot ที่ต้อง pre-warm ตอนนี้ (AWS ใช้ AMI + ECR ไม่เกี่ยวกับ worker ของ K3s)"""
    lead = timedelta(minutes=settings.PREWARM_LEAD_MINUTES)
    return (
        db.query(ClassSlot)
        .options(joinedload(ClassSlot.lab_image))
        .filter(
            ClassSlot.deleted_at.is_(None),
            ClassSlot.status.in_(LIVE_STATUSES),
            ClassSlot.run_target == RunTarget.KUBERNETES,
            ClassSlot.starts_at <= now + lead,
            ClassSlot.ends_at > now,
        )
        .all()
    )


def _target_images(now: datetime) -> set[str]:
    return {t.image for t in settings.PREWARM_TARGETS if t.start_at <= now < t.end_at}


def sync_prewarm(prewarm: PrewarmService, db: Optional[Session] = None,
                 now: Optional[datetime] = None) -> dict:
    """ทำให้ DaemonSet และ status ของ slot ตรงกับเวลา now 1 รอบ

    db = None ใช้แค่ PREWARM_TARGETS (เทสที่ไม่มี DB)
    """
    now = now or datetime.now(timezone.utc)
    slots = active_slots(db, now) if db is not None else []
    desired = _target_images(now) | {slot_image(s) for s in slots}
    current = prewarm.list_managed()
    result = {"created": [], "removed": [], "slots": {}}

    for image in sorted(desired - current.keys()):
        if prewarm.ensure(image):
            result["created"].append(image)
    for image in sorted(current.keys() - desired):
        prewarm.remove(current[image])
        result["removed"].append(image)

    if db is not None:
        _update_slot_status(prewarm, db, slots, now, result["slots"])
    return result


def _update_slot_status(prewarm: PrewarmService, db: Session, slots: list[ClassSlot],
                        now: datetime, changed: dict) -> None:
    def move(slot: ClassSlot, status: ClassSlotStatus) -> None:
        if slot.status != status:
            changed[str(slot.id)] = f"{slot.status.name} -> {status.name}"
            slot.status = status

    if slots:
        # ครบ = worker ที่ Ready ทุกเครื่อง pull แล้ว และไม่มีเครื่องที่เพิ่งหลุด (ดู PrewarmService.status)
        ready = {ds["image"] for ds in prewarm.status() if ds["all_pulled"]}
        for slot in slots:
            # ไม่ล็อกไว้ที่ READY ถ้ามี worker ใหม่ที่ยัง pull ไม่เสร็จ slot ต้องกลับมาเป็น PREWARMING
            move(slot, ClassSlotStatus.READY if slot_image(slot) in ready else ClassSlotStatus.PREWARMING)

    for slot in db.query(ClassSlot).filter(
        ClassSlot.deleted_at.is_(None),
        ClassSlot.status.in_(LIVE_STATUSES),
        ClassSlot.ends_at <= now,
    ):
        move(slot, ClassSlotStatus.DONE)
    db.commit()


def sync_once() -> Optional[dict]:
    """sync 1 รอบ คืน None ถ้า backend ตัวอื่นกำลังทำอยู่ (lock อยู่บน connection แยกเหมือน reconciler)"""
    with engine.connect() as lock_conn:
        if not lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}
        ).scalar():
            return None
        try:
            db = SessionLocal()
            try:
                return sync_prewarm(PrewarmService(get_kubernetes_service()), db)
            finally:
                db.close()
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})


async def run_prewarm_scheduler(interval_seconds: int, stop: asyncio.Event) -> None:
    """เรียก sync_once ทุก interval_seconds จนกว่า stop จะถูก set

    kubernetes client เป็นแบบ blocking เลยรันใน thread ไม่ให้ event loop ของ FastAPI ค้าง
    """
    logger.info(f"Prewarm scheduler started (every {interval_seconds}s, lead "
                f"{settings.PREWARM_LEAD_MINUTES} min, {len(settings.PREWARM_TARGETS)} .env targets)")
    while not stop.is_set():
        try:
            result = await asyncio.to_thread(sync_once)
            if result and (result["created"] or result["removed"] or result["slots"]):
                logger.info(f"Prewarm scheduler: {result}")
        except Exception as e:
            # รอบนี้พัง (เช่น ต่อ K3s ไม่ได้) ลองใหม่รอบหน้า
            logger.warning(f"Prewarm scheduler failed: {e}")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
    logger.info("Prewarm scheduler stopped")
