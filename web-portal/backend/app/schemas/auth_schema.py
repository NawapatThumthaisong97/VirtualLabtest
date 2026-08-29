from uuid import UUID

from app.models.user import UserRole
from app.schemas.base import CamelModel


class LoginRequest(CamelModel):
    username: str
    password: str


class TokenResponse(CamelModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(CamelModel):
    id: UUID
    email: str
    name: str
    student_id: str | None
    role: UserRole
