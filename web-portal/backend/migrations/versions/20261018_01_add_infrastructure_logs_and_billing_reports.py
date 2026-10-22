"""Add infrastructure_logs and billing_reports tables with composite indexes.

Revision ID: 20261018_01
Revises: 20261013_06
Create Date: 2026-10-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261018_01"
down_revision = "20241015_00"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create infrastructure_logs and billing_reports tables with composite indexes."""
    # 1. Create infrastructure_logs table
    op.create_table(
        "infrastructure_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("anon_id", sa.String(64), nullable=True),
        sa.Column("cluster_or_subnet", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )
    # Composite indexes for infrastructure_logs
    op.create_index(
        "ix_infra_logs_timestamp_severity",
        "infrastructure_logs",
        ["timestamp", "severity"],
    )
    op.create_index(
        "ix_infra_logs_category_severity",
        "infrastructure_logs",
        ["category", "severity"],
    )
    op.create_index(
        "ix_infra_logs_cluster_subnet",
        "infrastructure_logs",
        ["cluster_or_subnet"],
    )
    op.create_index(
        "ix_infra_logs_anon_id",
        "infrastructure_logs",
        ["anon_id"],
    )

    # 2. Create billing_reports table
    op.create_table(
        "billing_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("group_by", sa.String(50), nullable=False),
        sa.Column("export_format", sa.String(10), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("total_cost_thb", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("total_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Indexes for billing_reports
    op.create_index(
        "ix_billing_reports_created_at",
        "billing_reports",
        ["created_at"],
    )
    op.create_index(
        "ix_billing_reports_deleted_at",
        "billing_reports",
        ["deleted_at"],
    )


def downgrade() -> None:
    """Drop billing_reports and infrastructure_logs tables and indexes."""
    # 1. Drop billing_reports
    op.drop_index("ix_billing_reports_deleted_at", table_name="billing_reports")
    op.drop_index("ix_billing_reports_created_at", table_name="billing_reports")
    op.drop_table("billing_reports")

    # 2. Drop infrastructure_logs
    op.drop_index("ix_infra_logs_anon_id", table_name="infrastructure_logs")
    op.drop_index("ix_infra_logs_cluster_subnet", table_name="infrastructure_logs")
    op.drop_index("ix_infra_logs_category_severity", table_name="infrastructure_logs")
    op.drop_index("ix_infra_logs_timestamp_severity", table_name="infrastructure_logs")
    op.drop_table("infrastructure_logs")

