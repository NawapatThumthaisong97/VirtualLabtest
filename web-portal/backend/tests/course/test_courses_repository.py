"""
กลุ่ม 1: CourseRepository — query ตรงต่อ DB
"""
import uuid

from app.repositories.courses_repositories import CourseRepository


class TestFindById:
    """find_by_id / find_by_id_including_deleted"""

    def test_active_course_found(self, db, world):
        """Active course is returned"""
        repo = CourseRepository(db)
        found = repo.find_by_id(world.course.id)
        assert found is not None
        assert found.id == world.course.id

    def test_deleted_course_not_found(self, db, world):
        """find_by_id excludes soft deleted courses"""
        repo = CourseRepository(db)
        assert repo.find_by_id(world.deleted_course.id) is None

    def test_deleted_course_found_including_deleted(self, db, world):
        """find_by_id_including_deleted still returns soft deleted courses"""
        repo = CourseRepository(db)
        found = repo.find_by_id_including_deleted(world.deleted_course.id)
        assert found is not None
        assert found.id == world.deleted_course.id

    def test_unknown_id_returns_none(self, db):
        """Unknown course id returns None, not an error"""
        repo = CourseRepository(db)
        assert repo.find_by_id(uuid.uuid4()) is None


class TestFindByCreator:
    """find_by_creator"""

    def test_returns_only_active_courses_by_creator(self, db, world):
        """Only active courses created by the user are returned"""
        repo = CourseRepository(db)
        courses = repo.find_by_creator(world.instructor.id)
        ids = {c.id for c in courses}
        assert world.course.id in ids
        assert world.deleted_course.id not in ids

    def test_other_user_has_no_courses(self, db, world):
        """A user who created nothing gets an empty list"""
        repo = CourseRepository(db)
        assert repo.find_by_creator(world.other_user.id) == []


class TestFindByLecturer:
    """find_by_lecturer"""

    def test_matches_by_lecturer_name(self, db, world):
        """Courses taught by this lecturer name are returned"""
        repo = CourseRepository(db)
        courses = repo.find_by_lecturer(world.lecturer.name)
        ids = {c.id for c in courses}
        assert world.course.id in ids

    def test_excludes_deleted_courses(self, db, world):
        """Deleted courses with a matching lecturer name are excluded"""
        repo = CourseRepository(db)
        courses = repo.find_by_lecturer(world.lecturer.name)
        ids = {c.id for c in courses}
        assert world.deleted_course.id not in ids


class TestIsStudentEnrolled:
    """is_student_enrolled"""

    def test_enrolled_student_is_true(self, db, world):
        """Enrolled student returns True"""
        repo = CourseRepository(db)
        assert repo.is_student_enrolled(world.course.id, world.student.id) is True

    def test_not_enrolled_user_is_false(self, db, world):
        """A user who never enrolled returns False"""
        repo = CourseRepository(db)
        assert repo.is_student_enrolled(world.course.id, world.other_user.id) is False


class TestIsLecturerTeaching:
    """is_lecturer_teaching"""

    def test_matching_lecturer_name_is_true(self, db, world):
        """Lecturer name matching the course returns True"""
        repo = CourseRepository(db)
        assert repo.is_lecturer_teaching(world.course.id, world.lecturer.name) is True

    def test_non_matching_name_is_false(self, db, world):
        """A different name returns False"""
        repo = CourseRepository(db)
        assert repo.is_lecturer_teaching(world.course.id, "Someone Else") is False

    def test_regression_deleted_course_is_false(self, db, world):
        """Regression: a soft deleted course no longer grants lecturer access

        เดิม is_lecturer_teaching ไม่กรอง deleted_at ทำให้ instructor ที่ชื่อตรงกับ
        lecturer_name ยังเข้าถึง course ที่ถูกลบไปแล้วได้ผ่าน check_course_access
        """
        repo = CourseRepository(db)
        assert repo.is_lecturer_teaching(world.deleted_course.id, world.lecturer.name) is False
