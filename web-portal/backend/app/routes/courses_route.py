from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Request,
    UploadFile,
    status as http_status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.middlewares.auth import get_current_user
from app.middlewares.rbac import verify_permission
from app.models.user import User, UserRole
from app.repositories.courses_repositories import CourseRepository
from app.repositories.annoucement_repositories import AnnouncementRepository
from app.schemas.course_schema import (
    AnnouncementResponse,
    AnnouncementCreateRequest,
    AnnouncementUpdateRequest,
    CourseCreateRequest,
    CourseDetailResponse,
    CourseResponse,
    CourseUpdateRequest,
)
from app.services.courses_service import CourseService
from app.controllers.course_controller import CourseController
from app.middlewares.request_validation import require_non_empty_body
from app.adapters.local_storage import local_storage
from app.exceptions.domain import NotFoundError, ValidationError
from app.services.rbac_service import ResourceContextPolicy

router = APIRouter()

# สร้าง policy สำหรับ course context
course_policy = ResourceContextPolicy()


def course_response(course, request: Request) -> CourseResponse:
    response = CourseResponse.model_validate(course)
    if response.image_url and not response.image_url.startswith(
        ("http://", "https://")
    ):
        response.image_url = str(
            request.url_for("get_course_image", course_id=course.id)
        )
    return response


def announcement_response(announcement) -> AnnouncementResponse:
    """
    map เอง ไม่ใช้ model_validate เพราะ author_name ไม่ได้อยู่บนตาราง
    announcements ตรง ๆ — ต้องเดินผ่าน relationship ไปหยิบชื่อจาก users
    """
    author_name = announcement.author.name if announcement.author else None
    
    return AnnouncementResponse(
        id=announcement.id,
        message=announcement.message,
        created_at=announcement.created_at,
        author_name=author_name,
    )


def course_detail_response(
    course, announcements: list, request: Request
) -> CourseDetailResponse:
    response = CourseDetailResponse(
        id=course.id,
        code=course.code,
        name=course.name,
        lecturer_name=course.lecturer_name,
        image_url=course.image_url,
        background_key=course.background_key,
        icon_key=course.icon_key,
        announcement_ids=None,
        announcements=[announcement_response(item) for item in announcements],
    )
    if response.image_url and not response.image_url.startswith(
        ("http://", "https://")
    ):
        response.image_url = str(
            request.url_for("get_course_image", course_id=course.id)
        )
    return response


def get_course_controller(db: Session = Depends(get_db)) -> CourseController:
    course_repository = CourseRepository(db)
    announcement_repository = AnnouncementRepository(db)
    course_service = CourseService(course_repository, announcement_repository)
    return CourseController(course_service)


@router.get("/{course_id}", response_model=CourseDetailResponse)
def get_course(
    course_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
    _: User = Depends(
        verify_permission(
            "courses:read:self",
            context_policy=course_policy
        )
    ),
):
    """ดึงข้อมูล course พร้อม announcement (ต้อง login และมีสิทธิ์เข้าถึง)"""
    course, announcements = controller.get_course_detail(course_id)
    return course_detail_response(course, announcements, request)


@router.post(
    "",
    response_model=CourseResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_non_empty_body),
        Depends(verify_permission("courses:create:self"))
    ],
)
def create_course(
    course: CourseCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
):
    """สร้าง course ใหม่ (ต้อง login และเป็น Instructor หรือ Admin)"""
    # RBAC จัดการสิทธิ์แล้ว ไม่ต้อง check role
    created_course = controller.create_course(course, created_by_user_id=current_user.id)
    return course_response(created_course, request)


@router.get("", response_model=list[CourseResponse])
def get_all_courses(
    request: Request,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
):
    """คืนรายการวิชา (ต้อง login) - ถูกกรองตาม role อัตโนมัติ"""
    # Admin เห็นทุกวิชา (มี courses:manage:global)
    # Instructor เห็นวิชาที่สร้างเองหรือสอน
    # Student เห็นเฉพาะวิชาที่ลงทะเบียน
    if current_user.role is UserRole.ADMIN:
        courses = controller.get_all_courses()
    elif current_user.role is UserRole.INSTRUCTOR:
        courses = controller.get_courses_by_instructor(current_user.id, current_user.name)
    else:
        courses = controller.get_courses_by_student(current_user.id)
    
    return [course_response(course, request) for course in courses]


@router.get("/{course_id}/image", name="get_course_image")
def get_course_image(
    course_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
):
    """ดึงรูปภาพของ course (ต้อง login)"""
    course = controller.get_course(course_id)
    if not course.image_url or course.image_url.startswith(("http://", "https://")):
        raise NotFoundError(f"Course image {course_id} not found")
    path = local_storage.resolve(course.image_url)
    if not path.is_file():
        raise NotFoundError(f"Course image {course_id} not found")
    return FileResponse(path)


@router.post(
    "/{course_id}/image",
    response_model=CourseResponse,
    dependencies=[
        Depends(
            verify_permission(
                "storage:images:push:course",
                context_policy=course_policy,
            )
        )
    ],
)
def upload_course_image(
    course_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    image: UploadFile = File(...),
    controller: CourseController = Depends(get_course_controller),
):
    """อัปโหลดรูปภาพของ course (ต้องเป็น Instructor ที่สอนวิชานี้ หรือ Admin)"""
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValidationError("Only JPEG, PNG, and WebP images are supported")
    
    course = controller.course_service.save_course_image(
        course_id, image.filename or "image.bin", image
    )
    return course_response(course, request)


@router.patch(
    "/{course_id}",
    response_model=CourseResponse,
    dependencies=[
        Depends(require_non_empty_body),
        Depends(
            verify_permission(
                "courses:update:course",
                context_policy=course_policy
            )
        )
    ],
)
def update_course(
    course_id: UUID,
    updated_course: CourseUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
):
    """อัปเดตข้อมูล course (ต้องเป็น Instructor ที่สอนวิชานี้ หรือ Admin)"""
    # RBAC + Policy เช็คสิทธิ์แล้ว
    course = controller.update_course(course_id, updated_course)
    return course_response(course, request)


def update_course_announcement_ids(
    course_id: UUID,
    announcement_ids: list[UUID],
    controller: CourseController = Depends(get_course_controller),
):
    """อัปเดต announcement_ids ของ course โดยใช้ course_id"""
    controller.update_course_announcement_ids(course_id, announcement_ids)


@router.delete(
    "/{course_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            verify_permission(
                "courses:delete:course",
                context_policy=course_policy
            )
        )
    ],
)
def soft_delete_course(
    course_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
    db: Session = Depends(get_db),
):
    """
    ลบ course (soft delete หรือ hard delete ขึ้นอยู่กับเงื่อนไข)
    - ถ้าไม่มี student enroll และไม่มี lab -> hard delete
    - ถ้ามี student enroll หรือมี lab -> ห้ามลบ (409 Conflict)
    """
    from app.exceptions.domain import ConflictError
    from app.models.enrollment import Enrollment
    from app.models.lab import Lab
    from sqlalchemy import select, exists
    
    # ตรวจสอบว่ามี enrollment หรือ lab หรือไม่
    has_enrollments = db.execute(
        select(exists().where(Enrollment.course_id == course_id))
    ).scalar()
    
    has_labs = db.execute(
        select(exists().where(Lab.course_id == course_id))
    ).scalar()
    
    if has_enrollments or has_labs:
        raise ConflictError(
            "Cannot delete course with enrolled students or existing labs. "
            "Please remove all enrollments and labs before deleting."
        )
    
    # ถ้าไม่มี enrollment และไม่มี lab -> hard delete เลย
    controller.hard_delete_course(course_id)


@router.delete(
    "/{course_id}/hard",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(verify_permission("courses:manage:global"))
    ],
)
def hard_delete_course(
    course_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller)
):
    """ลบ course ถาวร (เฉพาะ Admin)"""
    # RBAC เช็คว่าต้องมี courses:manage:global แล้ว (Admin only)
    controller.hard_delete_course(course_id)


@router.post(
    "/{course_id}/announcements",
    response_model=AnnouncementResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_non_empty_body),
        Depends(
            verify_permission(
                "courses:announcements:create:course",
                context_policy=course_policy
            )
        )
    ],
)
def create_announcement(
    course_id: UUID,
    announcement: AnnouncementCreateRequest,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
):
    """สร้าง announcement (ต้องเป็น Instructor ที่สอนวิชานี้ หรือ Admin)"""
    # RBAC + Policy เช็คสิทธิ์แล้ว
    created_announcement = controller.create_announcement(
        course_id=course_id,
        message=announcement.message,
        author_id=current_user.id
    )
    return announcement_response(created_announcement)


@router.patch(
    "/{course_id}/announcements/{announcement_id}",
    response_model=AnnouncementResponse,
    dependencies=[
        Depends(require_non_empty_body),
        Depends(
            verify_permission(
                "courses:announcements:update:course",
                context_policy=course_policy
            )
        )
    ],
)
def update_announcement(
    course_id: UUID,
    announcement_id: UUID,
    announcement: AnnouncementUpdateRequest,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
):
    """อัปเดต announcement (ต้องเป็น Instructor ที่สอนวิชานี้ หรือ Admin)"""
    # RBAC + Policy เช็คสิทธิ์แล้ว
    updated_announcement = controller.update_announcement(
        course_id=course_id,
        announcement_id=announcement_id,
        message=announcement.message
    )
    return announcement_response(updated_announcement)


@router.delete(
    "/{course_id}/announcements/{announcement_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            verify_permission(
                "courses:announcements:delete:course",
                context_policy=course_policy
            )
        )
    ],
)
def delete_announcement(
    course_id: UUID,
    announcement_id: UUID,
    current_user: User = Depends(get_current_user),
    controller: CourseController = Depends(get_course_controller),
):
    """ลบ announcement (Hard Delete) - ต้องเป็น Instructor ที่สอนวิชานี้ หรือ Admin"""
    # RBAC + Policy เช็คสิทธิ์แล้ว
    controller.course_service.announcement_repository.delete(announcement_id)
    controller.course_service.announcement_repository.db.commit()
