"""
Fixture ฝั่ง DB + sky ปลอม สำหรับเทส create / delete / reconcile

DB: Postgres ชื่อ virtual_lab_test (model ใช้ UUID / JSONB / enum ของ Postgres ใช้ SQLite ไม่ได้)
- สร้าง schema ใหม่จาก model ทุกครั้งที่เริ่มรัน
- แต่ละเทสอยู่ใน transaction ที่ rollback ทิ้งตอนจบ ข้อมูลไม่ค้าง
  (join_transaction_mode="create_savepoint" ทำให้ db.commit() ในโค้ดจริงกลายเป็น savepoint)
- ต่อ DB ไม่ได้ → เทสที่ใช้ db ถูก skip ส่วนเทส builder ยังรันได้

เปลี่ยน DB ได้ด้วย env TEST_DATABASE_URL (ชื่อ DB ต้องลงท้ายด้วย _test กันลบข้อมูลจริง)
"""
import os
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  ให้ทุก table อยู่ใน Base.metadata
from app.configs.db import Base
from app.configs.settings import settings
from app.models.courses import Course
from app.models.lab import Lab, RunTarget
from app.models.lab_image import LabImage
from app.models.session import Session as SessionModel, SessionStatus, ServiceType
from app.models.user import User
from app.repositories.lab_image_repository import LabImageRepository
from app.repositories.lab_repository import LabRepository
from app.repositories.session_repository import SessionRepository
from app.services import session_service
from app.services.session_service import SessionService
from tests.fakes import FakeSky


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
def fake_sky(monkeypatch):
    fake = FakeSky()
    monkeypatch.setattr(session_service, "sky", fake)
    # _wait_job_running รอ 5 วินาทีต่อรอบ ในเทสไม่ต้องรอจริง
    monkeypatch.setattr(session_service.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(session_service, "get_ecr_token", lambda region: "fake-ecr-token")
    return fake


@pytest.fixture
def svc(db, fake_sky):
    return SessionService(db, SessionRepository(db), LabRepository(db), LabImageRepository(db))


@pytest.fixture
def world(db):
    """ข้อมูลตั้งต้น: user 1 คน, course 1 วิชา, lab K3s 1 ตัว, lab AWS 1 ตัว, lab ไม่มี image 1 ตัว"""
    user = User(email=f"student-{uuid.uuid4().hex[:8]}@test.local", name="Student")
    db.add(user)
    db.flush()
    course = Course(code=f"T{uuid.uuid4().hex[:6]}", name="Test course",
                    lecturer_name="Lecturer", created_by=user.id)
    db.add(course)
    db.flush()

    def image(repository, entrypoint="/bin/bash /run.sh", ports=(8080, 5173, 8443)):
        img = LabImage(uploaded_by=user.id, course_id=course.id, repository=repository,
                       tag="lab-01", image_digest=f"sha256:{uuid.uuid4().hex}", size_mb=100,
                       lifespan_minutes=60, exposed_ports=list(ports),
                       entrypoint_script=entrypoint, env_vars={"IDE_PASSWORD": "x"})
        db.add(img)
        db.flush()
        return img

    k8s_image = image("skypilot/music-lab")
    aws_image = image("vlab/music-lab-ide", entrypoint="", ports=(8080,))

    def lab(title, img, target, order_no):
        lb = Lab(course_id=course.id, title=title, order_no=order_no,
                 image_id=img.id if img else None, run_target=target)
        db.add(lb)
        db.flush()
        return lb

    ns = SimpleNamespace(
        user=user,
        course=course,
        k8s_image=k8s_image,
        aws_image=aws_image,
        k8s_lab=lab("K3s lab", k8s_image, RunTarget.KUBERNETES, 1),
        aws_lab=lab("AWS lab", aws_image, RunTarget.AWS, 2),
        no_image_lab=lab("Lab without image", None, RunTarget.KUBERNETES, 3),
    )
    db.commit()
    return ns


@pytest.fixture
def add_session(db, world):
    """ใส่ session ลง DB ตรง ๆ เพื่อจำลองสถานะก่อนหน้า (เช่น RUNNING ค้าง, PENDING เก่า)"""
    def _add(status, cluster="music-lab-old", lab=None, started_ago=timedelta(minutes=1),
             expires_in=None, user=None):
        now = datetime.utcnow()
        s = SessionModel(
            user_id=(user or world.user).id,
            lab_id=(lab or world.k8s_lab).id,
            lab_image_id=world.k8s_image.id,
            service_type=ServiceType.LAB,
            sky_cluster_name=cluster,
            status=status,
            started_at=now - started_ago,
            expires_at=now + expires_in if expires_in is not None else None,
            is_remote=False,
            is_cloud=False,
        )
        db.add(s)
        db.commit()
        return s
    return _add


def sessions_of(db, user, lab=None):
    q = db.query(SessionModel).filter(SessionModel.user_id == user.id)
    if lab is not None:
        q = q.filter(SessionModel.lab_id == lab.id)
    return q.order_by(SessionModel.started_at).all()


__all__ = ["sessions_of", "SessionStatus"]
