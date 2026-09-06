from uuid import UUID
from typing import Optional

from sqlalchemy import select

from app.models.lab_image import LabImage, ImageStatus
from app.repositories.base import BaseRepository


class LabImageRepository(BaseRepository[LabImage]):
    model = LabImage

    def find_by_id(self, image_id: UUID) -> Optional[LabImage]:
        """ดึง lab image ตาม ID"""
        return self.db.query(LabImage).filter(LabImage.id == image_id).first()

    def find_by_repository_and_tag(self, repository: str, tag: str) -> Optional[LabImage]:
        """ดึง lab image ตาม repository และ tag"""
        return (
            self.db.query(LabImage)
            .filter(
                LabImage.repository == repository,
                LabImage.tag == tag
            )
            .first()
        )

    def find_by_course(self, course_id: UUID, status: Optional[ImageStatus] = None) -> list[LabImage]:
        """ดึง lab images ทั้งหมดของ course"""
        query = (
            select(LabImage)
            .where(LabImage.course_id == course_id)
            .order_by(LabImage.created_at.desc())
        )
        
        if status is not None:
            query = query.where(LabImage.status == status)
        
        return list(self.db.execute(query).scalars().all())

    def find_approved_images(self, course_id: Optional[UUID] = None) -> list[LabImage]:
        """ดึง approved images (optionally filter by course)"""
        query = select(LabImage).where(LabImage.status == ImageStatus.APPROVED)
        
        if course_id is not None:
            query = query.where(LabImage.course_id == course_id)
        
        return list(self.db.execute(query).scalars().all())
