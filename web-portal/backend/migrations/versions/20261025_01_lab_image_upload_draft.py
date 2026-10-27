"""Allow draft lab_images before upload: nullable image_digest, unique archive_key.
Revision ID: 20261025_01
Revises: 20261024_02
Create Date: 2026-10-23

Flow อัปโหลด image (.tar) ขึ้น R2:
  1. client ขอ presign -> backend สร้างแถว lab_images status='pending' (ยังไม่รู้ image_digest)
  2. client PUT ไฟล์ไป R2 -> event -> Queue -> Worker -> webhook เติม archive_etag / size / uploaded_at
     โดยหาแถวจาก archive_key
  3. approve -> เติม image_digest

ดังนั้น
  - image_digest ต้อง NULL ได้ (unique เดิมยังอยู่ — Postgres ปล่อย NULL ซ้ำได้)
  - archive_key ต้อง unique + index เพราะ webhook ใช้ค้นหา และต้องไม่มีสองแถวชี้ไฟล์เดียวกัน
"""
from alembic import op

revision = "20261025_01"
down_revision = "20261024_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        "ALTER TABLE lab_images ALTER COLUMN image_digest DROP NOT NULL",
        # ชื่อเดียวกับที่ SQLAlchemy ตั้งให้ (unique=True, index=True) เพื่อไม่ให้ model กับ DB เพี้ยนกัน
        "CREATE UNIQUE INDEX ix_lab_images_archive_key ON lab_images (archive_key)",
    )
    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    statements = (
        "DROP INDEX ix_lab_images_archive_key",
        # draft ที่ยังไม่มี digest จะทำให้ SET NOT NULL พัง จึงเติมค่าชั่วคราวก่อน
        "UPDATE lab_images SET image_digest = 'pending:' || id::text WHERE image_digest IS NULL",
        "ALTER TABLE lab_images ALTER COLUMN image_digest SET NOT NULL",
    )
    for stmt in statements:
        op.execute(stmt)
