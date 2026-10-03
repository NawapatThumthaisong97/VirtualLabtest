from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.adapters.local_storage import local_storage
from app.exceptions.domain import (
    ConflictError,
    CourseNotFoundError,
    ValidationError,
    InternalServerError,
)
from app.models.courses import Course
from app.repositories.annoucement_repositories import AnnouncementRepository
from app.repositories.courses_repositories import CourseRepository
from app.schemas.course_schema import CourseUpdateRequest


class CourseService:
    def __init__(
        self,
        course_repository: CourseRepository,
        announcement_repository: AnnouncementRepository,
    ):
        self.course_repository = course_repository
        self.announcement_repository = announcement_repository

    def get_course_by_id(self, course_id: UUID) -> Course:
        """
        ดึงข้อมูล course ตาม ID
        
        Raises:
            CourseNotFoundError: ถ้าหา course ไม่เจอ
        """
        try:
            course = self.course_repository.find_by_id(course_id)
            if course is None:
                raise CourseNotFoundError(f"Course {course_id} not found")
            return course
        except CourseNotFoundError:
            raise
        except Exception as e:
            raise InternalServerError(f"Failed to fetch course: {str(e)}") from e

    def get_course_detail(self, course_id: UUID) -> tuple[Course, list]:
        """
        ดึงข้อมูล course พร้อม announcements
        
        Raises:
            CourseNotFoundError: ถ้าหา course ไม่เจอ
        """
        try:
            course = self.get_course_by_id(course_id)
            announcements = self.announcement_repository.find_by_course_id(course_id)
            return course, announcements
        except CourseNotFoundError:
            raise
        except Exception as e:
            raise InternalServerError(
                f"Failed to fetch course detail: {str(e)}"
            ) from e

    def create_course(self, course: Course) -> Course:
        """
        สร้าง course ใหม่
        
        Raises:
            ConflictError: ถ้ามี course ที่ซ้ำกัน (เช่น code ซ้ำ)
        """
        try:
            saved_course = self.course_repository.save(course)
            self.course_repository.db.commit()
            return saved_course
        except IntegrityError as e:
            self.course_repository.db.rollback()
            # ตรวจสอบว่า error เกิดจาก unique constraint ของ code หรือไม่
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            if 'code' in error_msg or 'courses_code_key' in error_msg:
                raise ConflictError(
                    f"Course with code '{course.code}' already exists"
                ) from e
            raise ConflictError("Course data conflicts with existing record") from e
        except Exception as e:
            self.course_repository.db.rollback()
            raise InternalServerError(f"Failed to create course: {str(e)}") from e

    def get_all_courses(self) -> list[Course]:
        """ดึงข้อมูล course ทั้งหมด"""
        try:
            return self.course_repository.get_all()
        except Exception as e:
            raise InternalServerError(f"Failed to fetch courses: {str(e)}") from e

    def update_course(
        self, course_id: UUID, course_update: CourseUpdateRequest
    ) -> Course:
        """
        อัปเดตข้อมูล course
        
        Raises:
            CourseNotFoundError: ถ้าหา course ไม่เจอ
            ConflictError: ถ้าข้อมูลที่อัปเดตชนกับ course อื่น
        """
        try:
            existing_course = self.course_repository.find_by_id(course_id)
            if not existing_course:
                raise CourseNotFoundError(f"Course {course_id} not found")

            for field, value in course_update.model_dump(exclude_unset=True).items():
                setattr(existing_course, field, value)
            self.course_repository.db.commit()
            return existing_course
        except IntegrityError as e:
            self.course_repository.db.rollback()
            raise ConflictError(
                f"Update failed: course code may conflict with existing course"
            ) from e
        except CourseNotFoundError:
            raise
        except Exception as e:
            self.course_repository.db.rollback()
            raise InternalServerError(f"Failed to update course: {str(e)}") from e

    def hard_delete_course(self, course_id: UUID) -> None:
        """
        ลบ course แบบ hard delete (ลบจริงออกจาก database)
        
        Raises:
            CourseNotFoundError: ถ้าหา course ไม่เจอ (รวมที่ถูกลบไปแล้ว)
        """
        try:
            existing_course = self.course_repository.find_by_id_including_deleted(
                course_id
            )
            if not existing_course:
                raise CourseNotFoundError(f"Course {course_id} not found")
            self.course_repository.hard_delete(existing_course)
            self.course_repository.db.commit()
        except CourseNotFoundError:
            raise
        except Exception as e:
            self.course_repository.db.rollback()
            raise InternalServerError(
                f"Failed to delete course: {str(e)}"
            ) from e

    def soft_delete_course(self, course_id: UUID) -> None:
        """
        ลบ course แบบ soft delete (ทำเครื่องหมายว่าถูกลบ)
        
        Raises:
            CourseNotFoundError: ถ้าหา course ไม่เจอ
        """
        try:
            existing_course = self.course_repository.find_by_id(course_id)
            if not existing_course:
                raise CourseNotFoundError(f"Course {course_id} not found")
            self.course_repository.soft_delete(existing_course)
            self.course_repository.db.commit()
        except CourseNotFoundError:
            raise
        except Exception as e:
            self.course_repository.db.rollback()
            raise InternalServerError(
                f"Failed to delete course: {str(e)}"
            ) from e

    def get_courses_by_lecturer(self, lecturer_name: str) -> list[Course]:
        """
        ดึง courses ที่สอนโดยอาจารย์คนนี้
        
        Raises:
            ValidationError: ถ้า lecturer_name ไม่ถูกต้อง
        """
        try:
            if not lecturer_name or not lecturer_name.strip():
                raise ValidationError("Lecturer name cannot be empty")
            return self.course_repository.find_by_lecturer(lecturer_name)
        except ValidationError:
            raise
        except Exception as e:
            raise InternalServerError(
                f"Failed to fetch courses by lecturer: {str(e)}"
            ) from e

    def get_courses_by_student(self, student_id: UUID) -> list[Course]:
        """ดึง courses ที่นักเรียนคนนี้ลงทะเบียน"""
        try:
            return self.course_repository.find_by_student(student_id)
        except Exception as e:
            raise InternalServerError(
                f"Failed to fetch courses by student: {str(e)}"
            ) from e

    def check_course_access(self, course_id: UUID, user_id: UUID, user_role, user_name: str) -> bool:
        """
        ตรวจสอบว่า user มีสิทธิ์เข้าถึง course นี้หรือไม่
        
        Returns:
            True: ถ้ามีสิทธิ์เข้าถึง
            False: ถ้าไม่มีสิทธิ์
        """
        from app.models.user import UserRole
        
        try:
            # Admin เข้าถึงได้ทุก course
            if user_role == UserRole.ADMIN:
                return True
            
            # Instructor ต้องเป็นคนสอนวิชานี้
            if user_role == UserRole.INSTRUCTOR:
                return self.course_repository.is_lecturer_teaching(course_id, user_name)
            
            # Student ต้อง enroll วิชานี้
            return self.course_repository.is_student_enrolled(course_id, user_id)
            
        except Exception as e:
            raise InternalServerError(
                f"Failed to check course access: {str(e)}"
            ) from e

    def save_course_image(self, course_id: UUID, filename: str, source) -> Course:
        """
        บันทึกรูปภาพของ course
        
        Raises:
            CourseNotFoundError: ถ้าหา course ไม่เจอ
            ValidationError: ถ้า filename หรือ source ไม่ถูกต้อง
        """
        try:
            course = self.course_repository.find_by_id(course_id)
            if not course:
                raise CourseNotFoundError(f"Course {course_id} not found")

            if not filename or not filename.strip():
                raise ValidationError("Filename cannot be empty")

            safe_filename = Path(filename).name
            if not safe_filename:
                raise ValidationError("Invalid filename")

            key = f"courses/{course_id}/{safe_filename}"
            local_storage.save(key, source.file)
            course.image_url = key
            self.course_repository.db.commit()
            return course
        except (CourseNotFoundError, ValidationError):
            raise
        except Exception as e:
            self.course_repository.db.rollback()
            raise InternalServerError(
                f"Failed to save course image: {str(e)}"
            ) from e

    def update_announcement_ids(
        self, course_id: UUID, announcement_ids: list[UUID]
    ) -> Course:
        """
        อัปเดต announcement IDs ของ course
        
        Raises:
            CourseNotFoundError: ถ้าหา course ไม่เจอ
        """
        try:
            course = self.course_repository.find_by_id(course_id)
            if not course:
                raise CourseNotFoundError(f"Course {course_id} not found")

            course.announcement_ids = announcement_ids
            self.course_repository.db.commit()
            return course
        except CourseNotFoundError:
            raise
        except Exception as e:
            self.course_repository.db.rollback()
            raise InternalServerError(
                f"Failed to update announcement IDs: {str(e)}"
            ) from e

    def create_announcement(
        self, course_id: UUID, message: str, author_id: UUID
    ):
        """
        สร้าง announcement ใหม่สำหรับ course
        
        Raises:
            CourseNotFoundError: ถ้าหา course ไม่เจอ
            ValidationError: ถ้า message ไม่ถูกต้อง
            InternalServerError: ถ้าเกิด error อื่น ๆ
        """
        try:
            # ตรวจสอบว่า course มีอยู่จริง
            course = self.course_repository.find_by_id(course_id)
            if not course:
                raise CourseNotFoundError(f"Course {course_id} not found")

            if not message or not message.strip():
                raise ValidationError("Announcement message cannot be empty")

            from app.models.announcement import Announcement
            announcement = Announcement(
                course_id=course_id,
                author_id=author_id,
                message=message.strip()
            )
            
            saved_announcement = self.announcement_repository.create(announcement)
            self.course_repository.db.commit()
            
            # Refresh เพื่อให้ได้ relationship data (author)
            try:
                self.course_repository.db.refresh(saved_announcement)
            except Exception as refresh_error:
                # ถ้า refresh ล้มเหลว ก็ยังคืน announcement ที่สร้างได้
                # แต่อาจไม่มี author relationship loaded
                pass
            
            return saved_announcement
            
        except (CourseNotFoundError, ValidationError):
            self.course_repository.db.rollback()
            raise
        except IntegrityError as e:
            self.course_repository.db.rollback()
            # ตรวจสอบว่า error มาจาก foreign key constraint
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            if 'author_id' in error_msg or 'users' in error_msg:
                raise ValidationError(f"Invalid author ID: {author_id}") from e
            elif 'course_id' in error_msg or 'courses' in error_msg:
                raise CourseNotFoundError(f"Course {course_id} not found") from e
            raise InternalServerError(
                f"Failed to create announcement: database constraint violation"
            ) from e
        except Exception as e:
            self.course_repository.db.rollback()
            raise InternalServerError(
                f"Failed to create announcement: {str(e)}"
            ) from e

    def update_announcement(
        self, course_id: UUID, announcement_id: UUID, message: str
    ):
        """
        อัปเดต announcement
        
        Raises:
            CourseNotFoundError: ถ้าหา course หรือ announcement ไม่เจอ
            ValidationError: ถ้า message ไม่ถูกต้อง หรือ announcement ไม่ได้อยู่ใน course นี้
            InternalServerError: ถ้าเกิด error อื่น ๆ
        """
        try:
            # ตรวจสอบว่า course มีอยู่จริง
            course = self.course_repository.find_by_id(course_id)
            if not course:
                raise CourseNotFoundError(f"Course {course_id} not found")

            # ตรวจสอบว่า announcement มีอยู่จริง
            announcement = self.announcement_repository.find_by_id(announcement_id)
            if not announcement:
                raise CourseNotFoundError(f"Announcement {announcement_id} not found")

            # ตรวจสอบว่า announcement อยู่ใน course นี้จริง
            if announcement.course_id != course_id:
                raise ValidationError(
                    f"Announcement {announcement_id} does not belong to course {course_id}"
                )

            if not message or not message.strip():
                raise ValidationError("Announcement message cannot be empty")

            announcement.message = message.strip()
            updated_announcement = self.announcement_repository.update(announcement)
            self.course_repository.db.commit()
            
            # Refresh เพื่อให้ได้ relationship data
            try:
                self.course_repository.db.refresh(updated_announcement)
            except Exception as refresh_error:
                # ถ้า refresh ล้มเหลว ก็ยังคืน announcement ที่ update ได้
                pass
            
            return updated_announcement
            
        except (CourseNotFoundError, ValidationError):
            self.course_repository.db.rollback()
            raise
        except IntegrityError as e:
            self.course_repository.db.rollback()
            raise InternalServerError(
                f"Failed to update announcement: database constraint violation"
            ) from e
        except AttributeError as e:
            self.course_repository.db.rollback()
            raise InternalServerError(
                f"Failed to update announcement: invalid attribute access - {str(e)}"
            ) from e
        except Exception as e:
            self.course_repository.db.rollback()
            raise InternalServerError(
                f"Failed to update announcement: {str(e)}"
            ) from e
    