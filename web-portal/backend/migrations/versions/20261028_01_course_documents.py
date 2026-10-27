"""course_documents: เอกสารของวิชาที่ไม่ผูกกับ lab (Instructor Console → Add new document)

Revision ID: 20261028_01
Revises: 20261025_02
Create Date: 2026-10-28

เอกสารที่ผูกกับ lab ยังเก็บที่ labs.doc_url เหมือนเดิม ตารางนี้สำหรับเอกสารรวมของวิชา
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261028_01"
down_revision = "20261025_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("file_key", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_course_documents_course_id", "course_documents", ["course_id"])
    op.create_index("ix_course_documents_deleted_at", "course_documents", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_course_documents_deleted_at", table_name="course_documents")
    op.drop_index("ix_course_documents_course_id", table_name="course_documents")
    op.drop_table("course_documents")
