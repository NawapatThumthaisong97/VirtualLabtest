from app.models.courses import Course
from uuid import UUID
from app.repositories.courses_repositories import CourseRepository
from app.repositories.annoucement_repositories import AnnouncementRepository
from app.schemas.course_schema import CourseUpdateRequest
from app.adapters.local_storage import local_storage
from pathlib import Path

class CourseService:
    def __init__(self, course_repository: CourseRepository, announcement_repository: AnnouncementRepository):
        self.course_repository = course_repository
        self.announcement_repository = announcement_repository

    def get_course_by_id(self, course_id: UUID) -> Course | None:
        return self.course_repository.find_by_id(course_id)

    def create_course(self, course: Course) -> Course:
        saved_course = self.course_repository.save(course)
        self.course_repository.db.commit()
        return saved_course
    
    def get_all_courses(self) -> list[Course]:
        return self.course_repository.get_all()
    
    def update_course(self, course_id: UUID, updated_course: CourseUpdateRequest) -> Course | None:
        existing_course = self.course_repository.find_by_id(course_id)
        if not existing_course:
            return None
        for attr, value in updated_course.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(existing_course, attr, value)
        saved_course = self.course_repository.save(existing_course)
        self.course_repository.db.commit()
        return saved_course
    
    def hard_delete_course(self, course_id: UUID) -> bool:
        existing_course = self.course_repository.find_by_id_including_deleted(course_id)
        if not existing_course:
            return False
        self.course_repository.hard_delete(existing_course)
        self.course_repository.db.commit()
        return True
    
    def soft_delete_course(self, course_id: UUID) -> bool:
        existing_course = self.course_repository.find_by_id(course_id)
        if not existing_course:
            return False
        self.course_repository.soft_delete(existing_course)
        self.course_repository.db.commit()
        return True
    
    def get_courses_by_lecturer(self, lecturer_name: str) -> list[Course]:
        return self.course_repository.find_by_lecturer(lecturer_name)
    
    def get_courses_by_student(self, student_id: UUID) -> list[Course]:
        return self.course_repository.find_by_student(student_id)

    def save_course_image(self, course_id: UUID, filename: str, source) -> Course | None:
        course = self.course_repository.find_by_id(course_id)
        if not course:
            return None
        safe_filename = Path(filename).name
        key = f"courses/{course_id}/{safe_filename}"
        local_storage.save(key, source.file)
        course.image_url = key
        self.course_repository.db.commit()
        return course
    
    