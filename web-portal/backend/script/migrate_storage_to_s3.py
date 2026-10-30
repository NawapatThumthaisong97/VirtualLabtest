"""
ย้ายไฟล์ของเว็บจาก disk (STORAGE_ROOT) ขึ้น S3 bucket (STORAGE_S3_BUCKET) ด้วย key เดิม — DB ไม่ต้องแก้

key ที่ DB เก็บ (courses/... labs/... course-docs/...) คือ path ใต้ STORAGE_ROOT อยู่แล้ว
คัดลอกตรงตัว เปลี่ยน STORAGE_BACKEND=s3 แล้วลิงก์เดิมใช้ได้ทันที

รันใน container ของ backend (มี credential profile skypilot + settings ครบ):
    python script/migrate_storage_to_s3.py --dry-run     # ดูว่าจะอัปอะไร
    python script/migrate_storage_to_s3.py               # อัปจริง
    python script/migrate_storage_to_s3.py --check-db    # + บอก key ใน DB ที่ไม่มีไฟล์ทั้งบน disk และ S3

- ไฟล์ที่มีบน S3 แล้วขนาดเท่ากัน = ข้าม (รันซ้ำได้)
- ไม่ลบไฟล์บน disk — ลบเองหลังเช็กว่าเว็บเปิดไฟล์จาก S3 ได้
"""

import argparse
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from botocore.exceptions import ClientError  # noqa: E402

from app.adapters.local_storage import LocalStorage  # noqa: E402
from app.adapters.s3_storage import build_s3_storage  # noqa: E402

PREFIXES = ("courses/", "labs/", "course-docs/")


def remote_size(s3, key: str) -> int | None:
    try:
        return s3.client.head_object(Bucket=s3.bucket, Key=key)["ContentLength"]
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def db_keys() -> list[str]:
    """key ทั้งหมดที่ DB อ้างถึง (รวมแถวที่ soft delete — กู้กลับมาแล้วไฟล์ต้องยังอยู่)"""
    from sqlalchemy import select

    from app.configs.db import SessionLocal
    from app.models.course_document import CourseDocument
    from app.models.courses import Course
    from app.models.lab import Lab

    db = SessionLocal()
    try:
        keys = set(db.scalars(select(Lab.doc_url).where(Lab.doc_url.is_not(None))))
        keys |= {k for k in db.scalars(select(Course.image_url).where(Course.image_url.is_not(None))) if not k.startswith("http")}
        keys |= set(db.scalars(select(CourseDocument.file_key)))
        return sorted(keys)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="แสดงอย่างเดียว ไม่อัป")
    parser.add_argument("--check-db", action="store_true", help="เทียบกับ key ใน DB ด้วย")
    args = parser.parse_args()

    local = LocalStorage()
    s3 = build_s3_storage()
    print(f"disk : {local.root}")
    print(f"s3   : s3://{s3.bucket}")
    print()

    uploaded = skipped = 0
    for path in sorted(p for p in local.root.rglob("*") if p.is_file()):
        key = path.relative_to(local.root).as_posix()
        if not key.startswith(PREFIXES):
            continue  # .gitkeep ฯลฯ ไม่ใช่ไฟล์ของเว็บ
        size = path.stat().st_size
        if remote_size(s3, key) == size:
            skipped += 1
            print(f"[=] {key} ({size} B) มีบน S3 แล้ว")
            continue
        content_type, _ = mimetypes.guess_type(path.name)
        print(f"[{'dry' if args.dry_run else '+'}] {key} ({size} B, {content_type})")
        if not args.dry_run:
            with path.open("rb") as handle:
                s3.save(key, handle, content_type)
            uploaded += 1

    print()
    print(f"อัป {uploaded} ไฟล์, ข้าม {skipped} ไฟล์ (มีแล้ว){' — dry run ไม่ได้อัปจริง' if args.dry_run else ''}")

    if args.check_db:
        print()
        missing = [k for k in db_keys() if remote_size(s3, k) is None and not local.exists(k)]
        if missing:
            print("key ใน DB ที่ไม่มีไฟล์ทั้งบน disk และ S3 (เปิดแล้วจะ 404):")
            for key in missing:
                print(f"  - {key}")
        else:
            print("key ใน DB มีไฟล์ครบ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
