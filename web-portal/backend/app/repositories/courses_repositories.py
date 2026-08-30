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
        result = select(self.model).where(self.model.lecturer_name == lecturer_name)
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
