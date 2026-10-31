"""คาบ online: เปิด EC2 รอไว้ให้นักศึกษาทุกคนก่อนคาบ (docs/AWS_PRELAUNCH.md)

Revision ID: 20261031_01
Revises: 20261028_01
Create Date: 2026-10-31

- booking_requests.mode / class_schedules.mode: onsite (warm pod เดิม) | online (EC2 ต่อคน)
  ของเดิมทั้งหมดเป็น onsite
- sessions.prelaunched_at: scheduler เปิดเครื่องนี้รอไว้ให้ (null = นักศึกษากด Start เอง)
- sessions.claimed_at: นักศึกษากด Start รับเครื่องที่เปิดรอไว้แล้ว
- sessionendreason เพิ่ม PRELAUNCH_UNCLAIMED: ไม่กด Start ภายในเวลาที่กำหนด ระบบคืนเครื่อง
"""
import sqlalchemy as sa
from alembic import op

revision = "20261031_01"
down_revision = "20261028_01"
branch_labels = None
depends_on = None

MODE_CHECK = "mode IN ('onsite', 'online')"


def upgrade() -> None:
    for table in ("booking_requests", "class_schedules"):
        op.add_column(table, sa.Column("mode", sa.String(16), nullable=False, server_default="onsite"))
        op.create_check_constraint(f"ck_{table}_mode", table, MODE_CHECK)
    op.add_column("sessions", sa.Column("prelaunched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    # IF NOT EXISTS: รันซ้ำได้ (Postgres 12+ ADD VALUE ใน transaction ได้ แค่ห้ามใช้ค่าใหม่ใน transaction เดียวกัน)
    op.execute("ALTER TYPE sessionendreason ADD VALUE IF NOT EXISTS 'PRELAUNCH_UNCLAIMED'")


def downgrade() -> None:
    # Postgres ลบค่าออกจาก enum ไม่ได้ ต้องสร้าง type ใหม่ — session ที่จบด้วยเหตุผลนี้ย้ายไป EXPIRED ก่อน
    op.execute("UPDATE sessions SET end_reason = 'EXPIRED' WHERE end_reason = 'PRELAUNCH_UNCLAIMED'")
    op.execute("ALTER TYPE sessionendreason RENAME TO sessionendreason_old")
    op.execute("CREATE TYPE sessionendreason AS ENUM "
               "('USER_DELETE', 'EXPIRED', 'LOST', 'LAUNCH_FAILED', 'STALE_PENDING')")
    op.execute("ALTER TABLE sessions ALTER COLUMN end_reason TYPE sessionendreason "
               "USING end_reason::text::sessionendreason")
    op.execute("DROP TYPE sessionendreason_old")
    op.drop_column("sessions", "claimed_at")
    op.drop_column("sessions", "prelaunched_at")
    for table in ("class_schedules", "booking_requests"):
        op.drop_constraint(f"ck_{table}_mode", table, type_="check")
        op.drop_column(table, "mode")
