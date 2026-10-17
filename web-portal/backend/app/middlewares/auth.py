from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.exceptions.domain import InvalidTokenError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Get current user (required auth)
    
    Raises:
        InvalidTokenError: ถ้าไม่มี token หรือ token ไม่ถูกต้อง
    """
    if credentials is None:
        raise InvalidTokenError("ต้องแนบ Authorization: Bearer <token>")
    service = AuthService(db, UserRepository(db))
    return service.get_user_from_token(credentials.credentials)


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Get current user (optional auth)
    
    Returns None ถ้าไม่มี token แทนที่จะ raise error
    ใช้สำหรับ endpoint ที่ไม่บังคับให้ login แต่ถ้า login แล้วจะได้ข้อมูลเพิ่ม
    """
    if credentials is None:
        return None
    try:
        service = AuthService(db, UserRepository(db))
        return service.get_user_from_token(credentials.credentials)
    except Exception:
        # Token ไม่ถูกต้อง ก็ถือว่าไม่มี user
        return None
