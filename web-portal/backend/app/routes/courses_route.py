from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
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
    CourseCreateRequest,
    CourseDetailResponse,
    CourseResponse,
    CourseUpdateRequest,
)
from app.services.courses_service import CourseService
from app.controllers.course_controller import CourseController
from app.middlewares.request_validation import require_non_empty_body
from app.adapters.local_storage import local_storage
from app.exceptions.domain import NotFoundError

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
    return AnnouncementResponse(
        id=announcement.id,
        message=announcement.message,
        created_at=announcement.created_at,
        author_name=announcement.author.name if announcement.author else None,
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
        raise HTTPException(
            status_code=400, detail="Only JPEG, PNG, and WebP images are supported"
        )
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
