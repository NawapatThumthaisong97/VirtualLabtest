import ipaddress
from uuid import UUID

from sqlalchemy.orm import Session
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.configs.db import SessionLocal
from app.configs.settings import settings
from app.exceptions.domain import DomainError
from app.models.rbac import Role, UserRoleAssignment
from app.models.user import User, UserRole
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
            if (
                user.role != UserRole.ADMIN
                or self._active_admin_email(db, user.id) is None
                or not self._has_trusted_tailscale_identity(request, user.email)
            ):
                return False
        except DomainError:
            return False
        except Exception:
            return False
        finally:
            db.close()

        request.session[SESSION_KEY] = str(user.id)
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        user_id = request.session.get(SESSION_KEY)
        if not user_id:
            return False

        try:
            parsed_user_id = UUID(user_id)
        except (TypeError, ValueError):
            request.session.clear()
            return False

        db = SessionLocal()
        try:
            admin_email = self._active_admin_email(db, parsed_user_id)
            is_admin = admin_email is not None and self._has_trusted_tailscale_identity(
                request, admin_email
            )
        except Exception:
            request.session.clear()
            return False
        finally:
            db.close()

        if not is_admin:
            request.session.clear()
        return is_admin

    @staticmethod
    def _active_admin_email(db: Session, user_id: UUID) -> str | None:
        return (
            db.query(User.email)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .filter(
                User.id == user_id,
                UserRoleAssignment.deleted_at.is_(None),
                Role.role_name == "Admin",
                Role.is_active.is_(True),
                Role.deleted_at.is_(None),
            )
            .scalar()
        )

    @staticmethod
    def _has_trusted_tailscale_identity(request: Request, expected_email: str) -> bool:
        if request.client is None or not settings.tailscale_trusted_proxy_cidrs:
            return False
        try:
            peer_ip = ipaddress.ip_address(request.client.host)
            trusted_proxy_cidrs = [
                ipaddress.ip_network(cidr, strict=False)
                for cidr in settings.tailscale_trusted_proxy_cidrs
            ]
        except ValueError:
            return False

        if not any(peer_ip in trusted_cidr for trusted_cidr in trusted_proxy_cidrs):
            return False
        tailscale_login = request.headers.get("Tailscale-User-Login", "").strip()
        return tailscale_login.casefold() == expected_email.casefold()
