from fastapi import APIRouter, Depends

from app.schemas.prewarm_schema import PrewarmResponse, WarmPodResponse
from app.schemas.response import ApiResponse
from app.services.kubernetes_service import get_kubernetes_service
from app.services.prewarm_service import PrewarmService
from app.services.warm_pod_service import WarmPodService

router = APIRouter()


def get_prewarm_service() -> PrewarmService:
    return PrewarmService(get_kubernetes_service())


@router.get("/prewarm", response_model=ApiResponse[list[PrewarmResponse]])
def list_prewarm(service: PrewarmService = Depends(get_prewarm_service)):
    """
    DaemonSet pre-pull ทั้งหมดที่ scheduler สร้างไว้ พร้อมสถานะราย worker
    - ดูอย่างเดียว การสร้าง / ลบเป็นหน้าที่ของ prewarm scheduler
    """
    return {
        "success": True,
        "message": "Prewarm status retrieved successfully",
        "data": service.status(),
    }


@router.get("/warm-pods", response_model=ApiResponse[list[WarmPodResponse]])
def list_warm_pods():
    """warm pod ทุกตัว: เครื่องไหน lab image ไหน ว่าง (free) หรือแจกให้ session แล้ว (claimed)"""
    return {
        "success": True,
        "message": "Warm pods retrieved successfully",
        "data": WarmPodService(get_kubernetes_service()).list_pods(),
    }


@router.get("/prewarm/{name}", response_model=ApiResponse[PrewarmResponse])
def get_prewarm(name: str, service: PrewarmService = Depends(get_prewarm_service)):
    """DaemonSet pre-pull ตัวเดียวตามชื่อ (404 ถ้าไม่มี)"""
    return {
        "success": True,
        "message": "Prewarm status retrieved successfully",
        "data": service.status(name)[0],
    }
