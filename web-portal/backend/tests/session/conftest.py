"""
Fixture sky ปลอม + ข้อมูลตั้งต้น สำหรับเทส create / delete / reconcile
(fixture db / db_engine อยู่ใน tests/conftest.py ใช้ร่วมกับเทส prewarm)
"""
import time as _real_time
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.courses import Course
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import Lab, LabStatus, RunTarget
from app.models.lab_image import ImageStatus, LabImage
from app.models.session import Session as SessionModel, SessionStatus, ServiceType
from app.models.user import User
from app.repositories.lab_image_repository import LabImageRepository
from app.repositories.lab_repository import LabRepository
from app.repositories.session_repository import SessionRepository
from app.services import session_service
from app.services.session_service import SessionService
from tests.fakes import FakeSky


class FakeClock:
    """แทน module time ใน session_service: sleep = เวลาเดินทันที (ไม่รอจริง) + เรียก on_sleep ให้เทสเปลี่ยนโลกได้"""

    def __init__(self):
        self.now = 1000.0
        self.slept = 0.0
        self.on_sleep = None   # callable(clock) — เช่น ทำให้ warm pod พร้อมระหว่างรอ

    def monotonic(self):
        return self.now

    def time(self):
        return _real_time.time()

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds
        if self.on_sleep is not None:
            self.on_sleep(self)


@pytest.fixture
def fake_sky(monkeypatch):
    fake = FakeSky()
    monkeypatch.setattr(session_service, "sky", fake)
    # _wait_job_running / รอ pod ใช้ time.sleep + time.monotonic — ในเทสใช้นาฬิกาปลอม ไม่รอจริง
    monkeypatch.setattr(session_service, "time", FakeClock())
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
    # เปิด lab ได้เฉพาะนักศึกษาที่ลงทะเบียนวิชานั้น (session_service.create_session)
    db.add(Enrollment(user_id=user.id, course_id=course.id, role_in_course=RoleInCourse.STUDENT))
    db.flush()

    def image(repository, entrypoint="/bin/bash /run.sh", ports=(8080, 5173, 8443)):
        img = LabImage(uploaded_by=user.id, course_id=course.id, repository=repository,
                       tag="lab-01", image_digest=f"sha256:{uuid.uuid4().hex}", size_mb=100,
                       lifespan_minutes=60, exposed_ports=list(ports),
                       entrypoint_script=entrypoint, env_vars={"IDE_PASSWORD": "x"},
                       status=ImageStatus.APPROVED)  # image ที่ยังไม่อนุมัติ launch ไม่ได้
        db.add(img)
        db.flush()
        return img

    k8s_image = image("skypilot/music-lab")
    aws_image = image("vlab/music-lab-ide", entrypoint="", ports=(8080,))

    def lab(title, img, target, order_no):
        lb = Lab(course_id=course.id, title=title, order_no=order_no,
                 image_id=img.id if img else None, run_target=target,
                 status=LabStatus.PUBLISHED)  # lab ที่ยังไม่ publish launch ไม่ได้
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
