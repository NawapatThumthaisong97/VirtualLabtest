from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.models.courses import Course
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import Lab
from app.models.rbac import Permission, Role, RolePermission, UserRoleAssignment
from app.models.session import Session as ComputeSession
from app.models.user import User


class RBACRepository:
    """Query ที่ใช้ตรวจสิทธิ์ (role/permission และ resource context) ทั้งหมดอยู่ที่นี่"""

    def __init__(self, db: Session):
        self.db = db

    def _exists(self, stmt) -> bool:
        return self.db.execute(stmt.limit(1)).first() is not None

    # ------------------------------------------------------------ role / permission

    def user_has_permission(
        self, user_id: UUID, resource_domain: str, permission_name: str
    ) -> bool:
        """user มี role ที่ active และผูกกับ permission นี้ (ทุกแถวต้องยังไม่ถูก soft delete)"""
        stmt = (
            select(Role.id)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.deleted_at.is_(None),
                Role.is_active.is_(True),
                Role.deleted_at.is_(None),
                RolePermission.deleted_at.is_(None),
                Permission.resource_domain == resource_domain,
                Permission.permission_name == permission_name,
                Permission.is_active.is_(True),
                Permission.deleted_at.is_(None),
            )
        )
        return self._exists(stmt)

    # ------------------------------------------------------------ compute session / cluster

    def user_owns_session(self, user_id: UUID, session_id: UUID) -> bool:
        stmt = select(ComputeSession.id).where(
            ComputeSession.id == session_id,
            ComputeSession.user_id == user_id,
            ComputeSession.deleted_at.is_(None),
        )
        return self._exists(stmt)

    def get_cluster_owner_ids(self, cluster_name: str) -> list[UUID]:
        """user_id ที่ไม่ซ้ำกันของ session ที่ยังไม่ถูกลบบน cluster นี้"""
        stmt = (
            select(ComputeSession.user_id)
            .where(
                ComputeSession.sky_cluster_name == cluster_name,
                ComputeSession.deleted_at.is_(None),
            )
            .distinct()
        )
        return list(self.db.execute(stmt).scalars().all())

    def is_instructor_of_cluster(
        self,
        user_id: UUID,
        cluster_name: str,
        course_id: UUID | None = None,
    ) -> bool:
        """
        user เป็น instructor ของวิชาที่ lab ของ session บน cluster นี้สังกัดอยู่
        และ cluster ต้องมีเจ้าของคนเดียว (ไม่มี session ของ user อื่นบน cluster เดียวกัน)
        ส่ง course_id มาเพื่อบังคับว่า lab ต้องอยู่ในวิชานั้นเท่านั้น
        """
        other_session = aliased(ComputeSession)
        has_conflicting_owner = exists().where(
            other_session.sky_cluster_name == ComputeSession.sky_cluster_name,
            other_session.deleted_at.is_(None),
            other_session.user_id != ComputeSession.user_id,
        )
        stmt = (
            select(ComputeSession.id)
            .join(Lab, Lab.id == ComputeSession.lab_id)
            .join(Enrollment, Enrollment.course_id == Lab.course_id)
            .where(
                ComputeSession.sky_cluster_name == cluster_name,
                ComputeSession.deleted_at.is_(None),
                Lab.deleted_at.is_(None),
                Enrollment.user_id == user_id,
                Enrollment.role_in_course == RoleInCourse.INSTRUCTOR,
                ~has_conflicting_owner,
            )
        )
        if course_id is not None:
            stmt = stmt.where(Lab.course_id == course_id)
        return self._exists(stmt)

    # ------------------------------------------------------------ course

    def find_active_course(self, course_id: UUID) -> Course | None:
        stmt = select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
        return self.db.execute(stmt).scalar_one_or_none()

    def is_enrolled(
        self,
        user_id: UUID,
        course_id: UUID,
        role_in_course: RoleInCourse | None = None,
    ) -> bool:
        stmt = select(Enrollment.user_id).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
        )
        if role_in_course is not None:
            stmt = stmt.where(Enrollment.role_in_course == role_in_course)
        return self._exists(stmt)

    def is_enrolled_instructor_of_active_course(
        self, user_id: UUID, course_id: UUID
    ) -> bool:
        stmt = (
            select(Course.id)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(
                Course.id == course_id,
                Course.deleted_at.is_(None),
                Enrollment.user_id == user_id,
                Enrollment.role_in_course == RoleInCourse.INSTRUCTOR,
            )
        )
        return self._exists(stmt)

    # ------------------------------------------------------------ user

    def get_user_name(self, user_id: UUID) -> str | None:
        stmt = select(User.name).where(User.id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()
