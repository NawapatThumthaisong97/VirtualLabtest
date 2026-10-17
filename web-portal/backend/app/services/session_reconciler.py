"""
Session Reconciler
งานพื้นหลังที่ปิด session ซึ่งเครื่องหายไปแล้วแต่ DB ยังเป็น RUNNING

autostop (lifespan_minutes) หรือ pod / EC2 ที่ตายเองจะลบเครื่องโดยไม่มีใครบอก backend
ถ้าไม่มีตัวนี้ session จะค้าง RUNNING จนกว่าผู้ใช้จะกด Start ใหม่หรือ DELETE
"""
import asyncio
from typing import Optional

from sqlalchemy import text

from app.configs.db import SessionLocal, engine
from app.repositories.lab_image_repository import LabImageRepository
from app.repositories.lab_repository import LabRepository
from app.repositories.session_repository import SessionRepository
from app.services.session_service import SessionService
from app.utils.logger import logger

# Postgres advisory lock กันไม่ให้ backend หลายตัว reconcile พร้อมกัน (เลขอะไรก็ได้ที่ไม่ชน)
ADVISORY_LOCK_KEY = 880_001


def reconcile_once() -> Optional[dict]:
    """reconcile 1 รอบ คืน None ถ้า backend ตัวอื่นกำลังทำอยู่

    lock ถือไว้บน connection แยก เพราะ SessionService commit หลายครั้ง ถ้าใช้ connection
    เดียวกับ ORM จะไม่แน่ใจว่า unlock ได้ connection เดิม
    """
    with engine.connect() as lock_conn:
        if not lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}
        ).scalar():
            return None
        try:
            db = SessionLocal()
            try:
                service = SessionService(
                    db, SessionRepository(db), LabRepository(db), LabImageRepository(db)
                )
                return service.reconcile_sessions()
            finally:
                db.close()
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})


async def run_reconciler(interval_seconds: int, stop: asyncio.Event) -> None:
    """เรียก reconcile_once ทุก interval_seconds จนกว่า stop จะถูก set

    เรียก SkyPilot แบบ blocking เลยรันใน thread ไม่ให้ event loop ของ FastAPI ค้าง
    """
    logger.info(f"Session reconciler started (every {interval_seconds}s)")
    while not stop.is_set():
        try:
            result = await asyncio.to_thread(reconcile_once)
            if result and (result["stopped"] or result["failed"]):
                logger.info(f"Session reconciler: {result}")
        except Exception as e:
            # รอบนี้พัง (เช่น SkyPilot API server ล่ม) ไม่แตะ session แล้วลองใหม่รอบหน้า
            logger.warning(f"Session reconciler failed: {e}")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
    logger.info("Session reconciler stopped")
