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
    if credentials is None:
        raise InvalidTokenError("ต้องแนบ Authorization: Bearer <token>")
    service = AuthService(db, UserRepository(db))
    return service.get_user_from_token(credentials.credentials)
