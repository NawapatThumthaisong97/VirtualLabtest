"""
กลุ่ม 3: ResourceContextPolicy / RBACService สำหรับ resource_domain = courses

ครอบคลุม scope "self" (courses:read:self) และ "course" (courses:update:course,
courses:delete:course) ที่ใช้ RBACRepository เป็น query layer
"""
import uuid

import pytest


class TestCoursesSelfScope:
    """ResourceContextPolicy.allows — courses / self scope"""

    def test_create_action_always_allowed(self, course_policy, db, world):
        """action=create is always allowed (permission already checked upstream)"""
        assert course_policy.allows(
            db, world.student, "courses", "self", "anything", action="create"
        ) is True

    def test_creator_instructor_has_access(self, course_policy, db, world):
        """Instructor who created the course can read it"""
        assert course_policy.allows(
            db, world.instructor, "courses", "self", str(world.course.id), action="read"
        ) is True

    def test_enrolled_student_has_access(self, course_policy, db, world):
        """Enrolled student can read the course"""
        assert course_policy.allows(
            db, world.student, "courses", "self", str(world.course.id), action="read"
        ) is True

    def test_named_lecturer_has_access(self, course_policy, db, world):
        """A user whose name matches lecturer_name can read the course"""
        assert course_policy.allows(
            db, world.lecturer, "courses", "self", str(world.course.id), action="read"
        ) is True

    def test_unrelated_user_has_no_access(self, course_policy, db, world):
        """A user with no relation to the course cannot read it"""
        assert course_policy.allows(
            db, world.other_user, "courses", "self", str(world.course.id), action="read"
        ) is False

    def test_invalid_resource_id_is_denied(self, course_policy, db, world):
        """A malformed course id (not a UUID) is denied, not a 500"""
        assert course_policy.allows(
            db, world.student, "courses", "self", "not-a-uuid", action="read"
        ) is False

    def test_regression_deleted_course_denies_access(self, course_policy, db, world):
        """Regression: a soft deleted course is not readable even by its creator

        เดิม _has_course_access ไม่เช็ค deleted_at ของ course ทำให้ user ที่ enroll /
        สร้างไว้ยังเข้าถึง course ที่ถูกลบไปแล้วได้
        """
        assert course_policy.allows(
            db, world.instructor, "courses", "self", str(world.deleted_course.id), action="read"
        ) is False


class TestCoursesCourseScope:
    """ResourceContextPolicy.allows — courses / course scope (update, delete, announcements)"""

    def test_creator_instructor_is_allowed(self, course_policy, db, world):
        """Instructor who created the course may update/delete it"""
        assert course_policy.allows(
            db, world.instructor, "courses", "course", str(world.course.id), action="update"
        ) is True

    def test_named_lecturer_is_allowed(self, course_policy, db, world):
        """A user whose name matches lecturer_name is treated as instructor"""
        assert course_policy.allows(
            db, world.lecturer, "courses", "course", str(world.course.id), action="update"
        ) is True

    def test_student_is_denied(self, course_policy, db, world):
        """A student (even if enrolled) cannot update/delete the course"""
        assert course_policy.allows(
            db, world.student, "courses", "course", str(world.course.id), action="update"
        ) is False

    def test_unrelated_instructor_is_denied(self, course_policy, db, world):
        """An instructor with no relation to the course is denied"""
        assert course_policy.allows(
            db, world.other_user, "courses", "course", str(world.course.id), action="delete"
        ) is False

    def test_regression_deleted_course_denies_instructor(self, course_policy, db, world):
        """Regression: creator instructor loses course-scope access once the course is deleted"""
        assert course_policy.allows(
            db,
            world.instructor,
            "courses",
            "course",
            str(world.deleted_course.id),
            action="update",
        ) is False


class TestHasPermission:
    """RBACService.has_permission / has_global_permission — malformed input handling"""

    def test_malformed_code_without_colon_returns_false(self, rbac_service, db, world):
        """Regression: a permission code without ':' returns False instead of raising"""
        assert rbac_service.has_permission(db, world.student.id, "no-colon-here") is False

    def test_unknown_user_has_no_permission(self, rbac_service, db):
        """A user with no role assignment has no permission"""
        assert rbac_service.has_permission(db, uuid.uuid4(), "courses:read:self") is False

    def test_global_permission_short_code_returns_false(self, rbac_service, db, world):
        """A permission code with fewer than 2 parts never matches a global permission"""
        assert rbac_service.has_global_permission(db, world.student.id, "courses") is False
