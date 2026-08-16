"""Domain exceptions — error ที่เกิดจาก business rule ไม่ใช่ HTTP
ทุก error ในระบบสืบทอดจาก DomainError เพื่อให้ exception handler
ใน main.py จับได้ที่เดียว แล้วแปลงเป็น HTTP response
"""


class DomainError(Exception):
    """base ของ error ทั้งหมด"""

    code: str = "internal_error"

    def __init__(self, message: str | None = None):
        self.message = message or self.__class__.__name__
        super().__init__(self.message)


# ---------- 404 ----------
class NotFoundError(DomainError):
    """หาข้อมูลที่ต้องการไม่เจอ"""

    code = "not_found"


class LabNotFoundError(NotFoundError):
    code = "lab_not_found"


class CourseNotFoundError(NotFoundError):
    code = "course_not_found"


# ---------- 409 ----------
class ConflictError(DomainError):
    """ข้อมูลชนกับที่มีอยู่แล้ว"""

    code = "conflict"


class DuplicateOrderNoError(ConflictError):
    code = "duplicate_order_no"


# ---------- 403 ----------
class ForbiddenError(DomainError):
    """ไม่มีสิทธิ์ทำสิ่งนี้"""

    code = "forbidden"


# ---------- 400 ----------
class ValidationError(DomainError):
    """ข้อมูลไม่ผ่านกฎทาง business (คนละเรื่องกับ Pydantic validation)"""

    code = "validation_error"
