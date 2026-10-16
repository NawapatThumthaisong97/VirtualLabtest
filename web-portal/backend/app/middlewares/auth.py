from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.configs.settings import settings
from app.exceptions.domain import InvalidTokenError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token: str | None = None
    if credentials is not None:
        token = credentials.credentials
    elif settings.ACCESS_TOKEN_COOKIE_NAME in request.cookies:
        token = request.cookies[settings.ACCESS_TOKEN_COOKIE_NAME]

    if not token:
        raise InvalidTokenError("ต้องแนบ Authorization: Bearer <token> หรือ Authentication Cookie")

    service = AuthService(db, UserRepository(db))
    return service.get_user_from_token(token)
