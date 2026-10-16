from fastapi import Response

from app.models.user import User
from app.schemas.auth_schema import (
    AuthTokens,
    LoginRequest,
    LogoutResponse,
    MeResponse,
    RefreshTokenRequest,
    SSOAuthorizeResponse,
    SSOLoginRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService


class AuthController:
    def __init__(self, service: AuthService):
        self.service = service

    def login(
        self, payload: LoginRequest, response: Response | None = None
    ) -> TokenResponse:
        user = self.service.authenticate(payload.username, payload.password)
        access_token, refresh_token = self.service.create_token_pair(user)
        if response:
            self.service.set_auth_cookies(
                response, access_token=access_token, refresh_token=refresh_token
            )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def sso_authorize_url(
        self,
        state: str | None = None,
        redirect_uri: str | None = None,
    ) -> SSOAuthorizeResponse:
        url = self.service.get_sso_authorize_url(
            state=state,
            redirect_uri=redirect_uri,
        )
        return SSOAuthorizeResponse(authorization_url=url)

    def sso_login(
        self,
        payload: SSOLoginRequest,
        forwarded_email: str | None = None,
        forwarded_name: str | None = None,
        response: Response | None = None,
    ) -> TokenResponse:
        sso_info = self.service.resolve_sso_user_info(
            payload,
            forwarded_email=forwarded_email,
            forwarded_name=forwarded_name,
        )
        user = self.service.authenticate_sso(sso_info)
        access_token, refresh_token = self.service.create_token_pair(user)
        if response:
            self.service.set_auth_cookies(
                response, access_token=access_token, refresh_token=refresh_token
            )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def refresh(
        self,
        refresh_token: str,
        response: Response | None = None,
    ) -> TokenResponse:
        _user, new_access_token, new_refresh_token = self.service.refresh_tokens(
            refresh_token
        )
        if response:
            self.service.set_auth_cookies(
                response,
                access_token=new_access_token,
                refresh_token=new_refresh_token,
            )
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
        )

    def logout(self, response: Response) -> LogoutResponse:
        self.service.clear_auth_cookies(response)
        return LogoutResponse(logged_out=True)

    def me(self, user: User) -> MeResponse:
        return MeResponse.model_validate(user)
