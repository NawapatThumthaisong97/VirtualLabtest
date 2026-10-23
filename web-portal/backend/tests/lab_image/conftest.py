"""
Fixture สำหรับเทส upload lab image (.tar) ขึ้น R2 + webhook

- ใช้ Postgres virtual_lab_test ผ่าน fixture `db` ใน tests/conftest.py (rollback ทุกเทส)
- R2 ใช้ `fake_r2` (tests/fakes.py) ไม่ต่อ Cloudflare จริง
- client ใช้ app จริงจาก app.main เพื่อให้ exception handler / validation handler เป็นตัวเดียวกับ production
"""
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.configs.db import get_db
from app.configs.settings import settings
from app.controllers.lab_image_controller import LabImageController
from app.models.courses import Course
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.user import User, UserRole
from app.repositories.lab_image_repository import LabImageRepository
from app.repositories.user_repository import UserRepository
from app.seeds.rbac_seed import RBACSeeder
from app.services.auth_service import AuthService
from app.services.lab_image_service import LabImageService
from tests.fakes import FakeR2

WEBHOOK_SECRET = "test-webhook-secret"
APPROVE_SECRET = "test-approve-secret"


@pytest.fixture(autouse=True)
def r2_settings(monkeypatch):
    monkeypatch.setattr(settings, "R2_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "LAB_IMAGE_APPROVE_WEBHOOK_SECRET", APPROVE_SECRET)
    monkeypatch.setattr(settings, "R2_PRESIGN_EXPIRES_SECONDS", 900)


@pytest.fixture
def fake_r2():
    return FakeR2()


@pytest.fixture
def client(db, fake_r2):
    from app.main import app
    from app.routes.lab_image_route import get_controller

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_controller] = lambda: LabImageController(
        LabImageService(db, LabImageRepository(db), fake_r2)
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def world(db):
    """
    ข้อมูลตั้งต้น (seed RBAC แล้ว):
    - owner: instructor ที่สร้างวิชา (course.created_by)
    - co_instructor: instructor ที่ enroll เป็น INSTRUCTOR ในวิชา
    - outsider: instructor ที่ไม่เกี่ยวกับวิชา
    - student: นักศึกษาที่ enroll ในวิชา
    - admin: admin
    - course / deleted_course: วิชาปกติ / วิชาที่ถูก soft delete
    """

    def make_user(name, role):
        user = User(
            id=uuid.uuid4(),
            email=f"{name.lower()}-{uuid.uuid4().hex[:8]}@test.local",
            name=name,
            role=role,
        )
        db.add(user)
        db.flush()
        return user

    owner = make_user("Owner", UserRole.INSTRUCTOR)
    co_instructor = make_user("CoInstructor", UserRole.INSTRUCTOR)
    outsider = make_user("Outsider", UserRole.INSTRUCTOR)
    student = make_user("Student", UserRole.STUDENT)
    admin = make_user("Admin", UserRole.ADMIN)

    course = Course(
        code=f"T{uuid.uuid4().hex[:6]}",
        name="Test course",
        lecturer_name="Someone Else",
        created_by=owner.id,
    )
    deleted_course = Course(
        code=f"T{uuid.uuid4().hex[:6]}",
        name="Deleted course",
        lecturer_name="Someone Else",
        created_by=owner.id,
    )
    db.add_all([course, deleted_course])
    db.flush()

    from datetime import datetime, timezone

    deleted_course.deleted_at = datetime.now(timezone.utc)
    db.add_all(
        [
            Enrollment(
                user_id=co_instructor.id,
                course_id=course.id,
                role_in_course=RoleInCourse.INSTRUCTOR,
            ),
            Enrollment(
                user_id=student.id,
                course_id=course.id,
                role_in_course=RoleInCourse.STUDENT,
            ),
        ]
    )
    db.commit()
    RBACSeeder(db).seed()

    return SimpleNamespace(
        owner=owner,
        co_instructor=co_instructor,
        outsider=outsider,
        student=student,
        admin=admin,
        course=course,
        deleted_course=deleted_course,
    )


@pytest.fixture
def auth(db):
    """auth(user) -> header Authorization: Bearer <access token>"""
    service = AuthService(db, UserRepository(db))

    def _headers(user):
        return {"Authorization": f"Bearer {service.create_access_token(user)}"}

    return _headers


@pytest.fixture
def upload_body(world):
    """body ขอ presign ที่ถูกต้อง (ตามตัวอย่างของ API) — override ได้ด้วย keyword"""

    def _body(**overrides):
        body = {
            "courseId": str(world.course.id),
            "repository": "skypilot/music-lab-test",
            "tag": "lab-01",
            "fileSizeBytes": 2147483648,
            "description": "All-in-one lab: Flask API, Vite client, code-server",
            "cpuRequirement": "2+",
            "memoryRequirement": "4+",
            "diskSize": 50,
            "lifespanMinutes": 60,
            "exposedPorts": [8080, 5173, 8443],
            "entrypointScript": "/bin/bash /run.sh",
            "workdir": "/workspace",
            "envVars": {"IDE_PASSWORD": "musiclab"},
        }
        body.update(overrides)
        return body

    return _body


@pytest.fixture
def create_draft(client, world, auth, upload_body):
    """ขอ presign ผ่าน API ด้วย owner แล้วคืน data ของ response"""

    def _create(**overrides):
        response = client.post(
            "/api/lab-image", json=upload_body(**overrides), headers=auth(world.owner)
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _create
