from uuid import UUID

from sqlalchemy import and_, func, select

from app.models.lab import Lab, LabStatus
from app.models.lab_progress import LabProgress, ProgressStatus
from app.repositories.base import BaseRepository


class LabRepository(BaseRepository[Lab]):
    model = Lab

    def find_by_course(
        self, course_id: UUID, status: LabStatus | None = None
    ) -> list[Lab]:
        # Bussiness Logic
        result = (
            select(Lab)
            .where(Lab.course_id == course_id, Lab.deleted_at.is_(None))
            .order_by(Lab.order_no)
        )
        if status is not None:
            result = result.where(Lab.status == status)
        return list(self.db.execute(result).scalars().all())

    def find_by_course_with_progress(
        self, course_id: UUID, user_id: UUID, status: LabStatus | None = None
    ) -> list[tuple[Lab, ProgressStatus | None]]:
        """
        lab ของวิชาหนึ่ง พร้อมสถานะความคืบหน้าของผู้ใช้คนนี้

        outer join เพราะ lab ที่ผู้ใช้ยังไม่เคยแตะจะไม่มีแถวใน lab_progress
        ถ้า inner join lab พวกนั้นจะหายไปจากตารางเลย
        """
        result = (
            select(Lab, LabProgress.status)
            .outerjoin(
                LabProgress,
                and_(LabProgress.lab_id == Lab.id, LabProgress.user_id == user_id),
            )
            .where(Lab.course_id == course_id, Lab.deleted_at.is_(None))
            .order_by(Lab.order_no)
        )
        if status is not None:
            result = result.where(Lab.status == status)
        return [(row[0], row[1]) for row in self.db.execute(result).all()]
