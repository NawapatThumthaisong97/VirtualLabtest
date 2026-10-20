"""Add AUTO to runtarget enum.

Revision ID: 20261013_07
Revises: 20241015_00 (archive fields — ต่อจาก 20261013_06 อีกที)
Create Date: 2026-10-21

AUTO = เลือกที่ launch ตามเครื่องที่กด Start (เครื่องแลป → KUBERNETES, ที่อื่น → AWS)
ดู docs/RUN_TARGET_AUTO.md — DB dev เคยเติมมือด้วย ALTER TYPE ... ADD VALUE 'AUTO' (docs/DB_DIAGRAM.md)
"""

from alembic import op


revision = "20261013_07"
down_revision = "20241015_00"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: DB ที่เติม AUTO ด้วยมือไปแล้วรันซ้ำได้
    op.execute("ALTER TYPE runtarget ADD VALUE IF NOT EXISTS 'AUTO'")


def downgrade() -> None:
    # Postgres ลบค่าออกจาก enum ไม่ได้ ต้องสร้าง type ใหม่ — lab ที่เป็น AUTO ต้องย้ายก่อน
    op.execute("UPDATE labs SET run_target = 'KUBERNETES' WHERE run_target = 'AUTO'")
    op.execute("ALTER TABLE labs ALTER COLUMN run_target DROP DEFAULT")
    op.execute("ALTER TYPE runtarget RENAME TO runtarget_old")
    op.execute("CREATE TYPE runtarget AS ENUM ('KUBERNETES', 'AWS')")
    op.execute("ALTER TABLE labs ALTER COLUMN run_target TYPE runtarget USING run_target::text::runtarget")
    op.execute("ALTER TABLE labs ALTER COLUMN run_target SET DEFAULT 'KUBERNETES'::runtarget")
    op.execute("DROP TYPE runtarget_old")
