from uuid import UUID
from typing import Optional
from datetime import datetime

from app.models.session import SessionStatus
from app.schemas.session_schema import (
    CreateSessionResponse,
    SessionDetailResponse,
    SessionResponse,
)
from app.services.session_service import SessionService


class SessionController:
    """Controller สำหรับจัดการ Session API"""

    def __init__(self, service: SessionService):
        self.service = service

    def get_all_sessions(
        self, user_id: Optional[UUID] = None, status: Optional[SessionStatus] = None
    ) -> list[SessionResponse]:
        """ดึง sessions ทั้งหมด"""
        sessions = self.service.get_all_sessions(user_id=user_id, status=status)
        return [SessionResponse.model_validate(session) for session in sessions]

    def get_session(self, session_id: UUID) -> SessionDetailResponse:
        """ดึง session ตาม ID"""
        session = self.service.get_session_by_id(session_id)
        return SessionDetailResponse.model_validate(session)

    def create_session(self, user_id: UUID, lab_id: UUID) -> CreateSessionResponse:
        """สร้าง session ใหม่ - return session info with endpoints"""
        result = self.service.create_session(user_id, lab_id)
        return CreateSessionResponse(**result)

    def delete_session(self, session_id: UUID) -> dict:
        """ลบ session - stop cluster และ soft delete"""
        return self.service.delete_session(session_id)
