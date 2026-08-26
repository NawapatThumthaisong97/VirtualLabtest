from app.models.course import Course
from app.repositories.base import BaseRepository
from uuid import UUID
from app.repositories.course_repositories import CourseRepository
from app.models.announcement import Announcement
from app.repositories.annoucement_repositories import AnnouncementRepository

class CourseService:
    def __init__(self, course_repository: CourseRepository, announcement_repository: AnnouncementRepository):
        self.course_repository = course_repository
        self.announcement_repository = announcement_repository

    def get_course_by_id(self, course_id: UUID) -> tuple[Course | None, list[Announcement]]:
        course = self.course_repository.find_by_id(course_id)
        announcements = self.announcement_repository.find_by_course_id(course_id) if course else []
        file = self.file_repository.find_by_course_id(course_id) if course else []
        return course, announcements, file

    def create_course(self, course: Course) -> Course:
        return self.course_repository.save(course)
    
    def get_all_courses(self) -> list[Course]:
        return self.course_repository.get_all()
    
    def update_course(self, course_id: UUID, updated_course: Course) -> Course | None:
        existing_course = self.course_repository.find_by_id(course_id)
        if not existing_course:
            return None
        for attr, value in updated_course.__dict__.items():
            if attr != "id" and value is not None:
                setattr(existing_course, attr, value)
        return self.course_repository.save(existing_course)
    
    def delete_course(self, course_id: UUID) -> bool:
        existing_course = self.course_repository.find_by_id(course_id)
        if not existing_course:
            return False
        self.course_repository.delete(existing_course)
        return True
    
    def get_courses_by_lecturer(self, lecturer_name: str) -> list[Course]:
        return self.course_repository.find_by_lecturer(lecturer_name)
    
    def get_courses_by_student(self, student_id: UUID) -> list[Course]:
        return self.course_repository.find_by_student(student_id)
    
    