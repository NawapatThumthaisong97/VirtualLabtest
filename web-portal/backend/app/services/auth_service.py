from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions.domain import InvalidCredentialsError, InvalidTokenError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.jwt_service import JWTService
from app.utils.security import verify_password


class AuthService:
    def __init__(self, db: Session, user_repo: UserRepository):
        self.db = db
        self.user_repo = user_repo
        self.jwt_service = JWTService(db)

    def authenticate(self, username: str, password: str) -> User:
        user = self.user_repo.find_by_login(username)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("student id / email หรือรหัสผ่านไม่ถูกต้อง")
        return user

    def create_access_token(self, user: User) -> str:
        return self.jwt_service.create_access_token(user)

    def get_user_from_token(self, token: str) -> User:
        claims = self.jwt_service.decode_access_token(token)
        subject = claims.user_id or claims.sub
        if subject is None:
            raise InvalidTokenError("token ไม่ถูกต้องหรือหมดอายุแล้ว")
        user_id = UUID(subject)

        user = self.user_repo.find_by_id(user_id)
        if user is None:
            raise InvalidTokenError("ไม่พบผู้ใช้ของ token นี้")
        return user
