"""usage_records.duration_seconds / est_cost_usd + cloud_controls (หน้า admin billing).

Revision ID: 20261023_03
Revises: 20261023_02
Create Date: 2026-10-23

DDL เหมือนที่ create_all สร้างจาก app/models/usage_record.py, cloud_control.py
IF NOT EXISTS ทุกตัว: DB ที่ create_all สร้างไว้แล้วรันซ้ำได้
"""

from alembic import op


revision = "20261023_03"
down_revision = "20261023_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        "ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS duration_seconds bigint DEFAULT 0 NOT NULL",
        "ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS est_cost_usd numeric(10, 4) DEFAULT 0 NOT NULL",
        """CREATE TABLE IF NOT EXISTS cloud_controls (
            id integer PRIMARY KEY,
            burst_enabled boolean NOT NULL,
            reason text,
            changed_by uuid REFERENCES users(id),
            changed_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT ck_cloud_controls_single_row CHECK (id = 1)
        )""",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cloud_controls")
    op.execute("ALTER TABLE usage_records DROP COLUMN IF EXISTS est_cost_usd")
    op.execute("ALTER TABLE usage_records DROP COLUMN IF EXISTS duration_seconds")
