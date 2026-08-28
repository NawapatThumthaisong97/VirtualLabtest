"""
เตรียมไฟล์เอกสารแลปสำหรับทดสอบ GET /api/labs/{lab_id}/doc

ทำ 3 อย่างให้ในทีเดียว — ไม่ต้องก๊อป UUID ไปมาเอง:
  1. หา lab จากชื่อ (หรือระบุ --lab-id ตรง ๆ)
  2. ก๊อปไฟล์ไปวางที่ storage/labs/{lab_id}/doc.<ext>
  3. อัปเดต labs.doc_url ให้ชี้ key นั้น

รัน (จากโฟลเดอร์ backend):
    python script/setup_lab_doc.py ../frontend/public/kubernetes-intro.pdf
    python script/setup_lab_doc.py <file> --title "Lab 2 : Kubernetes"
    python script/setup_lab_doc.py <file> --lab-id 0b2f8c14-...
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# console ของ Windows ปกติไม่ใช่ UTF-8 ข้อความไทยจะออกมาเป็นตัวยึกยือ
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.adapters.local_storage import local_storage
from app.configs.db import SessionLocal
from app.models.lab import Lab

DEFAULT_TITLE = "Linux Networking System"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="ไฟล์เอกสารที่จะใช้ทดสอบ (เช่น .pdf)")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="ชื่อ lab ที่จะผูกไฟล์นี้")
    parser.add_argument("--lab-id", default=None, help="ระบุ lab id ตรง ๆ (ข้าม --title)")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_file():
        print(f"[x] ไม่เจอไฟล์: {source}")
        return 1

    db = SessionLocal()
    try:
        if args.lab_id:
            lab = db.get(Lab, args.lab_id)
        else:
            lab = db.scalars(
                select(Lab)
                .where(Lab.title == args.title, Lab.deleted_at.is_(None))
                .order_by(Lab.created_at)
            ).first()

        if lab is None:
            target = args.lab_id or f'title="{args.title}"'
            print(f"[x] ไม่เจอ lab: {target}")
            print()

            # บอกไปเลยว่ามีอะไรให้เลือก — ไม่ต้องไปเปิด psql เองอีกรอบ
            available = db.scalars(
                select(Lab).where(Lab.deleted_at.is_(None)).order_by(Lab.created_at)
            ).all()

            if not available:
                print("    ตาราง labs ว่างเปล่า — รัน python script/run_seed.py ก่อน")
            else:
                print("    lab ที่มีอยู่ตอนนี้ (ใช้ --title ตามนี้):")
                for row in available:
                    print(f"      - {row.title}")
            return 1

        key = f"labs/{lab.id}/doc{source.suffix}"
        dest = local_storage.resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

        lab.doc_url = key
        db.commit()

        print(f"[ok] lab      : {lab.title}")
        print(f"[ok] lab_id   : {lab.id}")
        print(f"[ok] doc_url  : {key}")
        print(f"[ok] ไฟล์อยู่ที่ : {dest}")
        print()
        print(f"     API  -> http://localhost:8000/api/labs/{lab.id}/doc")
        print(f"     หน้าเว็บ -> http://localhost:5173/labs/{lab.id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
