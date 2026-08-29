from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.configs.settings import settings
from app.exceptions.domain import InvalidCredentialsError, InvalidTokenError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.security import verify_password


class AuthService:
    def __init__(self, db: Session, user_repo: UserRepository):
        self.db = db
        self.user_repo = user_repo

    def authenticate(self, username: str, password: str) -> User:
        user = self.user_repo.find_by_login(username)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("student id / email หรือรหัสผ่านไม่ถูกต้อง")
        return user

    def create_access_token(self, user: User) -> str:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        payload = {"sub": str(user.id), "exp": expire}
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def get_user_from_token(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            user_id = UUID(payload["sub"])
        except (JWTError, KeyError, ValueError) as e:
            raise InvalidTokenError("token ไม่ถูกต้องหรือหมดอายุแล้ว") from e

        user = self.user_repo.find_by_id(user_id)
        if user is None:
            raise InvalidTokenError("ไม่พบผู้ใช้ของ token นี้")
        return user
