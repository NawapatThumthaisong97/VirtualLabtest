from uuid import UUID

from sqlalchemy import func , select

from app.repositories.base import BaseRepositories
from app.models.course import Course  

class CourseRepository(BaseRepositories[Course]):
    model = Course

    def find_by_id(self, course_id: UUID) -> Course | None:
        result = select(self.model).where(self.model.id == course_id)
        if hasattr(self.model, "deleted_at"):
            result = result.where(self.model.deleted_at.is_(None))
        return self.db.execute(result).scalar_one_or_none()