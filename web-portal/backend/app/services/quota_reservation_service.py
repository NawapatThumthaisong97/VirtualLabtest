from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.exceptions.domain import QuotaExceededError
from app.models.quota import Quota, QuotaPeriod
from app.models.quota_reservation import QuotaReservation


class QuotaReservationService:
    ACTIVE_STATUSES = ("reserved", "committed")

    def __init__(self, db: Session):
        self.db = db

    def reserve_personal_cluster(
        self,
        user_id: UUID,
        compute_hours: Decimal,
        storage_mb: int,
    ) -> list[UUID]:
        if compute_hours <= 0 or storage_mb <= 0:
            raise ValueError("Cluster quota reservation must be positive")

        now = datetime.now(timezone.utc)
        try:
            quotas = (
                self.db.query(Quota)
                .filter(Quota.user_id == user_id, Quota.course_id.is_(None))
                .order_by(Quota.id)
                .with_for_update()
                .all()
            )
            if not quotas:
                raise QuotaExceededError("ไม่พบ quota สำหรับผู้ใช้นี้")

            reservations = []
            for quota in quotas:
                reserved_compute, reserved_storage = self._reserved_totals(
                    quota.id, now
                )
                if (
                    reserved_compute + compute_hours > quota.compute_hours_limit
                    or reserved_storage + storage_mb > quota.storage_mb_limit
                ):
                    raise QuotaExceededError("quota สำหรับ personal cluster เต็มแล้ว")

                reservations.append(
                    QuotaReservation(
                        quota_id=quota.id,
                        user_id=user_id,
                        compute_hours=compute_hours,
                        storage_mb=storage_mb,
                        period_end_at=self._period_end(quota.period, now),
                        status="reserved",
                    )
                )

            self.db.add_all(reservations)
            self.db.flush()
            reservation_ids = [reservation.id for reservation in reservations]
            self.db.commit()
            return reservation_ids
        except Exception:
            self.db.rollback()
            raise

    def mark_committed(self, reservation_ids: list[UUID]) -> None:
        self.db.query(QuotaReservation).filter(
            QuotaReservation.id.in_(reservation_ids),
            QuotaReservation.status == "reserved",
        ).update(
            {QuotaReservation.status: "committed"}, synchronize_session=False
        )

    def release(self, reservation_ids: list[UUID]) -> None:
        try:
            self.db.query(QuotaReservation).filter(
                QuotaReservation.id.in_(reservation_ids),
                QuotaReservation.status == "reserved",
            ).update(
                {QuotaReservation.status: "released"}, synchronize_session=False
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _reserved_totals(self, quota_id: UUID, now: datetime) -> tuple[Decimal, int]:
        totals = (
            self.db.query(
                func.coalesce(func.sum(QuotaReservation.compute_hours), 0),
                func.coalesce(func.sum(QuotaReservation.storage_mb), 0),
            )
            .filter(
                QuotaReservation.quota_id == quota_id,
                QuotaReservation.status.in_(self.ACTIVE_STATUSES),
                QuotaReservation.period_end_at > now,
            )
            .one()
        )
        return Decimal(totals[0]), int(totals[1])

    @staticmethod
    def _period_end(period: QuotaPeriod, now: datetime) -> datetime:
        if period is QuotaPeriod.WEEKLY:
            days_until_monday = 7 - now.weekday()
            return (now + timedelta(days=days_until_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        if period is QuotaPeriod.MONTHLY:
            if now.month == 12:
                return now.replace(
                    year=now.year + 1, month=1, day=1, hour=0, minute=0,
                    second=0, microsecond=0,
                )
            return now.replace(
                month=now.month + 1, day=1, hour=0, minute=0, second=0,
                microsecond=0,
            )
        if period is QuotaPeriod.SEMESTER:
            semester_end_month = 7 if now.month <= 6 else 1
            year = now.year if semester_end_month == 7 else now.year + 1
            return now.replace(
                year=year, month=semester_end_month, day=1, hour=0, minute=0,
                second=0, microsecond=0,
            )
        raise ValueError(f"Unsupported quota period: {period}")