from app.models.course import Course
from app.repositories.base import BaseRepository
from uuid import UUID
from app.repositories.course_repositories import CourseRepository
from app.models.announcement import Announcement
from app.repositories.annoucement_repositories import AnnouncementRepository
from app.services.course_service import CourseService

class CourseController:
    def __init__(self, course_service: CourseService):
        self.course_service = course_service

    def get_course(self, course_id: UUID) -> tuple[Course | None, list[Announcement]]:
        return self.course_service.get_course_by_id(course_id)

    def create_course(self, course: Course) -> Course:
        return self.course_service.create_course(course)
    
    def get_all_courses(self) -> list[Course]:
        return self.course_service.get_all_courses()
    
    def update_course(self, course_id: UUID, updated_course: Course) -> Course | None:
        return self.course_service.update_course(course_id, updated_course)
    
    def delete_course(self, course_id: UUID) -> bool:
        return self.course_service.delete_course(course_id)
    
    def get_courses_by_lecturer(self, lecturer_name: str) -> list[Course]:
        return self.course_service.get_courses_by_lecturer(lecturer_name)
    
    def get_courses_by_student(self, student_id: UUID) -> list[Course]:
        return self.course_service.get_courses_by_student(student_id)