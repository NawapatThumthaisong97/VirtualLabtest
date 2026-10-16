from uuid import UUID

from app.models.user import UserRole
from app.schemas.base import CamelModel


class LoginRequest(CamelModel):
    username: str
    password: str


class SSOLoginRequest(CamelModel):
    """ข้อมูลที่ส่งมาจากระบบ SSO ของมหาวิทยาลัย (เช่น Google OAuth2) หลังล็อกอินสำเร็จ"""

    code: str | None = None
    id_token: str | None = None
    access_token: str | None = None
    redirect_uri: str | None = None
    email: str | None = None
    name: str | None = None
    student_id: str | None = None
    email_verified: bool = True


class SSOAuthorizeResponse(CamelModel):
    authorization_url: str


class TokenResponse(CamelModel):
    access_token: str
    token_type: str = "bearer"


class JWTPayload(CamelModel):
    """โครงสร้างข้อมูลใน JWT Payload (ไม่มีความลับเชิงลึก เช่น รหัสผ่าน หรือ API Key)"""

    sub: str
    email: str
    name: str
    student_id: str | None = None
    role: UserRole
    iat: int | None = None
    exp: int


class MeResponse(CamelModel):
    id: UUID
    email: str
    name: str
    student_id: str | None
    role: UserRole
