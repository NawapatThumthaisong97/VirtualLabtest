from uuid import UUID
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query, Body, status as http_status
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.controllers.session_controller import SessionController
from app.middlewares.request_validation import require_non_empty_body
from app.models.session import SessionStatus
from app.repositories.session_repository import SessionRepository
from app.repositories.lab_repository import LabRepository
from app.repositories.lab_image_repository import LabImageRepository
from app.schemas.session_schema import (
    CreateSessionRequest,
    CreateSessionResponse,
    SessionDetailResponse,
    SessionResponse,
)
from app.schemas.response import ApiResponse
from app.services.session_service import SessionService

router = APIRouter()


def get_controller(db: Session = Depends(get_db)) -> SessionController:
    session_repo = SessionRepository(db)
    lab_repo = LabRepository(db)
    lab_image_repo = LabImageRepository(db)
    service = SessionService(db, session_repo, lab_repo, lab_image_repo)
    return SessionController(service)


@router.get("/sessions", response_model=ApiResponse[list[SessionResponse]])
def list_sessions(
    user_id: Optional[UUID] = Query(None, alias="userId"),
    status: Optional[SessionStatus] = Query(None),
    controller: SessionController = Depends(get_controller),
):
    """
    ดึง sessions ทั้งหมด
    - Query parameter: userId (optional) - filter ตาม user
    - Query parameter: status (optional) - filter ตาม status
    """
    return {
        "success": True,
        "message": "Sessions retrieved successfully",
        "data": controller.get_all_sessions(user_id=user_id, status=status),
    }


@router.get("/sessions/{session_id}", response_model=ApiResponse[SessionDetailResponse])
def get_session(
    session_id: UUID,
    controller: SessionController = Depends(get_controller),
):
    """ดึง session ตาม ID"""
    return {
        "success": True,
        "message": "Session retrieved successfully",
        "data": controller.get_session(session_id),
    }


@router.post(
    "/sessions",
    response_model=ApiResponse[CreateSessionResponse],
    status_code=http_status.HTTP_201_CREATED,
)
def create_session(
    request: CreateSessionRequest,
    controller: SessionController = Depends(get_controller),
):
    """
    สร้าง session ใหม่
    - Body: { "lab_id": "UUID", "user_id": "UUID (optional)" }
    - Return: session information with endpoints
    """
    # ถ้าไม่มี userId ใช้ default UUID
    user_id = request.user_id or UUID("00000000-0000-0000-0000-000000000000")
    
    return {
        "success": True,
        "message": "Session created successfully",
        "data": controller.create_session(user_id, request.lab_id),
    }


@router.delete(
    "/sessions/{session_id}",
    response_model=ApiResponse[dict],
    status_code=http_status.HTTP_200_OK
)
def delete_session(
    session_id: UUID,
    controller: SessionController = Depends(get_controller),
):
    """
    ลบ session - stop cluster (ถ้ายังรัน) และ soft delete
    - Path parameter: session_id (UUID)
    - Return: deletion status
    """
    return {
        "success": True,
        "message": "Session deleted successfully",
        "data": controller.delete_session(session_id),
    }

