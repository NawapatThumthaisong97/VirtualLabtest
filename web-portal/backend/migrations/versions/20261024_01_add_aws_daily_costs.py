"""Add aws_daily_costs (ยอดจริงจาก Cost Explorer หน้า admin billing).

Revision ID: 20261024_01
Revises: 20261023_03
Create Date: 2026-10-24

DDL เหมือนที่ create_all สร้างจาก app/models/aws_daily_cost.py — IF NOT EXISTS รันซ้ำได้
"""

from alembic import op


revision = "20261024_01"
down_revision = "20261023_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS aws_daily_costs (
        day date PRIMARY KEY,
        cost_usd numeric(12, 6) NOT NULL,
        fetched_at timestamp with time zone DEFAULT now() NOT NULL
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS aws_daily_costs")
