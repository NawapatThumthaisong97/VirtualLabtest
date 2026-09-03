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


class LabDocNotFoundError(NotFoundError):
    """แลปมีอยู่ แต่ยังไม่ได้แนบเอกสาร หรือไฟล์หายไปจาก storage"""

    code = "lab_doc_not_found"


class SessionNotFoundError(NotFoundError):
    code = "session_not_found"


class UserNotFoundError(NotFoundError):
    code = "user_not_found"


class LabImageNotFoundError(NotFoundError):
    code = "lab_image_not_found"


# ---------- 409 ----------
class ConflictError(DomainError):
    """ข้อมูลชนกับที่มีอยู่แล้ว"""

    code = "conflict"


class DuplicateOrderNoError(ConflictError):
    code = "duplicate_order_no"


class SessionAlreadyExistsError(ConflictError):
    code = "session_already_exists"


# ---------- 401 ----------
class UnauthorizedError(DomainError):
    """ยังไม่ได้ล็อกอิน หรือ token ใช้ไม่ได้"""

    code = "unauthorized"


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"


# ---------- 403 ----------
class ForbiddenError(DomainError):
    """ไม่มีสิทธิ์ทำสิ่งนี้"""

    code = "forbidden"


# ---------- 400 ----------
class ValidationError(DomainError):
    """ข้อมูลไม่ผ่านกฎทาง business (คนละเรื่องกับ Pydantic validation)"""

    code = "validation_error"


class InvalidSessionStateError(ValidationError):
    code = "invalid_session_state"


class LabImageMissingError(ValidationError):
    code = "lab_image_missing"


# ---------- 500 ----------
class InternalServerError(DomainError):
    """Internal server error"""
    
    code = "internal_server_error"


class ClusterOperationError(InternalServerError):
    code = "cluster_operation_error"
