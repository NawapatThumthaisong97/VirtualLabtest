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


class PrewarmNotFoundError(NotFoundError):
    code = "prewarm_not_found"


# ---------- 409 ----------
class ConflictError(DomainError):
    """ข้อมูลชนกับที่มีอยู่แล้ว"""

    code = "conflict"


class DuplicateOrderNoError(ConflictError):
    code = "duplicate_order_no"


class SessionAlreadyExistsError(ConflictError):
    code = "session_already_exists"


class QuotaExceededError(ConflictError):
    code = "quota_exceeded"


class CloudBurstDisabledError(ConflictError):
    """admin ปิด burst ขึ้น AWS (PATCH /admin/cloud/controls) เช่นเกิน budget"""
    code = "cloud_burst_disabled"


# ---------- 401 ----------
class UnauthorizedError(DomainError):
    """ยังไม่ได้ล็อกอิน หรือ token ใช้ไม่ได้"""

    code = "unauthorized"


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"


class SSOAuthenticationError(UnauthorizedError):
    """การยืนยันตัวตนผ่านระบบ SSO ไม่สำเร็จ หรือข้อมูลจาก SSO ไม่ครบถ้วน"""

    code = "sso_authentication_failed"


# ---------- 403 ----------
class ForbiddenError(DomainError):
    """ไม่มีสิทธิ์ทำสิ่งนี้"""

    code = "forbidden"


class InvalidEmailDomainError(ForbiddenError):
    """อีเมลไม่อยู่ภายใต้โดเมนของมหาวิทยาลัยที่อนุญาต"""

    code = "invalid_email_domain"


# ---------- 400 ----------
class ValidationError(DomainError):
    """ข้อมูลไม่ผ่านกฎทาง business (คนละเรื่องกับ Pydantic validation)"""

    code = "validation_error"


class InvalidSessionStateError(ValidationError):
    code = "invalid_session_state"


class LabImageMissingError(ValidationError):
    code = "lab_image_missing"


class InvalidLabImageError(ValidationError):
    """image ที่จะผูกกับ lab ไม่มีอยู่ หรือเป็นของวิชาอื่น"""
    code = "invalid_lab_image"


class LabImageNotReadyError(ValidationError):
    """publish lab ที่ image ยังสแกนไม่ผ่าน (นักศึกษาจะเปิด lab ไม่ได้)"""
    code = "lab_image_not_ready"


# ---------- 500 ----------
class InternalServerError(DomainError):
    """Internal server error"""
    
    code = "internal_server_error"


class ClusterOperationError(InternalServerError):
    code = "cluster_operation_error"
