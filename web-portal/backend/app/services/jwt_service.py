from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.configs.settings import settings
from app.exceptions.domain import InvalidTokenError
from app.models.rbac import Role, UserRoleAssignment
from app.models.user import User
from app.schemas.rbac_schema import JWTClaims


class JWTService:
    def __init__(self, db: Session):
        self.db = db

    def create_access_token(self, user: User) -> str:
        role_names = [
            role_name
            for (role_name,) in (
                self.db.query(Role.role_name)
                .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
                .filter(
                    UserRoleAssignment.user_id == user.id,
                    UserRoleAssignment.deleted_at.is_(None),
                    Role.is_active.is_(True),
                    Role.deleted_at.is_(None),
                )
                .order_by(Role.role_name)
                .all()
            )
        ]
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        payload = {
            "user_id": str(user.id),
            "roles": role_names,
            "exp": expires_at,
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def decode_access_token(self, token: str) -> JWTClaims:
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            claims = JWTClaims.model_validate(payload)
            subject = claims.user_id or claims.sub
            if subject is None:
                raise ValueError("Token has no user identifier")
            UUID(subject)
            return claims
        except (JWTError, PydanticValidationError, ValueError, TypeError) as error:
            raise InvalidTokenError("token ไม่ถูกต้องหรือหมดอายุแล้ว") from error