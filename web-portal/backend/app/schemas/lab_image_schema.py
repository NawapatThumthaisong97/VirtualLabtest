from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

from app.configs.settings import settings
from app.models.lab_image import ImageStatus, ScanStatus
from app.schemas.base import CamelModel

# ชื่อตาม docker reference: path component ตัวพิมพ์เล็ก คั่นด้วย . _ - และ / ได้
RepositoryName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9]+(?:(?:\.|_|__|-+)[a-z0-9]+)*(?:/[a-z0-9]+(?:(?:\.|_|__|-+)[a-z0-9]+)*)*$",
    ),
]
# lab image ทุกตัวต้องอยู่ใต้ vlab/ เพราะ ECR sync (ansible/roles/ecr-sync) ได้สิทธิ์ IAM แค่ repository/vlab/*
# ชื่อนอก prefix จะสแกนผ่านแต่ขึ้น ECR ไม่ได้ (lab บน AWS ใช้ไม่ได้) จึงปฏิเสธตั้งแต่ขอ upload
LAB_IMAGE_REPOSITORY_PREFIX = "vlab/"
# image ของระบบที่อยู่ใต้ prefix เดียวกัน ห้ามอาจารย์ใช้ชื่อซ้ำ (จะทับ image ที่ scan Job ใช้)
RESERVED_REPOSITORIES = frozenset({"vlab/scan-runner"})

ImageTag = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_][A-Za-z0-9._-]*$",
    ),
]


class LabImageUploadRequest(CamelModel):
    """ขอ presigned URL สำหรับอัปโหลด docker image (.tar) ขึ้น R2

    uploaded_by มาจาก JWT, archive_key / status / image_digest server เป็นคนกำหนด ไม่รับจาก client
    course_id คือวิชาที่ image นี้สังกัด server ตรวจว่า user เป็นผู้สอนวิชานี้จริงก่อนออก URL
    """

    course_id: UUID
    repository: RepositoryName
    tag: ImageTag
    file_size_bytes: int = Field(gt=0)

    description: str | None = Field(None, max_length=2000)
    cpu_requirement: str = Field("2+", min_length=1, max_length=20)
    memory_requirement: str = Field("4+", min_length=1, max_length=20)
    disk_size: int = Field(50, gt=0)
    lifespan_minutes: int = Field(60, gt=0)
    exposed_ports: list[int] = Field(default_factory=list)
    entrypoint_script: str = Field("/bin/bash /run.sh", min_length=1, max_length=255)
    workdir: str | None = Field(None, max_length=255)
    env_vars: dict[str, str] | None = None

    # ใช้ PydanticCustomError แทน ValueError: validation handler ใน main.py ใส่ exc.errors() ลง response
    # ตรง ๆ และ ValueError จะติดไปใน ctx ซึ่ง serialize เป็น JSON ไม่ได้ (กลายเป็น 500)
    @field_validator("file_size_bytes")
    @classmethod
    def _check_size(cls, size: int) -> int:
        limit = settings.LAB_IMAGE_MAX_ARCHIVE_BYTES
        if size > limit:
            raise PydanticCustomError(
                "file_too_large",
                "file must not exceed {limit} bytes (single PUT limit)",
                {"limit": limit},
            )
        return size

    @field_validator("repository")
    @classmethod
    def _check_repository_prefix(cls, repository: str) -> str:
        if not repository.startswith(LAB_IMAGE_REPOSITORY_PREFIX):
            raise PydanticCustomError(
                "repository_prefix",
                "repository must start with '{prefix}'",
                {"prefix": LAB_IMAGE_REPOSITORY_PREFIX},
            )
        if repository in RESERVED_REPOSITORIES:
            raise PydanticCustomError("repository_reserved", "repository name is reserved")
        return repository

    @field_validator("exposed_ports")
    @classmethod
    def _check_ports(cls, ports: list[int]) -> list[int]:
        if any(port < 1 or port > 65535 for port in ports):
            raise PydanticCustomError("port_out_of_range", "ports must be in range 1-65535")
        if len(set(ports)) != len(ports):
            raise PydanticCustomError("port_not_unique", "ports must be unique")
        return ports


class LabImageUploadResponse(CamelModel):
    image_id: UUID
    course_id: UUID
    repository: str
    tag: str
    status: ImageStatus
    archive_key: str
    upload_url: str
    method: str = "PUT"
    # client ต้องส่ง header เหล่านี้ตอน PUT ให้ตรงกับที่เซ็นไว้
    headers: dict[str, str]
    expires_at: datetime


class LabImageResponse(CamelModel):
    """แถว lab image สำหรับหน้าอาจารย์ (รายการในแท็บ Lab Image และ dropdown ตอนสร้าง lab)

    ไม่ส่ง archive_key / etag / scan_job_name: เป็นรายละเอียดภายในของ pipeline
    scan_summary ส่งทั้งก้อน (verdict, reasons, warnings, counts) ให้แสดงเหตุผลที่ไม่ผ่าน
    """

    id: UUID
    course_id: UUID
    repository: str
    tag: str
    image_digest: str | None
    size_mb: int
    description: str | None
    cpu_requirement: str
    memory_requirement: str
    disk_size: int
    lifespan_minutes: int
    exposed_ports: list[int]
    entrypoint_script: str
    workdir: str | None
    env_vars: dict[str, str] | None
    status: ImageStatus
    scan_status: ScanStatus
    scan_attempts: int
    scan_summary: dict | None
    archive_uploaded_at: datetime | None
    scan_started_at: datetime | None
    scan_finished_at: datetime | None
    created_at: datetime


class R2UploadWebhookPayload(BaseModel):
    """payload จาก cloudflare-worker/index.js (snake_case ตามที่ Worker ส่ง)"""

    account_id: str | None = None
    object_key: str = Field(min_length=1, max_length=1024)
    action: str | None = None
    bucket: str | None = None
    size: int | None = Field(None, ge=0)
    etag: str | None = Field(None, max_length=255)
    event_time: datetime | None = None


class R2UploadWebhookResponse(CamelModel):
    updated: bool
    image_id: UUID | None = None
    object_key: str
