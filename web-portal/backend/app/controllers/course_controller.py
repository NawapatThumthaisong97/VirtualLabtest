from app.models.courses import Course
from uuid import UUID
from app.repositories.courses_repositories import CourseRepository
from app.schemas.course_schema import CourseCreateRequest, CourseUpdateRequest
from app.services.courses_service import CourseService

class CourseController:
    def __init__(self, course_service: CourseService):
        self.course_service = course_service

    def get_course(self, course_id: UUID) -> Course | None:
        return self.course_service.get_course_by_id(course_id)

    def create_course(self, course: CourseCreateRequest) -> Course:
        return self.course_service.create_course(Course(**course.model_dump()))
    
    def get_all_courses(self) -> list[Course]:
        return self.course_service.get_all_courses()
    
    def update_course(self, course_id: UUID, updated_course: CourseUpdateRequest) -> Course | None:
        return self.course_service.update_course(course_id, updated_course)
    
    def soft_delete_course(self, course_id: UUID) -> bool:
        return self.course_service.soft_delete_course(course_id)

    def hard_delete_course(self, course_id: UUID) -> bool:
        return self.course_service.hard_delete_course(course_id)
    
    def get_courses_by_lecturer(self, lecturer_name: str) -> list[Course]:
        return self.course_service.get_courses_by_lecturer(lecturer_name)
    
    def get_courses_by_student(self, student_id: UUID) -> list[Course]:
        return self.course_service.get_courses_by_student(student_id)
