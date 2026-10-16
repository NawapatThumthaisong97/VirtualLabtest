from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.adapters import sso_adapter as sso_adapter_module
from app.adapters.sso_adapter import SSOUserInfo
from app.configs.settings import settings
from app.exceptions.domain import (
    InvalidCredentialsError,
    InvalidEmailDomainError,
    InvalidTokenError,
    SSOAuthenticationError,
)
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth_schema import SSOLoginRequest
from app.utils.security import verify_password


class AuthService:
    def __init__(self, db: Session, user_repo: UserRepository):
        self.db = db
        self.user_repo = user_repo

    @staticmethod
    def validate_university_email(email: str) -> str:
        """ตรวจสอบว่าอีเมลถูกต้องและอยู่ภายใต้โดเมนของมหาวิทยาลัยที่อนุญาตเท่านั้น"""
        normalized = (email or "").strip().lower()
        if not normalized or "@" not in normalized or " " in normalized:
            raise SSOAuthenticationError("รูปแบบอีเมลจากระบบ SSO ไม่ถูกต้อง")

        local_part, domain = normalized.rsplit("@", 1)
        if not local_part or not domain or "@" in local_part:
            raise SSOAuthenticationError("รูปแบบอีเมลจากระบบ SSO ไม่ถูกต้อง")

        allowed_domains = settings.allowed_email_domains
        if domain not in allowed_domains:
            domains_str = ", ".join(allowed_domains)
            raise InvalidEmailDomainError(
                f"อนุญาตให้เข้าสู่ระบบเฉพาะอีเมลภายใต้โดเมนของมหาวิทยาลัยเท่านั้น ({domains_str})"
            )

        return normalized

    def get_sso_authorize_url(
        self,
        state: str | None = None,
        redirect_uri: str | None = None,
    ) -> str:
        return sso_adapter_module.sso_adapter.build_authorization_url(
            state=state,
            redirect_uri=redirect_uri,
        )

    def resolve_sso_user_info(
        self,
        payload: SSOLoginRequest,
        forwarded_email: str | None = None,
        forwarded_name: str | None = None,
    ) -> SSOUserInfo:
        """ดึงข้อมูลผู้ใช้จาก Google OAuth2 (code / id_token / access_token) หรือจาก SSO callback"""
        adapter = sso_adapter_module.sso_adapter

        if payload.code:
            sso_info = adapter.exchange_code(
                payload.code, redirect_uri=payload.redirect_uri
            )
        elif payload.id_token:
            sso_info = adapter.verify_id_token(payload.id_token)
        elif payload.access_token:
            sso_info = adapter.fetch_user_info(payload.access_token)
        elif payload.email or forwarded_email:
            raw_email = (payload.email or forwarded_email or "").strip()
            raw_name = (payload.name or forwarded_name or "").strip()
            sso_info = SSOUserInfo(
                email=raw_email,
                name=raw_name,
                email_verified=payload.email_verified,
                student_id=payload.student_id,
            )
        else:
            raise SSOAuthenticationError(
                "ต้องส่ง code, id_token, access_token หรือข้อมูลผู้ใช้จากระบบ SSO"
            )

        if not sso_info.email_verified:
            raise SSOAuthenticationError("อีเมลจากระบบ SSO ยังไม่ได้รับการยืนยัน")

        if payload.student_id and not sso_info.student_id:
            sso_info.student_id = payload.student_id.strip() or None

        return sso_info

    def authenticate_sso(self, sso_info: SSOUserInfo) -> User:
        """ตรวจสอบโดเมนมหาวิทยาลัย ค้นหาผู้ใช้ในระบบ (หรือสร้างใหม่อัตโนมัติเมื่อล็อกอินครั้งแรก)"""
        email = self.validate_university_email(sso_info.email)
        user = self.user_repo.find_by_email(email)
        if user is not None:
            return user

        local_part = email.split("@", 1)[0]
        display_name = (sso_info.name or "").strip() or local_part

        student_id = (sso_info.student_id or "").strip() or None
        if student_id is None and local_part.isdigit():
            student_id = local_part
        if student_id and self.user_repo.find_by_login(student_id) is not None:
            student_id = None

        new_user = User(
            email=email,
            name=display_name,
            student_id=student_id,
            password_hash=None,
            role=UserRole.STUDENT,
        )
        self.user_repo.save(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        return new_user

    def authenticate(self, username: str, password: str) -> User:
        user = self.user_repo.find_by_login(username)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("student id / email หรือรหัสผ่านไม่ถูกต้อง")
        return user

    def create_access_token(self, user: User) -> str:
        """
        สร้าง JWT Access Token ที่มี Role (student, instructor, admin) และข้อมูลพื้นฐานของผู้ใช้
        โดยไม่ใส่ความลับเชิงลึก (เช่น password_hash หรือ API Key) ลงใน Payload
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        role_value = (
            user.role.value if isinstance(user.role, UserRole) else str(user.role)
        )
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "student_id": user.student_id,
            "role": role_value,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def create_refresh_token(self, user: User) -> str:
        """
        สร้าง JWT Refresh Token ที่มีอายุยาวกว่า สำหรับใช้ต่ออายุ access token
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "sub": str(user.id),
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def create_token_pair(self, user: User) -> tuple[str, str]:
        """สร้างคู่ (access_token, refresh_token)"""
        return self.create_access_token(user), self.create_refresh_token(user)

    def refresh_tokens(self, refresh_token: str) -> tuple[User, str, str]:
        """ตรวจสอบ refresh_token และออก token คู่ใหม่"""
        payload = self.decode_refresh_token(refresh_token)
        user_id = UUID(payload["sub"])
        user = self.user_repo.find_by_id(user_id)
        if user is None:
            raise InvalidTokenError("ไม่พบผู้ใช้ของ refresh token นี้")
        new_access_token, new_refresh_token = self.create_token_pair(user)
        return user, new_access_token, new_refresh_token

    def decode_access_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            token_type = payload.get("type", "access")
            if token_type != "access":
                raise InvalidTokenError("token ไม่ใช่ access token")
            UUID(payload["sub"])
            return payload
        except (JWTError, KeyError, ValueError, TypeError) as e:
            raise InvalidTokenError("token ไม่ถูกต้องหรือหมดอายุแล้ว") from e

    def decode_refresh_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            token_type = payload.get("type")
            if token_type != "refresh":
                raise InvalidTokenError("token ไม่ใช่ refresh token")
            UUID(payload["sub"])
            return payload
        except (JWTError, KeyError, ValueError, TypeError) as e:
            raise InvalidTokenError("refresh token ไม่ถูกต้องหรือหมดอายุแล้ว") from e

    def get_user_from_token(self, token: str) -> User:
        payload = self.decode_access_token(token)
        user_id = UUID(payload["sub"])

        user = self.user_repo.find_by_id(user_id)
        if user is None:
            raise InvalidTokenError("ไม่พบผู้ใช้ของ token นี้")
        return user

    @staticmethod
    def set_auth_cookies(
        response,
        access_token: str,
        refresh_token: str | None = None,
    ) -> None:
        """ตั้งค่า HTTP-Only, Secure, และ SameSite Cookie บน Response"""
        access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        response.set_cookie(
            key=settings.ACCESS_TOKEN_COOKIE_NAME,
            value=access_token,
            max_age=access_max_age,
            expires=access_max_age,
            httponly=True,
            secure=settings.AUTH_COOKIE_SECURE,
            samesite=settings.AUTH_COOKIE_SAMESITE,
            domain=settings.AUTH_COOKIE_DOMAIN,
            path="/",
        )
        if refresh_token:
            refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
            response.set_cookie(
                key=settings.REFRESH_TOKEN_COOKIE_NAME,
                value=refresh_token,
                max_age=refresh_max_age,
                expires=refresh_max_age,
                httponly=True,
                secure=settings.AUTH_COOKIE_SECURE,
                samesite=settings.AUTH_COOKIE_SAMESITE,
                domain=settings.AUTH_COOKIE_DOMAIN,
                path="/",
            )

    @staticmethod
    def clear_auth_cookies(response) -> None:
        """ลบ Authentication cookies ออกจาก Response"""
        response.delete_cookie(
            key=settings.ACCESS_TOKEN_COOKIE_NAME,
            path="/",
            domain=settings.AUTH_COOKIE_DOMAIN,
            httponly=True,
            secure=settings.AUTH_COOKIE_SECURE,
            samesite=settings.AUTH_COOKIE_SAMESITE,
        )
        response.delete_cookie(
            key=settings.REFRESH_TOKEN_COOKIE_NAME,
            path="/",
            domain=settings.AUTH_COOKIE_DOMAIN,
            httponly=True,
            secure=settings.AUTH_COOKIE_SECURE,
            samesite=settings.AUTH_COOKIE_SAMESITE,
        )
