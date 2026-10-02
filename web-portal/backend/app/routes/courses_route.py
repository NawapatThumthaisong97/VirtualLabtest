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
from app.middlewares.auth import get_current_user, get_current_user_optional
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

router = APIRouter()


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
    try:
        author_name = announcement.author.name if announcement.author else None
    except AttributeError:
        # ถ้า author relationship ไม่ได้ load
        author_name = None
    
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
    controller: CourseController = Depends(get_course_controller),
):
    """ดึงข้อมูล course พร้อม announcement ที่เกี่ยวข้อง"""
    course, announcements = controller.get_course_detail(course_id)
    return course_detail_response(course, announcements, request)


@router.post(
    "",
    response_model=CourseResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_non_empty_body)],
)
def create_course(
    course: CourseCreateRequest,
    controller: CourseController = Depends(get_course_controller),
):
    """สร้าง course ใหม่"""
    return controller.create_course(course)


@router.get("", response_model=list[CourseResponse])
def get_all_courses(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    controller: CourseController = Depends(get_course_controller),
):
    """
    คืนรายการวิชา:
    - ถ้าไม่ได้ login: คืนทุกวิชา (public)
    - ถ้า login แล้วเป็น admin: คืนทุกวิชา
    - ถ้า login แล้วเป็น student/instructor: คืนเฉพาะวิชาที่เกี่ยวข้อง
    """
    if current_user is None:
        # ไม่ได้ login: แสดงทุกวิชา (public mode)
        courses = controller.get_all_courses()
    elif current_user.role is UserRole.ADMIN:
        # Admin เห็นทุกวิชา
        courses = controller.get_all_courses()
    else:
        # Student/Instructor เห็นเฉพาะวิชาที่ลงเรียน/สอน
        courses = controller.get_courses_by_student(current_user.id)
    
    return [course_response(course, request) for course in courses]


@router.get("/{course_id}/image", name="get_course_image")
def get_course_image(
    course_id: UUID,
    controller: CourseController = Depends(get_course_controller),
):
    """ดึงรูปภาพของ course"""
    course = controller.get_course(course_id)
    if not course.image_url or course.image_url.startswith(("http://", "https://")):
        raise NotFoundError(f"Course image {course_id} not found")
    path = local_storage.resolve(course.image_url)
    if not path.is_file():
        raise NotFoundError(f"Course image {course_id} not found")
    return FileResponse(path)


@router.post("/{course_id}/image", response_model=CourseResponse)
def upload_course_image(
    course_id: UUID,
    request: Request,
    image: UploadFile = File(...),
    controller: CourseController = Depends(get_course_controller),
):
    """อัปโหลดรูปภาพของ course"""
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValidationError("Only JPEG, PNG, and WebP images are supported")
    course = controller.course_service.save_course_image(
        course_id, image.filename or "image.bin", image
    )
    return course_response(course, request)


@router.patch(
    "/{course_id}",
    response_model=CourseResponse,
    dependencies=[Depends(require_non_empty_body)],
)
def update_course(
    course_id: UUID,
    updated_course: CourseUpdateRequest,
    controller: CourseController = Depends(get_course_controller),
):
    """อัปเดตข้อมูล course โดยใช้ course_id"""
    return controller.update_course(course_id, updated_course)


def update_course_announcement_ids(
    course_id: UUID,
    announcement_ids: list[UUID],
    controller: CourseController = Depends(get_course_controller),
):
    """อัปเดต announcement_ids ของ course โดยใช้ course_id"""
    controller.update_course_announcement_ids(course_id, announcement_ids)


@router.delete("/{course_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def soft_delete_course(
    course_id: UUID, controller: CourseController = Depends(get_course_controller)
):
    """ซ่อน course โดยยังเก็บข้อมูลไว้ในฐานข้อมูล"""
    controller.soft_delete_course(course_id)


@router.delete("/{course_id}/hard", status_code=http_status.HTTP_204_NO_CONTENT)
def hard_delete_course(
    course_id: UUID, controller: CourseController = Depends(get_course_controller)
):
    """ลบ course ออกจากฐานข้อมูลถาวร"""
    controller.hard_delete_course(course_id)


@router.post(
    "/{course_id}/announcements",
    response_model=AnnouncementResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_non_empty_body)],
)
def create_announcement(
    course_id: UUID,
    announcement: AnnouncementCreateRequest,
    current_user: User | None = Depends(get_current_user_optional),
    controller: CourseController = Depends(get_course_controller),
):
    """
    สร้าง announcement ใหม่สำหรับ course
    
    Dev Mode: ถ้าไม่ได้ login จะใช้ hardcoded dev user
    Production: ต้อง login (oauth2-proxy)
    
    Raises:
        404: Course not found
        400: Invalid message or author
        500: Internal server error
    """
    # Dev Mode: ใช้ hardcoded user ID (TODO: ลบออกตอนเปิด Auth)
    if current_user is None:
        author_id = UUID("0685445d-c06b-4110-ba10-743fdf014639")
    else:
        author_id = current_user.id
    
    created_announcement = controller.create_announcement(
        course_id=course_id,
        message=announcement.message,
        author_id=author_id
    )
    return announcement_response(created_announcement)


@router.patch(
    "/{course_id}/announcements/{announcement_id}",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_non_empty_body)],
)
def update_announcement(
    course_id: UUID,
    announcement_id: UUID,
    announcement: AnnouncementUpdateRequest,
    controller: CourseController = Depends(get_course_controller),
):
    """
    อัปเดต announcement ของ course
    
    Raises:
        404: Course or announcement not found
        400: Invalid message or announcement doesn't belong to course
        500: Internal server error
    """
    updated_announcement = controller.update_announcement(
        course_id=course_id,
        announcement_id=announcement_id,
        message=announcement.message
    )
    return announcement_response(updated_announcement)
