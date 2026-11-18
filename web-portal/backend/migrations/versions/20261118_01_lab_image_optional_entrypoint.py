"""lab_images.entrypoint_script nullable: ว่าง = ใช้ ENTRYPOINT / CMD ของ image (docs/LAB_IMAGE_UPLOAD_PLAN.md ข้อ 3.3)

Revision ID: 20261118_01
Revises: 20261111_01
Create Date: 2026-11-18

เดิมคอลัมน์เป็น NOT NULL และ API ใส่ "/bin/bash /run.sh" ให้ถ้าไม่ส่งมา ทำให้ image ที่ไม่มี /run.sh เปิดไม่ขึ้น
แถวเดิมไม่แปลง: image เก่าที่เก็บ "/bin/bash /run.sh" ไว้ก็รันแบบเดิมต่อไป
"""
import sqlalchemy as sa
from alembic import op

revision = "20261118_01"
down_revision = "20261111_01"
branch_labels = None
depends_on = None

# ค่าที่ API เคยใส่ให้ ใช้ตอน downgrade เติมแถวที่เป็น NULL ก่อนกลับไปเป็น NOT NULL
LEGACY_DEFAULT = "/bin/bash /run.sh"


def upgrade() -> None:
    op.alter_column("lab_images", "entrypoint_script", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    # แถวที่ว่างจะกลับไปรัน /bin/bash /run.sh ซึ่งไม่ใช่พฤติกรรมเดิมของแถวนั้น แต่ NOT NULL บังคับให้ต้องมีค่า
    op.execute(
        sa.text("UPDATE lab_images SET entrypoint_script = :value WHERE entrypoint_script IS NULL")
        .bindparams(value=LEGACY_DEFAULT)
    )
    op.alter_column("lab_images", "entrypoint_script", existing_type=sa.String(255), nullable=False)
