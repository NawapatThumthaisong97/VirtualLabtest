from uuid import UUID 

from sqlalchemy import func , select

from app.models.lab import Lab, LabStatus
from app.repositories.base import BaseRepository

class LabRepository(BaseRepository[Lab]):
    model = Lab

    def find_by_course(self, course_id: UUID, status: LabStatus | None = None) -> list[Lab]:
        #Bussiness Logic
        result = (
        select(Lab)
        .where(
            Lab.course_id == course_id,
            Lab.deleted_at.is_(None)
        )
        .order_by(Lab.order_no)
        )
        if status is not None:
            result = result.where(Lab.status == status)
        return list(self.db.execute(result).scalars().all())
