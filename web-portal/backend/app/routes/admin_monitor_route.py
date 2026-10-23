"""
Admin Monitor Routes — การ์ดหน้า admin overview (docs/ADMIN_MONITOR.md)
ดูอย่างเดียว ต้องมี monitoring:read:all (admin)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.middlewares.rbac import verify_permission
from app.schemas.admin_monitor_schema import InfraMapResponse, RoomUsageResponse
from app.schemas.response import ApiResponse
from app.services.admin_monitor_service import AdminMonitorService
from app.services.kubernetes_service import get_kubernetes_service
from app.utils.logger import logger

router = APIRouter(dependencies=[Depends(verify_permission("monitoring:read:all"))])


def get_admin_monitor_service(db: Session = Depends(get_db)) -> AdminMonitorService:
    try:
        k8s = get_kubernetes_service()
    except Exception as e:
        # โหลด kubeconfig ไม่ได้ = ตอบว่า cluster down ไม่ใช่ 500
        logger.warning(f"[admin monitor] kubernetes unavailable: {e}")
        k8s = None
    return AdminMonitorService(db, k8s)


@router.get("/infra/map", response_model=ApiResponse[InfraMapResponse], response_model_by_alias=True)
def get_infra_map(service: AdminMonitorService = Depends(get_admin_monitor_service)):
    """cluster ทั้งหมด: K3s (control plane + ห้องแลปจาก label vlab/room) และ AWS"""
    return {
        "success": True,
        "message": "Infra map retrieved successfully",
        "data": service.get_infra_map(),
    }


@router.get("/rooms/usage", response_model=ApiResponse[RoomUsageResponse], response_model_by_alias=True)
def get_rooms_usage(service: AdminMonitorService = Depends(get_admin_monitor_service)):
    """แต่ละห้องใช้อยู่กี่เครื่อง โดยคาบอะไร"""
    return {
        "success": True,
        "message": "Room usage retrieved successfully",
        "data": service.get_rooms_usage(),
    }
