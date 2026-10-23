"""Merge heads: class_slots (20261013_08) + infrastructure_logs / billing_reports (20261018_01).

Revision ID: 20261023_01
Revises: 20261013_08, 20261018_01
Create Date: 2026-10-23

20261018_01 (PR #98) ต่อจาก 20241015_00 แทน head ล่าสุด พอ merge main เข้ามา alembic เลยมี 2 head
→ init_db.py `upgrade head` พัง (MultipleHeads) deploy ไม่ผ่าน
ไม่แก้ down_revision ของ 20261018_01 เพราะ DB ที่ stamp ไว้แล้ว (dev ของคนที่ใช้ main) จะเพี้ยน
ใช้ merge revision แทน ไม่มี DDL
"""

revision = "20261023_01"
down_revision = ("20261013_08", "20261018_01")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
