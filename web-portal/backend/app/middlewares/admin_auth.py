from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.configs.db import SessionLocal
from app.exceptions.domain import DomainError
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

SESSION_KEY = "admin_user_id"

# 🚨 DEV MODE: ปิดการ login ชั่วคราว
# ตั้งค่านี้เป็น True เพื่อข้าม authentication (ใช้เฉพาะ development!)
SKIP_AUTH_FOR_DEV = True  # ⚠️ เปลี่ยนเป็น False ก่อน deploy production!


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        # 🚨 DEV MODE: ข้าม login
        if SKIP_AUTH_FOR_DEV:
            # ใช้ admin user ID ปลอม (หรือ query จาก DB)
            request.session[SESSION_KEY] = "00000000-0000-0000-0000-000000000000"
            return True
        
        # ===== ส่วน Login ปกติ (ใช้ตอน production) =====
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
        # 🚨 DEV MODE: ข้ามการตรวจสอบ session
        if SKIP_AUTH_FOR_DEV:
            return True
        
        # ===== ส่วน Authentication ปกติ (ใช้ตอน production) =====
        return SESSION_KEY in request.session
