"""
Fixture ฝั่ง DB สำหรับเทส course / announcement / RBAC ของ course

ใช้ Postgres เดียวกับ tests/session (virtual_lab_test) ดูรายละเอียดการตั้งค่าที่
tests/session/conftest.py — ที่นี่ประกาศ db_engine/db ซ้ำเพราะ pytest ไม่แชร์ fixture
ข้ามโฟลเดอร์ย่อยที่ไม่ได้อยู่ใต้ conftest เดียวกัน

เปลี่ยน DB ได้ด้วย env TEST_DATABASE_URL (ชื่อ DB ต้องลงท้ายด้วย _test กันลบข้อมูลจริง)
"""
import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  ให้ทุก table อยู่ใน Base.metadata
from app.configs.db import Base
from app.configs.settings import settings
from app.models.announcement import Announcement
from app.models.courses import Course
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.user import User, UserRole
from app.repositories.annoucement_repositories import AnnouncementRepository
from app.repositories.courses_repositories import CourseRepository
from app.repositories.rbac_repository import RBACRepository
from app.services.courses_service import CourseService
from app.services.rbac_service import RBACService, ResourceContextPolicy


def _test_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL") or make_url(settings.DATABASE_URL).set(
        database="virtual_lab_test"
    ).render_as_string(hide_password=False)
    if not make_url(url).database.endswith("_test"):
        raise RuntimeError(f"test DB name must end with _test: {make_url(url).database}")
    return url


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(_test_db_url())
    try:
        with engine.connect():
            pass
    except OperationalError as e:
        pytest.skip(f"test database not available: {e.orig}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def course_service(db):
    return CourseService(CourseRepository(db), AnnouncementRepository(db))


@pytest.fixture
def rbac_service():
    return RBACService()


@pytest.fixture
def course_policy():
    return ResourceContextPolicy()


@pytest.fixture
def rbac_repo(db):
    return RBACRepository(db)


@pytest.fixture
def world(db):
    """
    ข้อมูลตั้งต้น:
    - instructor: สร้าง course เอง (created_by)
    - lecturer: ไม่ได้ created_by/enroll แต่ชื่อตรงกับ course.lecturer_name
    - student: enroll เป็น student ใน course
    - other_user: ไม่เกี่ยวข้องกับ course เลย
    - course: วิชาที่ instructor สร้าง สอนโดย lecturer (ตามชื่อ)
    - deleted_course: วิชาเดียวกันแต่ soft deleted ไว้เช็ค regression
    """
    def make_user(name, role, email=None):
        user = User(
            email=email or f"{name.lower()}-{uuid.uuid4().hex[:8]}@test.local",
            name=name,
            role=role,
        )
        db.add(user)
        db.flush()
        return user

    instructor = make_user("Instructor One", UserRole.INSTRUCTOR)
    lecturer = make_user("Lecturer Name", UserRole.INSTRUCTOR)
    student = make_user("Student One", UserRole.STUDENT)
    other_user = make_user("Other User", UserRole.STUDENT)
    admin = make_user("Admin One", UserRole.ADMIN)

    course = Course(
        code=f"T{uuid.uuid4().hex[:6]}",
        name="Test course",
        lecturer_name=lecturer.name,
        created_by=instructor.id,
    )
    db.add(course)
    db.flush()

    enrollment = Enrollment(
        user_id=student.id,
        course_id=course.id,
        role_in_course=RoleInCourse.STUDENT,
    )
    db.add(enrollment)
    db.flush()

    deleted_course = Course(
        code=f"T{uuid.uuid4().hex[:6]}",
        name="Deleted course",
        lecturer_name=lecturer.name,
        created_by=instructor.id,
    )
    db.add(deleted_course)
    db.flush()
    from datetime import datetime, timezone
    deleted_course.deleted_at = datetime.now(timezone.utc)
    db.flush()

    db.commit()

    return SimpleNamespace(
        instructor=instructor,
        lecturer=lecturer,
        student=student,
        other_user=other_user,
        admin=admin,
        course=course,
        deleted_course=deleted_course,
    )


@pytest.fixture
def add_announcement(db):
    """สร้าง announcement ลง DB ตรง ๆ"""
    def _add(course, author, message="Hello"):
        announcement = Announcement(course_id=course.id, author_id=author.id, message=message)
        db.add(announcement)
        db.commit()
        return announcement
    return _add
