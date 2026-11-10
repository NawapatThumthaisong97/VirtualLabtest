"""lab gateway: sessions.gateway_token + sessions.upstreams (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md 1A.3)

Revision ID: 20261111_01
Revises: 20261031_01
Create Date: 2026-11-11

- sessions.gateway_token: token ใน hostname ของ lab AWS (l-<token>-<port>.<domain>) unique, null = ไม่ผ่าน gateway
- sessions.upstreams: ปลายทางจริงที่ Traefik ส่งต่อ {"<port>": "http://10.10.2.x:<port>"}
ทั้งสอง column nullable ไม่ต้อง backfill: session เดิมทั้งหมดไม่ผ่าน gateway
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261111_01"
down_revision = "20261031_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("gateway_token", sa.String(32), nullable=True))
    op.add_column("sessions", sa.Column("upstreams", JSONB, nullable=True))
    op.create_unique_constraint("uq_sessions_gateway_token", "sessions", ["gateway_token"])


def downgrade() -> None:
    op.drop_constraint("uq_sessions_gateway_token", "sessions", type_="unique")
    op.drop_column("sessions", "upstreams")
    op.drop_column("sessions", "gateway_token")
