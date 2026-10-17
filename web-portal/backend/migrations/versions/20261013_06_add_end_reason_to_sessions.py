"""Add end_reason column to sessions table.

Revision ID: 20261013_06
Revises: 20261013_05
Create Date: 2026-10-13
"""

from alembic import op


revision = "20261013_06"
down_revision = "20261013_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add end_reason enum type and column to sessions table."""
    statements = (
        # Create the enum type first
        """CREATE TYPE sessionendreason AS ENUM (
            'USER_DELETE', 
            'EXPIRED', 
            'LOST', 
            'LAUNCH_FAILED', 
            'STALE_PENDING'
        )""",
        # Add the column (nullable, no default since it's only for ended sessions)
        """ALTER TABLE sessions 
           ADD COLUMN end_reason sessionendreason""",
    )
    
    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    """Remove end_reason column and enum type from sessions table."""
    statements = (
        "ALTER TABLE sessions DROP COLUMN end_reason",
        "DROP TYPE sessionendreason",
    )
    
    for stmt in statements:
        op.execute(stmt)
