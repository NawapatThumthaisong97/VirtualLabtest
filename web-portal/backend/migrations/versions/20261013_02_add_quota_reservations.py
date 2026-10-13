"""Add atomic quota reservation records.

Revision ID: 20261013_02
Revises: 20261013_01
Create Date: 2026-10-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261013_02"
down_revision = "20261013_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quota_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quota_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("compute_hours", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("storage_mb", sa.Integer(), nullable=False),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="reserved", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('reserved', 'committed', 'released')",
            name="ck_quota_reservations_status",
        ),
        sa.CheckConstraint(
            "compute_hours > 0", name="ck_quota_reservations_compute_positive"
        ),
        sa.CheckConstraint(
            "storage_mb > 0", name="ck_quota_reservations_storage_positive"
        ),
        sa.ForeignKeyConstraint(["quota_id"], ["quotas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quota_reservations_quota_period",
        "quota_reservations",
        ["quota_id", "period_end_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quota_reservations_quota_period", table_name="quota_reservations"
    )
    op.drop_table("quota_reservations")