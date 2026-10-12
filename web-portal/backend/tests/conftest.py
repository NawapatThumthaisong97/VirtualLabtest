"""
Fixture ที่ใช้ร่วมกันทุกเทส

เทสกลุ่ม builder ไม่ต่อ DB และไม่เรียก SkyPilot จริง แค่สร้าง task config แล้วตรวจผล
"""
import pytest

from app.configs.settings import settings
from app.models.lab_image import LabImage
from app.services.session_service import SessionService

ECR_HOST = "123456789012.dkr-ecr.ap-southeast-1.on.aws"
AMI = "ami-0123456789abcdef0"
REGISTRY = "10.0.0.1:5001"


@pytest.fixture
def service():
    # builder ไม่ใช้ db / repository เลยส่ง None ได้
    return SessionService(db=None, session_repository=None,
                          lab_repository=None, lab_image_repository=None)


@pytest.fixture
def make_image():
    """สร้าง LabImage (ไม่ลง DB) ค่าตั้งต้นเหมือน lab music-lab ที่ใช้อยู่จริง"""
    def _make(**overrides) -> LabImage:
        fields = dict(
            repository="skypilot/music-lab",
            tag="lab-01",
            cpu_requirement="2+",
            memory_requirement="4+",
            disk_size=50,
            lifespan_minutes=60,
            exposed_ports=[8080, 5173, 8443],
            entrypoint_script="/bin/bash /run.sh",
            workdir=None,
            env_vars={"IDE_PASSWORD": "musiclab"},
        )
        fields.update(overrides)
        return LabImage(**fields)
    return _make


@pytest.fixture(autouse=True)
def fixed_settings(monkeypatch):
    """ไม่ให้ผลเทสขึ้นกับ .env ของแต่ละเครื่อง"""
    monkeypatch.setenv("DOCKER_REGISTRY_HOST", REGISTRY)
    monkeypatch.setattr(settings, "AWS_REGION", "ap-southeast-1")
    monkeypatch.setattr(settings, "AWS_LAB_AMI", AMI)
    monkeypatch.setattr(settings, "AWS_INSTANCE_TYPE", "m7i-flex.large")
    monkeypatch.setattr(settings, "AWS_DISK_SIZE", 30)
    monkeypatch.setattr(settings, "ECR_REGISTRY_HOST", ECR_HOST)
