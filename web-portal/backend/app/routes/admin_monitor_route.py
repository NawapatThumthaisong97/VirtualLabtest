"""
Admin Monitor Routes — การ์ดหน้า admin overview (docs/ADMIN_MONITOR.md)
ดูอย่างเดียว ต้องมี monitoring:read:all (admin)
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.middlewares.auth import get_current_user
from app.middlewares.rbac import verify_permission
from app.models.user import User
from app.schemas.admin_monitor_schema import (
    BillingMonthlyResponse,
    BillingSummaryResponse,
    CloudControlResponse,
    CloudControlUpdate,
    InfraMapResponse,
    LogHistogramResponse,
    LogListResponse,
    RoomUsageResponse,
    SystemStatusResponse,
)
from app.schemas.response import ApiResponse
from app.services import admin_billing_service, admin_log_service
from app.services.admin_monitor_service import AdminMonitorService
from app.services.health_service import get_system_status
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


@router.get("/system/status", response_model=ApiResponse[SystemStatusResponse], response_model_by_alias=True)
def get_status(db: Session = Depends(get_db)):
    """สถานะ backend / k8s / registry / SkyPilot / AWS: ผลล่าสุด + แถบ 24 ชั่วโมง (จาก job ตรวจทุก 5 นาที)"""
    return {
        "success": True,
        "message": "System status retrieved successfully",
        "data": get_system_status(db),
    }


@router.get("/billing/summary", response_model=ApiResponse[BillingSummaryResponse], response_model_by_alias=True)
def get_billing_summary(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM (ไม่ใส่ = เดือนนี้ เวลาไทย)"),
    db: Session = Depends(get_db),
):
    """AWS ใช้ไปกี่ $ เทียบ budget + คาดทั้งเดือน, ชั่วโมง on-prem / AWS และสัดส่วน"""
    first = date(int(month[:4]), int(month[5:]), 1) if month else None
    return {
        "success": True,
        "message": "Billing summary retrieved successfully",
        "data": admin_billing_service.get_billing_summary(db, first),
    }


@router.get("/billing/monthly", response_model=ApiResponse[BillingMonthlyResponse], response_model_by_alias=True)
def get_billing_monthly(months: int = Query(6, ge=1, le=24), db: Session = Depends(get_db)):
    """ชั่วโมง on-prem / AWS + $ AWS รายเดือน ย้อนหลัง months เดือน (เก่า → ใหม่)"""
    return {
        "success": True,
        "message": "Monthly billing retrieved successfully",
        "data": admin_billing_service.get_billing_monthly(db, months),
    }


@router.get("/cloud/controls", response_model=ApiResponse[CloudControlResponse], response_model_by_alias=True)
def get_cloud_controls(db: Session = Depends(get_db)):
    """สวิตช์ burst ขึ้น AWS ตอนนี้เปิดหรือปิด"""
    return {
        "success": True,
        "message": "Cloud controls retrieved successfully",
        "data": admin_billing_service.get_cloud_control(db),
    }


@router.patch(
    "/cloud/controls",
    response_model=ApiResponse[CloudControlResponse],
    response_model_by_alias=True,
    dependencies=[Depends(verify_permission("monitoring:write:all"))],
)
def update_cloud_controls(
    body: CloudControlUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """เปิด / ปิด burst ขึ้น AWS — ปิดแล้วกด Start จากนอกห้องแลปได้ 409 (เครื่องแลปใช้ K3s ได้ตามปกติ)"""
    return {
        "success": True,
        "message": "Cloud controls updated successfully",
        "data": admin_billing_service.set_burst(db, body.burst_enabled, body.reason, current_user.id),
    }


@router.get("/logs", response_model=ApiResponse[LogListResponse], response_model_by_alias=True)
def get_logs(
    category: Optional[str] = Query(None, pattern="^(CLUSTER|CLOUD|cluster|cloud)$", description="CLUSTER / CLOUD"),
    type: Optional[str] = Query(None, description="event type เช่น POD_EVENT"),
    severity: Optional[str] = Query(None, description="INFO / WARNING / ERROR / CRITICAL"),
    start: Optional[datetime] = Query(None, alias="from"),
    end: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """log การใช้งาน / ปัญหาของ cluster และ cloud ใหม่สุดก่อน (user เป็น anonId)"""
    return {
        "success": True,
        "message": "Logs retrieved successfully",
        "data": admin_log_service.list_logs(db, category, type, severity, start, end, limit, offset),
    }


@router.get("/logs/histogram", response_model=ApiResponse[LogHistogramResponse], response_model_by_alias=True)
def get_logs_histogram(
    category: Optional[str] = Query(None, pattern="^(CLUSTER|CLOUD|cluster|cloud)$"),
    hours: int = Query(72, ge=2, le=24 * 30),
    bucket_hours: int = Query(2, ge=1, le=24, alias="bucketHours"),
    db: Session = Depends(get_db),
):
    """จำนวน log ต่อช่วงเวลา (กราฟแท่ง Log Explorer) + แยกตามประเภท"""
    return {
        "success": True,
        "message": "Log histogram retrieved successfully",
        "data": admin_log_service.histogram(db, category, hours, bucket_hours),
    }
