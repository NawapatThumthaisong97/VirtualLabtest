from uuid import UUID

from sqlalchemy import func , select

from app.repositories.base import BaseRepositories
from app.models.announcement import Announcement  

class AnnouncementRepository(BaseRepositories[Announcement]):
    model = Announcement
    
    def find_by_id(self, announcement_id: UUID) -> Announcement | None:
        result = select(self.model).where(self.model.id == announcement_id)
        return self.db.execute(result).scalar_one_or_none()
    
    def find_by_course_id(self, course_id: UUID) -> list[Announcement]:
        result = select(self.model).where(self.model.course_id == course_id)
        return self.db.execute(result).scalars().all()