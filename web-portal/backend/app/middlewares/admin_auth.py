from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.configs.db import SessionLocal
from app.exceptions.domain import DomainError
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

SESSION_KEY = "admin_user_id"


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))

        db = SessionLocal()
        try:
            user = AuthService(db, UserRepository(db)).authenticate(username, password)
        except DomainError:
            return False
        finally:
            db.close()

        if user.role != UserRole.ADMIN:
            return False

        request.session[SESSION_KEY] = str(user.id)
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return SESSION_KEY in request.session
