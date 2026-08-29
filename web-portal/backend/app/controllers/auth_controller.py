from app.models.user import User
from app.schemas.auth_schema import LoginRequest, MeResponse, TokenResponse
from app.services.auth_service import AuthService


class AuthController:
    def __init__(self, service: AuthService):
        self.service = service

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.service.authenticate(payload.username, payload.password)
        return TokenResponse(access_token=self.service.create_access_token(user))

    def me(self, user: User) -> MeResponse:
        return MeResponse.model_validate(user)
