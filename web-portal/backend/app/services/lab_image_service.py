"""
Lab image upload (.tar -> Cloudflare R2)

Flow:
  1. อาจารย์ขอ presign -> สร้าง/ใช้แถว draft (status=PENDING) แล้วออก presigned PUT URL
  2. client PUT ไฟล์ตรงเข้า R2
  3. R2 event -> Queue -> Worker -> webhook -> เติม archive_* ของแถวที่ archive_key ตรงกัน
"""
import hmac
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.r2_adapter import R2Adapter
from app.configs.settings import settings
from app.exceptions.domain import (
    ConflictError,
    CourseNotFoundError,
    ForbiddenError,
    LabImageNotFoundError,
    UnauthorizedError,
)
from app.models.courses import Course
from app.models.enrollment import RoleInCourse
from app.models.lab_image import ImageStatus, LabImage
from app.models.user import User
from app.repositories.lab_image_repository import LabImageRepository
from app.repositories.rbac_repository import RBACRepository
from app.schemas.lab_image_schema import (
    LabImageApproveRequest,
    LabImageApproveResponse,
    LabImageRejectRequest,
    LabImageRejectResponse,
    LabImageUploadRequest,
    LabImageUploadResponse,
    R2UploadWebhookPayload,
    R2UploadWebhookResponse,
)
from app.services.rbac_service import RBACService
from app.services.schedule_service import SCHEDULE_TZ

UPLOAD_PERMISSION = "storage:images:push:course"
ARCHIVE_CONTENT_TYPE = "application/x-tar"
MIB = 1024 * 1024

# field ใน request ที่ map ตรงไปคอลัมน์ lab_images
_CONFIG_FIELDS = (
    "description",
    "cpu_requirement",
    "memory_requirement",
    "disk_size",
    "lifespan_minutes",
    "exposed_ports",
    "entrypoint_script",
    "workdir",
    "env_vars",
)


ARCHIVE_KEY_PREFIX = "lab-images"
_UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9-]+")


def build_archive_key(course_code: str, image_id: UUID, now: datetime) -> str:
    """R2 object key: lab-images/{รหัสวิชา}_{ปี}_{เดือน}_{วัน}_{image_id 8 ตัวแรก}_image.tar

    - รหัสวิชาเหลือเฉพาะ A-Z a-z 0-9 - (course.code กรอกอะไรก็ได้ ห้ามให้มี / หรือ .. หลุดเข้า path)
    - วันที่ใช้เวลาไทย (ตรงกับที่คนเห็น) ณ ตอนออก presign ครั้งแรก
    - ส่วน image_id กันไฟล์ทับกันเมื่อวิชาเดียวอัปหลาย image ในวันเดียว (PUT ผ่าน presigned URL ทับไฟล์เดิมได้)
    """
    code = _UNSAFE_KEY_CHARS.sub("-", course_code).strip("-") or "course"
    day = now.astimezone(SCHEDULE_TZ)
    return (
        f"{ARCHIVE_KEY_PREFIX}/{code}_{day:%Y}_{day:%m}_{day:%d}_{image_id.hex[:8]}_image.tar"
    )


class WebhookSecretInvalidError(UnauthorizedError):
    code = "invalid_webhook_secret"


class LabImageService:
    def __init__(
        self,
        db: Session,
        lab_image_repository: LabImageRepository,
        r2: R2Adapter,
        rbac_service: RBACService | None = None,
    ):
        self.db = db
        self.lab_image_repository = lab_image_repository
        self.r2 = r2
        self.rbac_service = rbac_service or RBACService()
        self.rbac_repository = RBACRepository(db)

    # ------------------------------------------------------------ presign

    def _ensure_can_upload(self, user: User, course_id: UUID) -> Course:
        """admin (global) อัปได้ทุกวิชา, instructor ต้องมีสิทธิ์ + เป็นเจ้าของ/ผู้สอนวิชานั้นจริง

        คืน course ที่ตรวจแล้ว (ใช้สร้าง archive key)
        """
        course = self.rbac_repository.find_active_course(course_id)
        if course is None:
            raise CourseNotFoundError(f"Course {course_id} not found")

        if self.rbac_service.has_global_permission(self.db, user.id, UPLOAD_PERMISSION):
            return course
        if not self.rbac_service.has_permission(self.db, user.id, UPLOAD_PERMISSION):
            raise ForbiddenError("ไม่มีสิทธิ์อัปโหลด lab image")

        # เทียบด้วย id เท่านั้น (ไม่ใช้ lecturer_name ที่เป็นชื่อแสดงผล ชื่อซ้ำกันได้)
        is_owner = course.created_by == user.id or self.rbac_repository.is_enrolled(
            user.id, course_id, RoleInCourse.INSTRUCTOR
        )
        if not is_owner:
            raise ForbiddenError("ไม่ได้เป็นผู้สอนของวิชานี้")
        return course

    def _new_image_id_and_key(self, course: Course) -> tuple[UUID, str]:
        """สุ่ม image_id จนได้ key ที่ยังไม่มีใน DB (ส่วนท้าย 8 ตัวชนกันได้ยากมากแต่ไม่ใช่เป็นไปไม่ได้)"""
        now = datetime.now(timezone.utc)
        for _ in range(5):
            image_id = uuid.uuid4()
            key = build_archive_key(course.code, image_id, now)
            if self.lab_image_repository.find_by_archive_key(key) is None:
                return image_id, key
        raise ConflictError("Could not allocate a unique archive key, please retry")

    def _find_reusable_draft(
        self, payload: LabImageUploadRequest, user: User
    ) -> LabImage | None:
        """repository:tag ซ้ำ -> ใช้แถวเดิมได้เฉพาะ draft ของคนเดิม วิชาเดิม ที่ยังไม่มีไฟล์ขึ้น R2"""
        existing = self.lab_image_repository.find_by_repository_and_tag(
            payload.repository, payload.tag
        )
        if existing is None:
            return None
        is_reusable_draft = (
            existing.status is ImageStatus.PENDING
            and existing.archive_uploaded_at is None
            and existing.uploaded_by == user.id
            and existing.course_id == payload.course_id
        )
        if not is_reusable_draft:
            raise ConflictError(
                f"Image {payload.repository}:{payload.tag} already exists"
            )
        return existing

    def create_upload(
        self, payload: LabImageUploadRequest, user: User
    ) -> LabImageUploadResponse:
        course = self._ensure_can_upload(user, payload.course_id)

        image = self._find_reusable_draft(payload, user)
        if image is None:
            image_id, archive_key = self._new_image_id_and_key(course)
            image = LabImage(
                id=image_id,
                uploaded_by=user.id,
                course_id=payload.course_id,
                repository=payload.repository,
                tag=payload.tag,
                image_digest=None,  # เติมตอน approve
                status=ImageStatus.PENDING,
                archive_key=archive_key,
            )
        elif not image.archive_key:
            image.archive_key = build_archive_key(
                course.code, image.id, datetime.now(timezone.utc)
            )

        # ค่าประมาณจากที่ client แจ้ง webhook จะทับด้วยขนาดจริง
        image.size_mb = math.ceil(payload.file_size_bytes / MIB)
        for field in _CONFIG_FIELDS:
            setattr(image, field, getattr(payload, field))

        # เซ็น URL ก่อน commit: ถ้า R2 ยังไม่ได้ตั้งค่าจะได้ไม่เหลือแถว draft ค้าง
        expires_in = settings.R2_PRESIGN_EXPIRES_SECONDS
        upload_url = self.r2.generate_presigned_put_url(
            image.archive_key, ARCHIVE_CONTENT_TYPE, expires_in
        )
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        try:
            self.lab_image_repository.save(image)
            self.db.commit()
        except IntegrityError as error:
            # ขอพร้อมกัน 2 request ด้วย repository:tag เดียวกัน
            self.db.rollback()
            raise ConflictError(
                f"Image {payload.repository}:{payload.tag} already exists"
            ) from error
        self.db.refresh(image)

        return LabImageUploadResponse(
            image_id=image.id,
            course_id=image.course_id,
            repository=image.repository,
            tag=image.tag,
            status=image.status,
            archive_key=image.archive_key,
            upload_url=upload_url,
            headers={"Content-Type": ARCHIVE_CONTENT_TYPE},
            expires_at=expires_at,
        )

    # ------------------------------------------------------------ webhook

    @staticmethod
    def _verify_secret(provided: str | None, expected: str | None) -> None:
        # ไม่ได้ตั้ง secret = ปฏิเสธทุก request (fail closed)
        if not expected or not provided or not hmac.compare_digest(
            provided.encode(), expected.encode()
        ):
            raise WebhookSecretInvalidError("Invalid webhook secret")

    @classmethod
    def verify_webhook_secret(cls, provided: str | None) -> None:
        """webhook จาก Cloudflare Worker (upload event)"""
        cls._verify_secret(provided, settings.R2_WEBHOOK_SECRET)

    @classmethod
    def verify_approve_secret(cls, provided: str | None) -> None:
        """webhook อนุมัติ image — ใช้ secret คนละชุดกับของ Cloudflare ไม่รับแทนกัน"""
        cls._verify_secret(provided, settings.LAB_IMAGE_APPROVE_WEBHOOK_SECRET)



    def handle_upload_event(
        self, payload: R2UploadWebhookPayload
    ) -> R2UploadWebhookResponse:
        """เติม archive_* จาก event ของ R2 — ทำซ้ำได้ (Queue ส่งซ้ำได้) ค่าใหม่ทับค่าเดิม"""
        image = self.lab_image_repository.find_by_archive_key(payload.object_key)
        if image is None:
            # ไม่ใช่ไฟล์ที่ระบบออก presign ให้ ตอบ 2xx ให้ Worker ack ไม่ต้อง retry
            return R2UploadWebhookResponse(updated=False, object_key=payload.object_key)

        if payload.etag is not None:
            image.archive_etag = payload.etag.strip('"')
        if payload.size is not None:
            image.archive_size_bytes = payload.size
            image.size_mb = math.ceil(payload.size / MIB)
        image.archive_uploaded_at = payload.event_time or datetime.now(timezone.utc)
        self.db.commit()

        return R2UploadWebhookResponse(
            updated=True, image_id=image.id, object_key=payload.object_key
        )





    # ------------------------------------------------------------ approve

    def approve_image(self, payload: LabImageApproveRequest) -> LabImageApproveResponse:
        """PENDING -> APPROVED (ทำซ้ำได้ ถ้าอนุมัติแล้วคืนผลเดิมโดยไม่แก้ข้อมูล)

        ไม่เติม image_digest — เป็นหน้าที่ของขั้น import เข้า registry
        """
        image = self.lab_image_repository.find_by_id(payload.lab_image_id, for_update=True)
        if image is None:
            raise LabImageNotFoundError(f"Lab image {payload.lab_image_id} not found")

        if image.status is ImageStatus.APPROVED:
            return LabImageApproveResponse(image_id=image.id, status=image.status, updated=False)
        if image.status is ImageStatus.REJECTED:
            raise ConflictError(f"Lab image {image.id} was rejected and cannot be approved")
        if image.archive_uploaded_at is None:
            # ยังไม่มี event ว่าไฟล์ขึ้น R2 ห้ามอนุมัติ image ที่ไม่มีไฟล์
            raise ConflictError(f"Lab image {image.id} has no uploaded archive yet")

        image.status = ImageStatus.APPROVED
        self.db.commit()
        return LabImageApproveResponse(image_id=image.id, status=image.status, updated=True)

    # ------------------------------------------------------------ reject

    def reject_image(self, payload: LabImageRejectRequest) -> LabImageRejectResponse:
        """ปฏิเสธ = ลบ lab image ที่ยัง PENDING ทิ้งทั้งแถว DB และไฟล์บน R2

        ลำดับ: ลบแถว (flush, ยังไม่ commit) -> ลบไฟล์ R2 -> commit
        - แถวที่ถูกอ้างอิงอยู่ (lab / session / ตารางเรียน) ถูกปฏิเสธก่อนแตะ R2
        - R2 ลบไม่สำเร็จ -> rollback แถวยังอยู่ ยิงซ้ำได้ (ลบ R2 ซ้ำได้ ไม่ error)
        - ไม่มีกรณีที่แถวหายแต่ไฟล์ค้างบน R2 โดยไม่มีใครรู้
        """
        image = self.lab_image_repository.find_by_id(payload.lab_image_id, for_update=True)
        if image is None:
            raise LabImageNotFoundError(f"Lab image {payload.lab_image_id} not found")
        if image.status is not ImageStatus.PENDING:
            raise ConflictError(
                f"Lab image {image.id} is {image.status.value}, only pending images can be rejected"
            )

        if self.lab_image_repository.is_referenced(image.id):
            raise ConflictError(f"Lab image {image.id} is still referenced by a lab or session")

        image_id, archive_key = image.id, image.archive_key
        try:
            self.lab_image_repository.delete(image)
        except IntegrityError as error:
            self.db.rollback()
            raise ConflictError(f"Lab image {image_id} is still referenced and cannot be deleted") from error

        try:
            if archive_key:
                self.r2.delete_object(archive_key)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return LabImageRejectResponse(image_id=image_id, archive_key=archive_key, deleted=True)
