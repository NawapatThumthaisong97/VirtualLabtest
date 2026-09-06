from uuid import UUID
from sqlalchemy.orm import Session, joinedload
from app.models.session import Session as SessionModel, SessionStatus
from typing import Optional


class SessionRepository:
    """Repository สำหรับจัดการ Session ในฐานข้อมูล"""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self, user_id: Optional[UUID] = None, status: Optional[SessionStatus] = None) -> list[SessionModel]:
        """ดึง sessions ทั้งหมด (filter ตาม user_id หรือ status ได้)"""
        query = self.db.query(SessionModel).filter(SessionModel.deleted_at.is_(None))
        
        if user_id:
            query = query.filter(SessionModel.user_id == user_id)
        if status:
            query = query.filter(SessionModel.status == status)
            
        return query.all()

    def get_by_id(self, session_id: UUID) -> Optional[SessionModel]:
        """ดึง session ตาม ID"""
        return (
            self.db.query(SessionModel)
            .filter(SessionModel.id == session_id, SessionModel.deleted_at.is_(None))
            .options(joinedload(SessionModel.user), joinedload(SessionModel.lab))
            .first()
        )

    def create(self, session: SessionModel) -> SessionModel:
        """สร้าง session ใหม่"""
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update(self, session: SessionModel) -> SessionModel:
        """อัพเดท session"""
        self.db.commit()
        self.db.refresh(session)
        return session

    def soft_delete(self, session: SessionModel) -> None:
        """ลบ session แบบ soft delete"""
        from datetime import datetime, timezone
        session.deleted_at = datetime.now(timezone.utc)
        self.db.commit()

    def delete(self, session: SessionModel) -> None:
        """ลบ session แบบถาวร (ไม่แนะนำ - ใช้ soft_delete แทน)"""
        self.db.delete(session)
        self.db.commit()
