from uuid import UUID
from typing import Optional

from sqlalchemy import exists, select

from app.models.class_schedule import ClassSchedule
from app.models.class_slot import ClassSlot
from app.models.lab import Lab
from app.models.lab_image import LabImage, ImageStatus
from app.models.session import Session as LabSession
from app.repositories.base import BaseRepository


class LabImageRepository(BaseRepository[LabImage]):
    model = LabImage

    def find_by_id(self, image_id: UUID, for_update: bool = False) -> Optional[LabImage]:
        """ดึง lab image ตาม ID (for_update=True -> ล็อกแถวจนจบ transaction กัน approve/reject ชนกัน)"""
        query = self.db.query(LabImage).filter(LabImage.id == image_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def is_referenced(self, image_id: UUID) -> bool:
        """มี lab / session / ตารางเรียน อ้างถึง image นี้อยู่ไหม

        ต้องเช็คเองก่อนลบ: relationship ของ LabImage ไม่มี cascade ถ้าลบเลย SQLAlchemy จะ
        เซ็ต FK ที่ nullable (เช่น labs.image_id) เป็น NULL เงียบๆ แทนที่จะ error
        """
        checks = (
            exists().where(Lab.image_id == image_id),
            exists().where(LabSession.lab_image_id == image_id),
            exists().where(ClassSlot.lab_image_id == image_id),
            exists().where(ClassSchedule.default_lab_image_id == image_id),
        )
        return any(self.db.query(check).scalar() for check in checks)

    def delete(self, image: LabImage) -> None:
        """ลบแถวจริง (hard delete) — flush เพื่อให้ FK violation เกิดตรงนี้ ยังไม่ commit"""
        self.db.delete(image)
        self.db.flush()

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

    def find_by_archive_key(self, archive_key: str) -> Optional[LabImage]:
        """ดึง lab image ตาม R2 object key (ใช้จับคู่ event จาก webhook)"""
        return self.db.query(LabImage).filter(LabImage.archive_key == archive_key).first()

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
