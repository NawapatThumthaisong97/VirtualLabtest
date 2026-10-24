from sqlalchemy import Column, Date, Numeric, DateTime
from sqlalchemy.sql import func
from app.configs.db import Base


class AwsDailyCost(Base):
    """ยอด AWS จริงรายวัน (UTC) จาก Cost Explorer เฉพาะ resource ที่มี tag ของ lab — หน้า admin billing (PR 4)

    ก่อนหัก credit / refund (บัญชีใช้ credit ยอดหลังหักเป็น 0 ตลอด) อัปเดตทับวันละครั้ง (ยอดล่าสุดของ AWS ขยับได้ 1–2 วัน)
    """
    __tablename__ = "aws_daily_costs"

    day = Column(Date, primary_key=True)
    cost_usd = Column(Numeric(precision=12, scale=6), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
