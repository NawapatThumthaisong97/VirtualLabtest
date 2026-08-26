from app.models.course import Course
from app.repositories.base import BaseRepository
from uuid import UUID
from app.repositories.course_repositories import CourseRepository
from app.models.announcement import Announcement
from app.repositories.annoucement_repositories import AnnouncementRepository
from app.services.course_service import CourseService
from app.controllers.course_controller import CourseController

from fastapi import APIRouter, Depends, Query, status as http_status
from app.middlewares.request_validation import require_non_empty_body
from sqlalchemy.orm import Session

router = APIRouter()
    
def get_course_controller(db: Session = Depends(BaseRepository.get_db)):
        course_repository = CourseRepository(db)
        announcement_repository = AnnouncementRepository(db)
        course_service = CourseService(course_repository, announcement_repository)
        return CourseController(course_service)
    
@router.get("/courses/{course_id}", response_model=Course)
async def get_course(course_id: UUID, controller: CourseController = Depends(get_course_controller)):
    """ดึงข้อมูล course โดยใช้ course_id"""
    return controller.get_course_by_id(course_id)

@router.post("/courses", response_model=Course, status_code=http_status.HTTP_201_CREATED)
@require_non_empty_body
async def create_course(course: Course, controller: CourseController = Depends(get_course_controller)):
    """สร้าง course ใหม่"""
    return controller.create_course(course)

@router.get("/courses", response_model=list[Course])
async def get_all_courses(controller: CourseController = Depends(get_course_controller)):
    """ดึงข้อมูล course ทั้งหมด"""
    return controller.get_all_courses()

@router.patch("/courses/{course_id}", response_model=Course)
@require_non_empty_body
async def update_course(course_id: UUID, updated_course: Course, controller: CourseController = Depends(get_course_controller)):
    """อัปเดตข้อมูล course โดยใช้ course_id"""
    return controller.update_course(course_id, updated_course)

@router.delete("/courses/{course_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_course(course_id: UUID, controller: CourseController = Depends(get_course_controller)):
    """ลบ course โดยใช้ course_id"""
    controller.delete_course(course_id)
    return {"message": "Course deleted successfully."}