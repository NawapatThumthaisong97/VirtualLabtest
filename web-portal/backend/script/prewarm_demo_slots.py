#!/usr/bin/env python3
"""
สร้าง 2 คาบทดลอง (Exp2) ให้ prewarm scheduler เห็น: SE301 ใช้ vlab/hello:v1, DEVOPS201 ใช้ vlab/hello:v2

ทั้งสองคาบเริ่มพร้อมกัน แต่คาบแรกจบก่อน ใช้ดูว่า scheduler
- สร้าง DaemonSet 2 ตัว (คนละ image) ก่อนคาบตาม PREWARM_LEAD_MINUTES
- slot เป็น PREWARMING แล้ว READY เมื่อทุก worker pull เสร็จ
- คาบแรกจบ → ลบเฉพาะ DaemonSet ของ v1 slot แรกเป็น DONE คาบสองยังอยู่

ต้อง seed ก่อน (ใช้วิชา SE301 / DEVOPS201 และอาจารย์จาก seed) และ push vlab/hello:v1, v2 ขึ้น registry แล้ว

ใช้:
    python script/prewarm_demo_slots.py                    # เริ่มอีก 2 นาที คาบแรก 5 นาที คาบสอง 10 นาที
    python script/prewarm_demo_slots.py --start 3 --first 6 --second 12
    python script/prewarm_demo_slots.py --clear            # soft delete คาบทดลองทั้งหมด

ตั้งใน .env ก่อนเปิด backend (scheduler ปิดไว้เป็นค่าเริ่มต้น):
    PREWARM_ENABLED=true
    PREWARM_INTERVAL_SECONDS=20
    PREWARM_LEAD_MINUTES=1
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.configs.db import SessionLocal
from app.models.class_slot import ClassSlot
from app.models.courses import Course
from app.models.lab_image import ImageStatus, LabImage

DEMO_NOTE = "prewarm demo (script/prewarm_demo_slots.py)"


def demo_image(db, course: Course, tag: str) -> LabImage:
    img = db.query(LabImage).filter_by(repository="vlab/hello", tag=tag).first()
    if img is None:
        img = LabImage(uploaded_by=course.created_by, course_id=course.id, repository="vlab/hello",
                       tag=tag, image_digest=f"demo-vlab-hello-{tag}", size_mb=55,
                       status=ImageStatus.APPROVED, description="Exp2 demo image (experiments/prewarm/hello)")
        db.add(img)
        db.flush()
    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=float, default=2, help="ทั้งสองคาบเริ่มอีกกี่นาที")
    parser.add_argument("--first", type=float, default=5, help="คาบแรก (SE301, hello:v1) ยาวกี่นาที")
    parser.add_argument("--second", type=float, default=10, help="คาบสอง (DEVOPS201, hello:v2) ยาวกี่นาที")
    parser.add_argument("--clear", action="store_true", help="soft delete คาบทดลองทั้งหมดแล้วจบ")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        if args.clear:
            n = db.query(ClassSlot).filter(ClassSlot.note == DEMO_NOTE, ClassSlot.deleted_at.is_(None)) \
                .update({ClassSlot.deleted_at: now})
            db.commit()
            print(f"soft deleted {n} demo slots")
            return

        se = db.query(Course).filter_by(code="SE301").one()
        devops = db.query(Course).filter_by(code="DEVOPS201").one()
        starts_at = now + timedelta(minutes=args.start)
        for course, tag, minutes in ((se, "v1", args.first), (devops, "v2", args.second)):
            slot = ClassSlot(course_id=course.id, lab_image_id=demo_image(db, course, tag).id,
                             starts_at=starts_at, ends_at=starts_at + timedelta(minutes=minutes),
                             expected_seats=5, note=DEMO_NOTE, created_by=course.created_by)
            db.add(slot)
            db.flush()
            local = lambda t: t.astimezone().strftime("%H:%M:%S")
            print(f"{course.code:10} hello:{tag}  {local(slot.starts_at)} - {local(slot.ends_at)}  slot {slot.id}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
