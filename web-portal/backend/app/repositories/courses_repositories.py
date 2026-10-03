from uuid import UUID

from sqlalchemy import select

from app.repositories.base import BaseRepository
from app.models.courses import Course


class CourseRepository(BaseRepository[Course]):
    model = Course

    def find_by_id(self, course_id: UUID) -> Course | None:
        result = select(self.model).where(self.model.id == course_id)
        if hasattr(self.model, "deleted_at"):
            result = result.where(self.model.deleted_at.is_(None))
        return self.db.execute(result).scalar_one_or_none()

    def find_by_id_including_deleted(self, course_id: UUID) -> Course | None:
        result = select(self.model).where(self.model.id == course_id)
        return self.db.execute(result).scalar_one_or_none()

    def find_by_lecturer(self, lecturer_name: str) -> list[Course]:
        result = select(self.model).where(
            self.model.lecturer_name == lecturer_name,
            self.model.deleted_at.is_(None)
        )
        return list(self.db.execute(result).scalars().all())

    def find_by_creator(self, creator_id: UUID) -> list[Course]:
        """ดึงวิชาที่สร้างโดย user นี้"""
        result = select(self.model).where(
            self.model.created_by == creator_id,
            self.model.deleted_at.is_(None)
        )
        return list(self.db.execute(result).scalars().all())

    def find_by_student(self, student_id: UUID) -> list[Course]:
        from app.models.enrollment import Enrollment

        result = (
            select(self.model)
            .join(Enrollment, Enrollment.course_id == self.model.id)
            .where(
                Enrollment.user_id == student_id,
                # เส้นนี้กลายเป็นตัวหลักของหน้า /courses แล้ว วิชาที่ถูกซ่อนไว้
                # (soft delete) ต้องไม่โผล่กลับมาให้นักศึกษาเห็น
                self.model.deleted_at.is_(None),
            )
            .order_by(self.model.code)
        )
        return list(self.db.execute(result).scalars().all())

    def is_student_enrolled(self, course_id: UUID, student_id: UUID) -> bool:
        """ตรวจสอบว่านักศึกษาลงทะเบียนวิชานี้หรือไม่"""
        from app.models.enrollment import Enrollment

        result = select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == student_id
        )
        return self.db.execute(result).scalar_one_or_none() is not None

    def is_lecturer_teaching(self, course_id: UUID, lecturer_name: str) -> bool:
        """ตรวจสอบว่าอาจารย์สอนวิชานี้หรือไม่"""
        result = select(self.model).where(
            self.model.id == course_id,
            self.model.lecturer_name == lecturer_name
        )
        return self.db.execute(result).scalar_one_or_none() is not None
