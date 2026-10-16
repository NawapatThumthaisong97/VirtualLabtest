from app.models.user import User
from app.schemas.auth_schema import (
    LoginRequest,
    MeResponse,
    SSOAuthorizeResponse,
    SSOLoginRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService


class AuthController:
    def __init__(self, service: AuthService):
        self.service = service

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.service.authenticate(payload.username, payload.password)
        return TokenResponse(access_token=self.service.create_access_token(user))

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
    ) -> TokenResponse:
        sso_info = self.service.resolve_sso_user_info(
            payload,
            forwarded_email=forwarded_email,
            forwarded_name=forwarded_name,
        )
        user = self.service.authenticate_sso(sso_info)
        return TokenResponse(access_token=self.service.create_access_token(user))

    def me(self, user: User) -> MeResponse:
        return MeResponse.model_validate(user)
