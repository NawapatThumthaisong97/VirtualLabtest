"""Add run_target column to labs table.

Revision ID: 20261013_05
Revises: 20261013_04
Create Date: 2026-10-13
"""

from alembic import op


revision = "20261013_05"
down_revision = "20261013_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add run_target enum type and column to labs table."""
    statements = (
        # Create the enum type first
        "CREATE TYPE runtarget AS ENUM ('KUBERNETES', 'AWS')",
        # Add the column with default value
        """ALTER TABLE labs 
           ADD COLUMN run_target runtarget 
           NOT NULL 
           DEFAULT 'KUBERNETES'::runtarget""",
    )
    
    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    """Remove run_target column and enum type from labs table."""
    statements = (
        "ALTER TABLE labs DROP COLUMN run_target",
        "DROP TYPE runtarget",
    )
    
    for stmt in statements:
        op.execute(stmt)
