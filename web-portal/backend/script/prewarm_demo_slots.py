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
    WARM_POD_ENABLED=true          # ถ้าจะทดลอง warm pod ด้วย (Exp3)

แต่ละคาบมี lab ของตัวเอง (พิมพ์ lab_id ออกมา) image เป็น busybox httpd เปิด v1 พอร์ต 8080 / v2 พอร์ต 8081
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.configs.db import SessionLocal
from app.models.class_slot import ClassSlot
from sqlalchemy import func

from app.models.courses import Course
from app.models.lab import Lab, LabStatus, RunTarget
from app.models.lab_image import ImageStatus, LabImage

DEMO_NOTE = "prewarm demo (script/prewarm_demo_slots.py)"


# hello เป็น busybox มี httpd ในตัว ใช้เป็น "lab" ทดลอง warm pod ได้ (เปิด http://<IP เครื่อง>:<port> เห็น hello vN)
# คนละพอร์ต เพราะ warm pod ใช้ hostPort ถ้า 2 lab ใช้พอร์ตเดียวกันบนเครื่องเดียว ตัวที่ 2 จะ Pending
DEMO_PORTS = {"v1": 8080, "v2": 8081}


def demo_image(db, course: Course, tag: str) -> LabImage:
    port = DEMO_PORTS[tag]
    img = db.query(LabImage).filter_by(repository="vlab/hello", tag=tag).first()
    if img is None:
        img = LabImage(uploaded_by=course.created_by, course_id=course.id, repository="vlab/hello",
                       tag=tag, image_digest=f"demo-vlab-hello-{tag}", size_mb=55,
                       status=ImageStatus.APPROVED, description="Exp2/3 demo image (experiments/prewarm/hello)")
        db.add(img)
    img.cpu_requirement, img.memory_requirement = "0.1", "0.05"  # เล็กพอลงทุกเครื่อง
    img.exposed_ports = [port]
    img.entrypoint_script = f"mkdir -p /www && cat /hello.txt > /www/index.html && exec httpd -f -p {port} -h /www"
    img.lifespan_minutes = 10
    db.flush()
    return img


def demo_lab(db, course: Course, img: LabImage) -> Lab:
    """lab ที่ชี้ image ทดลอง ไว้ใช้ POST /api/sessions"""
    lab = db.query(Lab).filter_by(course_id=course.id, image_id=img.id, deleted_at=None).first()
    if lab is None:
        last = db.query(func.max(Lab.order_no)).filter(Lab.course_id == course.id).scalar() or 0
        lab = Lab(course_id=course.id, title=f"Demo warm pod ({img.full_image_name})", order_no=last + 1,
                  image_id=img.id, status=LabStatus.PUBLISHED, run_target=RunTarget.KUBERNETES)
        db.add(lab)
        db.flush()
    return lab


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
            img = demo_image(db, course, tag)
            lab = demo_lab(db, course, img)
            slot = ClassSlot(course_id=course.id, lab_id=lab.id, lab_image_id=img.id,
                             starts_at=starts_at, ends_at=starts_at + timedelta(minutes=minutes),
                             expected_seats=5, note=DEMO_NOTE, created_by=course.created_by)
            db.add(slot)
            db.flush()
            local = lambda t: t.astimezone().strftime("%H:%M:%S")
            print(f"{course.code:10} hello:{tag} port {DEMO_PORTS[tag]}  {local(slot.starts_at)} - "
                  f"{local(slot.ends_at)}  lab_id {lab.id}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
