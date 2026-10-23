from fastapi import APIRouter, Body, Cookie, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.configs.settings import settings
from app.controllers.auth_controller import AuthController
from app.exceptions.domain import InvalidTokenError
from app.middlewares.auth import get_current_user
from app.middlewares.request_validation import require_non_empty_body
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth_schema import (
    LoginRequest,
    LogoutResponse,
    MeResponse,
    RefreshTokenRequest,
    SSOAuthorizeResponse,
    SSOLoginRequest,
    TokenResponse,
)
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
def login(
    payload: LoginRequest,
    response: Response,
    controller: AuthController = Depends(get_controller),
):
    return {
        "success": True,
        "message": "Login successful",
        "data": controller.login(payload, response=response),
    }


@router.get(
    "/auth/sso/login",
    response_model=ApiResponse[SSOAuthorizeResponse],
)
def sso_authorize(
    state: str | None = Query(default=None),
    redirect_uri: str | None = Query(default=None),
    controller: AuthController = Depends(get_controller),
):
    return {
        "success": True,
        "message": "SSO authorization URL generated",
        "data": controller.sso_authorize_url(state=state, redirect_uri=redirect_uri),
    }


@router.post(
    "/auth/sso",
    response_model=ApiResponse[TokenResponse],
)
@router.post(
    "/auth/sso/callback",
    response_model=ApiResponse[TokenResponse],
)
def sso_login(
    response: Response,
    payload: SSOLoginRequest | None = Body(default=None),
    x_forwarded_email: str | None = Header(default=None, alias="X-Forwarded-Email"),
    x_auth_request_email: str | None = Header(
        default=None, alias="X-Auth-Request-Email"
    ),
    x_forwarded_user: str | None = Header(default=None, alias="X-Forwarded-User"),
    controller: AuthController = Depends(get_controller),
):
    forwarded_email = x_forwarded_email or x_auth_request_email
    data = controller.sso_login(
        payload or SSOLoginRequest(),
        forwarded_email=forwarded_email,
        forwarded_name=x_forwarded_user,
        response=response,
    )
    return {
        "success": True,
        "message": "SSO login successful",
        "data": data,
    }


@router.get(
    "/auth/sso/callback",
    response_model=ApiResponse[TokenResponse],
)
def sso_callback_get(
    response: Response,
    code: str | None = Query(default=None),
    id_token: str | None = Query(default=None),
    access_token: str | None = Query(default=None),
    redirect_uri: str | None = Query(default=None),
    x_forwarded_email: str | None = Header(default=None, alias="X-Forwarded-Email"),
    x_auth_request_email: str | None = Header(
        default=None, alias="X-Auth-Request-Email"
    ),
    x_forwarded_user: str | None = Header(default=None, alias="X-Forwarded-User"),
    controller: AuthController = Depends(get_controller),
):
    forwarded_email = x_forwarded_email or x_auth_request_email
    payload = SSOLoginRequest(
        code=code,
        id_token=id_token,
        access_token=access_token,
        redirect_uri=redirect_uri,
    )
    data = controller.sso_login(
        payload,
        forwarded_email=forwarded_email,
        forwarded_name=x_forwarded_user,
        response=response,
    )
    return {
        "success": True,
        "message": "SSO login successful",
        "data": data,
    }


@router.post(
    "/auth/refresh",
    response_model=ApiResponse[TokenResponse],
)
def refresh_token_endpoint(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = Body(default=None),
    cookie_refresh_token: str | None = Cookie(
        default=None, alias=settings.REFRESH_TOKEN_COOKIE_NAME
    ),
    controller: AuthController = Depends(get_controller),
):
    token = (payload and payload.refresh_token) or cookie_refresh_token
    if not token and settings.REFRESH_TOKEN_COOKIE_NAME in request.cookies:
        token = request.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]

    if not token:
        raise InvalidTokenError("ต้องส่ง refresh token ผ่าน Cookie หรือ Body")

    data = controller.refresh(token, response=response)
    return {
        "success": True,
        "message": "Token refreshed successfully",
        "data": data,
    }


@router.post(
    "/auth/logout",
    response_model=ApiResponse[LogoutResponse],
)
def logout(
    response: Response,
    controller: AuthController = Depends(get_controller),
):
    return {
        "success": True,
        "message": "Logged out successfully",
        "data": controller.logout(response),
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
