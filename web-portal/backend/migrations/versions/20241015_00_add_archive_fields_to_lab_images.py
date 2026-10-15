"""Add R2 archive fields to lab_images

Revision ID: 20241015_00_add_archive_fields_to_lab_images
Revises: 20261013_06_add_end_reason_to_sessions
Create Date: 2024-10-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20241015_00_add_archive_fields_to_lab_images'
down_revision = '20261013_06_add_end_reason_to_sessions'
branch_labels = None
depends_on = None


def upgrade():
    """Add R2 archive metadata fields to lab_images table"""
    
    # Add archive_key - R2 object key of .tar archive
    op.add_column('lab_images', 
        sa.Column('archive_key', sa.String(500), nullable=True,
                  comment='R2 object key of Docker image .tar archive'))
    
    # Add archive_etag - R2 ETag for integrity verification
    op.add_column('lab_images',
        sa.Column('archive_etag', sa.String(255), nullable=True,
                  comment='R2 ETag (MD5 hash) for integrity verification'))
    
    # Add archive_size_bytes - Size of archive file
    op.add_column('lab_images',
        sa.Column('archive_size_bytes', sa.BigInteger, nullable=True,
                  comment='Size of .tar archive on R2 in bytes'))
    
    # Add archive_uploaded_at - Upload timestamp
    op.add_column('lab_images',
        sa.Column('archive_uploaded_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Timestamp when archive was uploaded to R2'))


def downgrade():
    """Remove R2 archive metadata fields from lab_images table"""
    
    op.drop_column('lab_images', 'archive_uploaded_at')
    op.drop_column('lab_images', 'archive_size_bytes')
    op.drop_column('lab_images', 'archive_etag')
    op.drop_column('lab_images', 'archive_key')
