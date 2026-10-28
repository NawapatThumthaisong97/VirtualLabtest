from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.middlewares.auth import get_current_user
from app.models.user import User
from app.schemas.base import CamelModel
from app.schemas.response import ApiResponse
from app.services.activity_service import ActivityService

router = APIRouter()


class ActivityResponse(CamelModel):
    """กิจกรรมหนึ่งรายการ — kind บอกว่าเป็นอะไร (frontend จัดข้อความเอง)

    session_running / session_ended / session_failed / lab_finished (นักศึกษา)
    image_passed / image_failed / lab_draft / launch_count (อาจารย์ / admin)
    """
    kind: str
    at: datetime | None
    course_code: str
    title: str
    lab_id: UUID | None = None
    course_id: UUID | None = None
    detail: dict = {}


@router.get("/v1/me/activity", response_model=ApiResponse[list[ActivityResponse]])
def my_activity(
    limit: int = Query(3, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """กิจกรรมล่าสุดของคนที่ login (กล่อง Activity Logging หน้า home) ค่าเริ่มต้น 3 รายการให้สูงเท่ากล่อง Announcement"""
    items = ActivityService(db).for_user(current_user, limit)
    return {
        "success": True,
        "message": "Activity retrieved successfully",
        "data": [ActivityResponse(**item.__dict__) for item in items],
    }
