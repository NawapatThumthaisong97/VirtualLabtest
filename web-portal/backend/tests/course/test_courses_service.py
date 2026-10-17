"""
กลุ่ม 2: CourseService — business logic เหนือ repository (create/update/delete course, announcements)
"""
import uuid

import pytest

from app.exceptions.domain import (
    ConflictError,
    CourseNotFoundError,
    ValidationError,
)
from app.models.courses import Course


class TestCreateCourse:
    """create_course"""

    def test_creates_course(self, course_service, db, world):
        """A new course is persisted with the given creator"""
        course = Course(
            code=f"NEW{uuid.uuid4().hex[:6]}",
            name="Brand new course",
            lecturer_name="Someone",
            created_by=world.instructor.id,
        )
        created = course_service.create_course(course)
        assert created.id is not None
        assert course_service.course_repository.find_by_id(created.id) is not None

    def test_duplicate_code_raises_conflict(self, course_service, world):
        """Reusing an existing course code raises ConflictError, not a raw DB error"""
        duplicate = Course(
            code=world.course.code,
            name="Duplicate code course",
            lecturer_name="Someone",
            created_by=world.instructor.id,
        )
        with pytest.raises(ConflictError):
            course_service.create_course(duplicate)


class TestGetCourseById:
    """get_course_by_id"""

    def test_found(self, course_service, world):
        """Existing course is returned"""
        course = course_service.get_course_by_id(world.course.id)
        assert course.id == world.course.id

    def test_unknown_raises_not_found(self, course_service):
        """Unknown course id raises CourseNotFoundError"""
        with pytest.raises(CourseNotFoundError):
            course_service.get_course_by_id(uuid.uuid4())

    def test_deleted_course_raises_not_found(self, course_service, world):
        """Soft deleted course is treated as not found"""
        with pytest.raises(CourseNotFoundError):
            course_service.get_course_by_id(world.deleted_course.id)


class TestCheckCourseAccess:
    """check_course_access"""

    def test_admin_always_has_access(self, course_service, world):
        """Admin can access any course regardless of enrollment"""
        from app.models.user import UserRole
        assert course_service.check_course_access(
            world.course.id, world.admin.id, UserRole.ADMIN, world.admin.name
        ) is True

    def test_instructor_creator_has_access(self, course_service, world):
        """Instructor who created the course has access"""
        from app.models.user import UserRole
        assert course_service.check_course_access(
            world.course.id, world.instructor.id, UserRole.INSTRUCTOR, world.instructor.name
        ) is True

    def test_instructor_matching_lecturer_name_has_access(self, course_service, world):
        """Instructor whose name matches lecturer_name has access even without enrollment"""
        from app.models.user import UserRole
        assert course_service.check_course_access(
            world.course.id, world.lecturer.id, UserRole.INSTRUCTOR, world.lecturer.name
        ) is True

    def test_unrelated_instructor_has_no_access(self, course_service, world):
        """Instructor with no relation to the course has no access"""
        from app.models.user import UserRole
        assert course_service.check_course_access(
            world.course.id, world.other_user.id, UserRole.INSTRUCTOR, "Nobody"
        ) is False

    def test_enrolled_student_has_access(self, course_service, world):
        """Enrolled student has access"""
        from app.models.user import UserRole
        assert course_service.check_course_access(
            world.course.id, world.student.id, UserRole.STUDENT, world.student.name
        ) is True

    def test_unenrolled_student_has_no_access(self, course_service, world):
        """Student who never enrolled has no access"""
        from app.models.user import UserRole
        assert course_service.check_course_access(
            world.course.id, world.other_user.id, UserRole.STUDENT, world.other_user.name
        ) is False


class TestAnnouncements:
    """create / update / delete announcement"""

    def test_create_announcement(self, course_service, db, world):
        """Announcement is created under the given course"""
        announcement = course_service.create_announcement(
            world.course.id, "Welcome!", world.instructor.id
        )
        assert announcement.course_id == world.course.id
        assert announcement.message == "Welcome!"

    def test_create_announcement_unknown_course_raises(self, course_service, world):
        """Creating an announcement under an unknown course raises CourseNotFoundError"""
        with pytest.raises(CourseNotFoundError):
            course_service.create_announcement(uuid.uuid4(), "Hi", world.instructor.id)

    def test_create_announcement_empty_message_raises(self, course_service, world):
        """Blank message raises ValidationError"""
        with pytest.raises(ValidationError):
            course_service.create_announcement(world.course.id, "   ", world.instructor.id)

    def test_update_announcement(self, course_service, world, add_announcement):
        """Announcement message is updated"""
        announcement = add_announcement(world.course, world.instructor, "Old")
        updated = course_service.update_announcement(
            world.course.id, announcement.id, "New message"
        )
        assert updated.message == "New message"

    def test_update_announcement_from_other_course_raises(
        self, course_service, world, add_announcement
    ):
        """Updating an announcement that belongs to a different course raises ValidationError"""
        other_course = Course(
            code=f"OTH{uuid.uuid4().hex[:6]}",
            name="Other course",
            lecturer_name="Someone",
            created_by=world.instructor.id,
        )
        course_service.course_repository.db.add(other_course)
        course_service.course_repository.db.flush()
        announcement = add_announcement(other_course, world.instructor, "Belongs elsewhere")

        with pytest.raises(ValidationError):
            course_service.update_announcement(world.course.id, announcement.id, "Hijack")

    def test_delete_announcement(self, course_service, world, add_announcement):
        """Announcement belonging to the course is deleted"""
        announcement = add_announcement(world.course, world.instructor, "Bye")
        course_service.delete_announcement(world.course.id, announcement.id)
        assert course_service.announcement_repository.find_by_id(announcement.id) is None

    def test_delete_announcement_unknown_raises_not_found(self, course_service, world):
        """Deleting an unknown announcement raises CourseNotFoundError"""
        with pytest.raises(CourseNotFoundError):
            course_service.delete_announcement(world.course.id, uuid.uuid4())

    def test_regression_cross_course_delete_is_rejected(
        self, course_service, world, add_announcement
    ):
        """Regression: deleting another course's announcement via this course_id is rejected

        เดิม route delete_announcement ไม่เช็คว่า announcement เป็นของ course_id ใน path
        จริงหรือไม่ ทำให้ instructor ของวิชา A ลบ announcement ของวิชา B ได้ถ้ารู้ id
        """
        other_course = Course(
            code=f"OTH{uuid.uuid4().hex[:6]}",
            name="Other course",
            lecturer_name="Someone",
            created_by=world.instructor.id,
        )
        course_service.course_repository.db.add(other_course)
        course_service.course_repository.db.flush()
        announcement = add_announcement(other_course, world.instructor, "Belongs elsewhere")

        with pytest.raises(ValidationError):
            course_service.delete_announcement(world.course.id, announcement.id)

        # announcement ของ course อื่นต้องยังอยู่ ไม่ถูกลบไปด้วย
        assert course_service.announcement_repository.find_by_id(announcement.id) is not None
