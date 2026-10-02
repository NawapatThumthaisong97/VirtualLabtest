from uuid import UUID

from app.models.courses import Course
from app.schemas.course_schema import CourseCreateRequest, CourseUpdateRequest
from app.services.courses_service import CourseService


class CourseController:
    """
    Controller สำหรับ Course
    ทำหน้าที่เป็นตัวกลางระหว่าง Route และ Service
    """

    def __init__(self, course_service: CourseService):
        self.course_service = course_service

    def get_course(self, course_id: UUID) -> Course:
        """
        ดึงข้อมูล course ตาม ID
        
        Raises:
            CourseNotFoundError: จาก service ถ้าหา course ไม่เจอ
        """
        return self.course_service.get_course_by_id(course_id)

    def get_course_detail(self, course_id: UUID) -> tuple[Course, list]:
        """
        ดึงข้อมูล course พร้อม announcements
        
        Raises:
            CourseNotFoundError: จาก service ถ้าหา course ไม่เจอ
        """
        return self.course_service.get_course_detail(course_id)

    def create_course(self, course: CourseCreateRequest) -> Course:
        """
        สร้าง course ใหม่
        
        Raises:
            ConflictError: จาก service ถ้ามี course ซ้ำ
        """
        return self.course_service.create_course(Course(**course.model_dump()))

    def get_all_courses(self) -> list[Course]:
        """ดึงข้อมูล course ทั้งหมด"""
        return self.course_service.get_all_courses()

    def update_course(self, course_id: UUID, updated_course: CourseUpdateRequest) -> Course:
        """
        อัปเดตข้อมูล course
        
        Raises:
            CourseNotFoundError: จาก service ถ้าหา course ไม่เจอ
            ConflictError: จาก service ถ้าข้อมูลชนกัน
        """
        return self.course_service.update_course(course_id, updated_course)

    def soft_delete_course(self, course_id: UUID) -> None:
        """
        ลบ course แบบ soft delete
        
        Raises:
            CourseNotFoundError: จาก service ถ้าหา course ไม่เจอ
        """
        self.course_service.soft_delete_course(course_id)

    def hard_delete_course(self, course_id: UUID) -> None:
        """
        ลบ course แบบ hard delete
        
        Raises:
            CourseNotFoundError: จาก service ถ้าหา course ไม่เจอ
        """
        self.course_service.hard_delete_course(course_id)

    def get_courses_by_lecturer(self, lecturer_name: str) -> list[Course]:
        """
        ดึง courses ที่สอนโดยอาจารย์คนนี้
        
        Raises:
            ValidationError: จาก service ถ้า lecturer_name ไม่ถูกต้อง
        """
        return self.course_service.get_courses_by_lecturer(lecturer_name)

    def get_courses_by_student(self, student_id: UUID) -> list[Course]:
        """ดึง courses ที่นักเรียนคนนี้ลงทะเบียน"""
        return self.course_service.get_courses_by_student(student_id)

    def update_course_announcement_ids(
        self, course_id: UUID, announcement_ids: list[UUID]
    ) -> Course:
        """
        อัปเดต announcement IDs ของ course
        
        Raises:
            CourseNotFoundError: จาก service ถ้าหา course ไม่เจอ
        """
        return self.course_service.update_announcement_ids(course_id, announcement_ids)

    def create_announcement(self, course_id: UUID, message: str, author_id: UUID):
        """
        สร้าง announcement ใหม่สำหรับ course
        
        Raises:
            CourseNotFoundError: จาก service ถ้าหา course ไม่เจอ
            ValidationError: จาก service ถ้า message ไม่ถูกต้อง
        """
        return self.course_service.create_announcement(course_id, message, author_id)

    def update_announcement(
        self, course_id: UUID, announcement_id: UUID, message: str
    ):
        """
        อัปเดต announcement
        
        Raises:
            CourseNotFoundError: จาก service ถ้าหา course หรือ announcement ไม่เจอ
            ValidationError: จาก service ถ้า message ไม่ถูกต้อง
        """
        return self.course_service.update_announcement(course_id, announcement_id, message)
