"""Add scan state columns to lab_images and drop unique on image_digest.

Revision ID: 20261025_02
Revises: 20261025_01
Create Date: 2026-10-24

ดู docs/LAB_IMAGE_SCAN_ARCHITECTURE.md
  - scan_status: NOT_STARTED -> QUEUED -> RUNNING -> PASSED / FAILED / ERROR
    เก็บเป็นชื่อ enum (ตัวพิมพ์ใหญ่) เหมือน enum อื่นที่ SQLAlchemy สร้าง
  - image_digest ไม่ unique แล้ว: tar เนื้อเดียวกันสองชื่อได้ digest เดียวกัน
    (repository, tag) ยัง unique ผ่าน uq_repository_tag

แถวเดิม:
  - APPROVED ถือว่า PASSED (image เดิม build ด้วย Ansible ไม่ได้ผ่าน pipeline นี้)
  - PENDING ที่มีไฟล์ขึ้น R2 แล้ว -> QUEUED (รอสแกน) ที่เหลือ NOT_STARTED
"""
from alembic import op

revision = "20261025_02"
down_revision = "20261025_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        "CREATE TYPE scanstatus AS ENUM "
        "('NOT_STARTED', 'QUEUED', 'RUNNING', 'PASSED', 'FAILED', 'ERROR')",
        """ALTER TABLE lab_images
           ADD COLUMN scan_status scanstatus NOT NULL DEFAULT 'NOT_STARTED'::scanstatus,
           ADD COLUMN scan_attempts INTEGER NOT NULL DEFAULT 0,
           ADD COLUMN scan_job_name VARCHAR(63),
           ADD COLUMN scan_started_at TIMESTAMP WITH TIME ZONE,
           ADD COLUMN scan_finished_at TIMESTAMP WITH TIME ZONE,
           ADD COLUMN scan_summary JSONB""",
        # ชื่อเดียวกับที่ SQLAlchemy ตั้งให้ (index=True)
        "CREATE INDEX ix_lab_images_scan_status ON lab_images (scan_status)",
        "UPDATE lab_images SET scan_status = 'PASSED' WHERE status = 'APPROVED'",
        "UPDATE lab_images SET scan_status = 'QUEUED' "
        "WHERE status = 'PENDING' AND archive_uploaded_at IS NOT NULL",
        # UNIQUE แบบ inline ใน initial schema -> Postgres ตั้งชื่อเป็น <table>_<column>_key
        "ALTER TABLE lab_images DROP CONSTRAINT IF EXISTS lab_images_image_digest_key",
    )
    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    statements = (
        # digest ซ้ำกันจะทำให้ ADD UNIQUE พัง: เก็บไว้แถวแรก ที่เหลือล้างเป็น NULL (NULL ซ้ำได้)
        """UPDATE lab_images SET image_digest = NULL
           WHERE id IN (
               SELECT id FROM (
                   SELECT id, ROW_NUMBER() OVER (PARTITION BY image_digest ORDER BY created_at) AS rn
                   FROM lab_images WHERE image_digest IS NOT NULL
               ) dup WHERE dup.rn > 1
           )""",
        "ALTER TABLE lab_images ADD CONSTRAINT lab_images_image_digest_key UNIQUE (image_digest)",
        "DROP INDEX ix_lab_images_scan_status",
        """ALTER TABLE lab_images
           DROP COLUMN scan_summary,
           DROP COLUMN scan_finished_at,
           DROP COLUMN scan_started_at,
           DROP COLUMN scan_job_name,
           DROP COLUMN scan_attempts,
           DROP COLUMN scan_status""",
        "DROP TYPE scanstatus",
    )
    for stmt in statements:
        op.execute(stmt)
