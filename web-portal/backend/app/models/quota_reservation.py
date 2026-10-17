import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.configs.db import Base


class QuotaReservation(Base):
    __tablename__ = "quota_reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved', 'committed', 'released')",
            name="ck_quota_reservations_status",
        ),
        CheckConstraint("compute_hours > 0", name="ck_quota_reservations_compute_positive"),
        CheckConstraint("storage_mb > 0", name="ck_quota_reservations_storage_positive"),
        Index("ix_quota_reservations_quota_period", "quota_id", "period_end_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quota_id = Column(
        UUID(as_uuid=True),
        ForeignKey("quotas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    compute_hours = Column(Numeric(10, 2), nullable=False)
    storage_mb = Column(Integer, nullable=False)
    period_end_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, default="reserved", server_default="reserved")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )