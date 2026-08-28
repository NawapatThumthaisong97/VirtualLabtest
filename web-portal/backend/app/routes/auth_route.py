from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.controllers.auth_controller import AuthController
from app.middlewares.auth import get_current_user
from app.middlewares.request_validation import require_non_empty_body
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth_schema import LoginRequest, MeResponse, TokenResponse
from app.schemas.response import ApiResponse
from app.services.auth_service import AuthService

router = APIRouter()


def get_controller(db: Session = Depends(get_db)) -> AuthController:
    return AuthController(AuthService(db, UserRepository(db)))


@router.post(
    "/auth/login",
    response_model=ApiResponse[TokenResponse],
    dependencies=[Depends(require_non_empty_body)],
)
def login(payload: LoginRequest, controller: AuthController = Depends(get_controller)):
    return {
        "success": True,
        "message": "Login successful",
        "data": controller.login(payload),
    }


@router.get("/me", response_model=ApiResponse[MeResponse])
def me(
    current_user: User = Depends(get_current_user),
    controller: AuthController = Depends(get_controller),
):
    return {
        "success": True,
        "message": "Current user retrieved successfully",
        "data": controller.me(current_user),
    }
