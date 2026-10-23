from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.schemas.prewarm_schema import PrewarmResponse, PrewarmScheduleResponse, WarmPodResponse
from app.schemas.response import ApiResponse
from app.services.kubernetes_service import get_kubernetes_service
from app.services.prewarm_scheduler import build_schedule
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


# ต้องประกาศก่อน /prewarm/{name} ไม่งั้น "schedule" ถูกจับเป็นชื่อ DaemonSet
@router.get("/prewarm/schedule", response_model=ApiResponse[PrewarmScheduleResponse])
def get_prewarm_schedule(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """
    scheduler จะทำงานเมื่อไหร่: ค่าตั้ง (เปิดไหม / ทุกกี่วินาที / เริ่มก่อนคาบกี่นาที) + คาบที่ยังไม่จบ
    พร้อมเวลาเริ่ม pre-pull (prewarm_at) และ PREWARM_TARGETS จาก .env — ดูอย่างเดียว
    """
    return {
        "success": True,
        "message": "Prewarm schedule retrieved successfully",
        "data": build_schedule(db, datetime.now(timezone.utc), limit),
    }


@router.get("/prewarm/{name}", response_model=ApiResponse[PrewarmResponse])
def get_prewarm(name: str, service: PrewarmService = Depends(get_prewarm_service)):
    """DaemonSet pre-pull ตัวเดียวตามชื่อ (404 ถ้าไม่มี)"""
    return {
        "success": True,
        "message": "Prewarm status retrieved successfully",
        "data": service.status(name)[0],
    }
