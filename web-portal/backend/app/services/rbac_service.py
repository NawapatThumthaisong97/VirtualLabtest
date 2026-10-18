from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.models.enrollment import RoleInCourse
from app.models.user import User
from app.repositories.rbac_repository import RBACRepository


GLOBAL_PERMISSION_BY_DOMAIN_AND_ACTION = {
    ("clusters", "*"): "clusters:manage:global",
    ("kubernetes", "*"): "kubernetes:cluster_admin:global",
    ("network", "policies"): "network:policies:manage:global",
    ("network", "tailscale"): "network:tailscale:manage:global",
    ("network", "egress_allowlist"): "network:egress_allowlist:manage:global",
    ("storage", "images"): "storage:registry:manage:global",
    ("storage", "registry"): "storage:registry:manage:global",
    ("storage", "data"): "storage:r2:manage:global",
    ("storage", "datasets"): "storage:r2:manage:global",
    ("storage", "r2"): "storage:r2:manage:global",
    ("storage", "quotas"): "storage:quotas:manage:global",
    ("courses", "*"): "courses:manage:global",
    ("courses", "create"): "courses:manage:global",
    ("courses", "update"): "courses:manage:global",
    ("courses", "delete"): "courses:manage:global",
    ("courses", "announcements"): "courses:manage:global",
    ("metrics", "*"): "clusters:manage:global",
    ("logs", "*"): "clusters:manage:global",
}


def _parse_uuid(value: str | None) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


class RBACService:
    def has_permission(self, db: DbSession, user_id: UUID, permission_code: str) -> bool:
        if ":" not in permission_code:
            return False
        resource_domain, permission_name = permission_code.split(":", maxsplit=1)
        return RBACRepository(db).user_has_permission(
            user_id, resource_domain, permission_name
        )

    def has_global_permission(
        self,
        db: DbSession,
        user_id: UUID,
        permission_code: str,
    ) -> bool:
        permission_parts = permission_code.split(":")
        if len(permission_parts) < 2:
            return False
        resource_domain, permission_family = permission_parts[:2]
        global_code = GLOBAL_PERMISSION_BY_DOMAIN_AND_ACTION.get(
            (resource_domain, permission_family)
        ) or GLOBAL_PERMISSION_BY_DOMAIN_AND_ACTION.get((resource_domain, "*"))
        return global_code is not None and self.has_permission(
            db, user_id, global_code
        )


ResourceScopeChecker = Callable[[DbSession, UUID, str, UUID | None], bool]


class ResourceContextPolicy:
    def __init__(
        self,
        scope_checkers: dict[str, ResourceScopeChecker] | None = None,
    ) -> None:
        self.scope_checkers = scope_checkers or {}

    def allows(
        self,
        db: DbSession,
        user: User,
        resource_domain: str,
        scope: str,
        resource_id: str,
        course_id: UUID | None = None,
        action: str | None = None,
    ) -> bool:
        checker = self.scope_checkers.get(f"{resource_domain}:{scope}")
        if checker is not None:
            return checker(db, user.id, resource_id, course_id)

        repo = RBACRepository(db)

        if scope == "self" and resource_domain in {"clusters", "kubernetes", "network"}:
            return self._owns_cluster_or_session(repo, user.id, resource_id)

        # Course self scope - student can read enrolled courses, instructor can read teaching courses
        if scope == "self" and resource_domain == "courses":
            if action == "create":
                # Instructor can create courses - permission already checked in verify_permission
                return True
            target_course_id = _parse_uuid(resource_id)
            if target_course_id is None:
                return False
            return self._has_course_access(repo, user.id, target_course_id)

        # Course scope - instructor must be teaching this course
        if scope == "course" and resource_domain == "courses":
            target_course_id = _parse_uuid(resource_id)
            if target_course_id is None:
                return False
            return self._is_course_instructor(repo, user.id, target_course_id)

        if scope == "assigned" and resource_domain in {"kubernetes", "network"}:
            return repo.is_instructor_of_cluster(user.id, resource_id)

        if scope == "course" and resource_domain in {"clusters", "storage"}:
            if course_id is None:
                return False
            if resource_domain == "storage":
                if _parse_uuid(resource_id) != course_id:
                    return False
                return repo.is_enrolled_instructor_of_active_course(user.id, course_id)
            if action == "create":
                return repo.is_enrolled_instructor_of_active_course(user.id, course_id)
            return repo.is_instructor_of_cluster(user.id, resource_id, course_id=course_id)

        return False

    def _owns_cluster_or_session(
        self,
        repo: RBACRepository,
        user_id: UUID,
        resource_id: str,
    ) -> bool:
        session_id = _parse_uuid(resource_id)
        if session_id is None:
            return self._has_exclusive_cluster_owner(repo, user_id, resource_id)
        return repo.user_owns_session(user_id, session_id)

    @staticmethod
    def _has_exclusive_cluster_owner(
        repo: RBACRepository,
        user_id: UUID | None,
        cluster_name: str,
    ) -> bool:
        owners = repo.get_cluster_owner_ids(cluster_name)
        if len(owners) != 1:
            return False
        return user_id is None or owners[0] == user_id

    @staticmethod
    def _is_named_lecturer(repo: RBACRepository, user_id: UUID, lecturer_name: str) -> bool:
        # NOTE: จับคู่ด้วยชื่อแสดงผล ไม่ใช่ id ผู้ใช้ที่ชื่อซ้ำกับ lecturer_name จะได้สิทธิ์ด้วย
        user_name = repo.get_user_name(user_id)
        return user_name is not None and user_name == lecturer_name

    @classmethod
    def _has_course_access(cls, repo: RBACRepository, user_id: UUID, course_id: UUID) -> bool:
        """
        ตรวจสอบว่า user มีสิทธิ์เข้าถึง course นี้หรือไม่ (course ต้องยังไม่ถูกลบ)
        - Student: ต้อง enroll
        - Instructor: ต้องเป็นผู้สร้าง, ผู้สอน, หรือ enroll เป็น instructor
        """
        course = repo.find_active_course(course_id)
        if course is None:
            return False
        if course.created_by == user_id:
            return True
        if repo.is_enrolled(user_id, course_id):
            return True
        return cls._is_named_lecturer(repo, user_id, course.lecturer_name)

    @classmethod
    def _is_course_instructor(cls, repo: RBACRepository, user_id: UUID, course_id: UUID) -> bool:
        """
        ตรวจสอบว่า user เป็น instructor ของ course นี้หรือไม่ (course ต้องยังไม่ถูกลบ)
        - ต้องเป็นผู้สร้าง, ผู้สอน, หรือ enroll เป็น instructor
        """
        course = repo.find_active_course(course_id)
        if course is None:
            return False
        if course.created_by == user_id:
            return True
        if repo.is_enrolled(user_id, course_id, RoleInCourse.INSTRUCTOR):
            return True
        return cls._is_named_lecturer(repo, user_id, course.lecturer_name)
