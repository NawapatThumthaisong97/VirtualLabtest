from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.repositories.base import BaseRepository
from app.models.announcement import Announcement


class AnnouncementRepository(BaseRepository[Announcement]):
    model = Announcement

    def find_by_id(self, announcement_id: UUID) -> Announcement | None:
        result = select(self.model).where(self.model.id == announcement_id)
        return self.db.execute(result).scalar_one_or_none()

    def find_by_course_id(self, course_id: UUID) -> list[Announcement]:
        # joinedload author เพราะ response ต้องใช้ชื่อคนโพสต์ทุกแถว
        # ถ้าปล่อย lazy load จะยิง query เพิ่มอีก 1 ครั้งต่อ 1 ประกาศ (N+1)
        result = (
            select(self.model)
            .options(joinedload(self.model.author))
            .where(self.model.course_id == course_id)
            .order_by(self.model.created_at.desc())
        )
        return list(self.db.execute(result).scalars().all())
