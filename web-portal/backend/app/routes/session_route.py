from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query, Body, Request, status as http_status
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.controllers.session_controller import SessionController
from app.middlewares.auth import get_current_user
from app.middlewares.rbac import verify_permission
from app.middlewares.request_validation import require_non_empty_body
from app.models.session import SessionStatus
from app.models.user import User
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
from app.services.rbac_service import ResourceContextPolicy

router = APIRouter()
session_context_policy = ResourceContextPolicy()


def get_controller(db: Session = Depends(get_db)) -> SessionController:
    session_repo = SessionRepository(db)
    lab_repo = LabRepository(db)
    lab_image_repo = LabImageRepository(db)
    service = SessionService(db, session_repo, lab_repo, lab_image_repo)
    return SessionController(service)


@router.get(
    "/sessions",
    response_model=ApiResponse[list[SessionResponse]],
    dependencies=[
        Depends(
            verify_permission("clusters:read:self", allow_collection=True)
        )
    ],
)
def list_sessions(
    status: Optional[SessionStatus] = Query(None),
    current_user: User = Depends(get_current_user),
    controller: SessionController = Depends(get_controller),
):
    """
    ดึง sessions ทั้งหมด
    - Results are always restricted to the authenticated user
    - Query parameter: status (optional) - filter ตาม status
    """
    return {
        "success": True,
        "message": "Sessions retrieved successfully",
        "data": controller.get_all_sessions(user_id=current_user.id, status=status),
    }


@router.get(
    "/sessions/{session_id}",
    response_model=ApiResponse[SessionDetailResponse],
    dependencies=[
        Depends(
            verify_permission(
                "clusters:read:self", context_policy=session_context_policy
            )
        )
    ],
)
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
    dependencies=[
        Depends(
            verify_permission("clusters:create:self")
        )
    ],
)
def create_session(
    request: CreateSessionRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    controller: SessionController = Depends(get_controller),
):
    """
    สร้าง session ใหม่
    - Body: { "lab_id": "UUID" }; the authenticated user's ID is used
    - Return: session information with endpoints
    - กดจากเครื่องแลปที่มี warm pod ว่าง (WARM_POD_ENABLED) ได้ pod นั้นทันที (launch_mode = warm_pod)
    """
    # user = คนที่ login (schema ไม่รับ user_id แล้ว — เดิมเรียก request.user_id ได้ AttributeError → 500 ทุกครั้ง)
    user_id = current_user.id
    # IP ของ connection จริง ไม่อ่าน X-Forwarded-For เพราะ client ใส่เองได้ (ปลอมเป็นเครื่องอื่นได้)
    client_ip = http_request.client.host if http_request.client else None

    return {
        "success": True,
        "message": "Session created successfully",
        "data": controller.create_session(user_id, request.lab_id, client_ip=client_ip),
    }


@router.delete(
    "/sessions/{session_id}",
    response_model=ApiResponse[dict],
    status_code=http_status.HTTP_200_OK,
    dependencies=[
        Depends(
            verify_permission(
                "clusters:delete:self", context_policy=session_context_policy
            )
        )
    ],
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

