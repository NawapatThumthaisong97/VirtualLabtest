"""Add health_checks (การ์ด System status หน้า admin).

Revision ID: 20261023_02
Revises: 20261023_01
Create Date: 2026-10-23

DDL เหมือนที่ create_all สร้างจาก app/models/health_check.py
IF NOT EXISTS ทุกตัว: DB ที่ create_all สร้างไว้แล้วรันซ้ำได้
"""

from alembic import op


revision = "20261023_02"
down_revision = "20261023_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS health_checks (
            id bigserial PRIMARY KEY,
            service varchar(32) NOT NULL,
            status varchar(16) NOT NULL,
            latency_ms integer,
            version varchar(64),
            detail text,
            checked_at timestamp with time zone DEFAULT now() NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS ix_health_checks_service_checked_at ON health_checks (service, checked_at)",
        "CREATE INDEX IF NOT EXISTS ix_health_checks_checked_at ON health_checks (checked_at)",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS health_checks")
