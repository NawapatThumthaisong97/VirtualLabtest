from uuid import UUID

from sqlalchemy import func , select

from app.repositories.base import BaseRepositories
from app.models.file import File

class FileRepository(BaseRepositories[File]):
    model = File

    def find_by_id(self, file_id: UUID) -> File | None:
        result = select(self.model).where(self.model.id == file_id)
        return self.db.execute(result).scalar_one_or_none()
    
    def find_by_course_id(self, course_id: UUID) -> list[File]:
        result = select(self.model).where(self.model.course_id == course_id)
        return self.db.execute(result).scalars().all()