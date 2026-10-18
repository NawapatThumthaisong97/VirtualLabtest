"""
Monitor Routes
API Endpoints สำหรับ Cluster Metrics, Critical Logs และ Security Violation Counters
จำกัดสิทธิ์เฉพาะ Role Admin ผ่าน RBAC Middleware และทำงานแบบ Read-Only เท่านั้น
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status as http_status
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.controllers.monitor_controller import MonitorController
from app.middlewares.rbac import verify_permission
from app.schemas.monitor_schema import (
    ClusterMetricsResponse,
    CreateInfrastructureLogRequest,
    InfrastructureLogItem,
    LogListResponse,
    SecurityCountersResponse,
)
from app.schemas.response import ApiResponse
from app.services.kubernetes_service import get_kubernetes_service
from app.services.log_masker_service import LogMaskerService
from app.services.monitor_service import MonitorService

router = APIRouter(
    dependencies=[Depends(verify_permission("monitoring:read:all"))]
)


def get_monitor_controller(db: Session = Depends(get_db)) -> MonitorController:
    """Dependency provider สำหรับ MonitorController"""
    k8s_svc = None
    try:
        k8s_svc = get_kubernetes_service()
    except Exception:
        pass
    service = MonitorService(
        db=db,
        log_masker=LogMaskerService(),
        k8s_service=k8s_svc,
    )
    return MonitorController(service)


# ---------- Metrics Endpoints ----------

@router.get(
    "/metrics",
    response_model=ApiResponse[ClusterMetricsResponse],
    summary="Get Cluster Resource Allocation Metrics & Summary",
    description="ดึงข้อมูลภาพรวมสถานะทรัพยากร (CPU, RAM, Active Sessions) และสถิติความปลอดภัยเบื้องต้น รองรับการ Filter/Group ระหว่าง AWS SkyPilot และ Local K3s แยกตามวง NAT",
)
@router.get(
    "/v1/metrics",
    response_model=ApiResponse[ClusterMetricsResponse],
    include_in_schema=False,
)
async def get_cluster_metrics(
    provider: Optional[str] = Query(None, description="กรองตาม provider เช่น aws หรือ local_k3s"),
    nat_subnet: Optional[str] = Query(None, description="กรองตามวง NAT เช่น 192.168.1.0/24"),
    group_by: Optional[str] = Query(None, description="จัดกลุ่ม เช่น provider หรือ nat_subnet"),
    controller: MonitorController = Depends(get_monitor_controller),
) -> ApiResponse[ClusterMetricsResponse]:
    data = controller.get_cluster_metrics(
        provider=provider,
        nat_subnet=nat_subnet,
        group_by=group_by,
    )
    return ApiResponse(
        success=True,
        message="Cluster metrics retrieved successfully",
        data=data,
    )


@router.get(
    "/metrics/security-counters",
    response_model=ApiResponse[SecurityCountersResponse],
    summary="Get Security Violation Counters",
    description="ดึงสถิติตัวนับการละเมิดความปลอดภัย: Squid Proxy Egress Drops, OPA/Kyverno Policy Blocks, และ Tailscale Cross-Cluster Attempts",
)
@router.get(
    "/v1/metrics/security-counters",
    response_model=ApiResponse[SecurityCountersResponse],
    include_in_schema=False,
)
@router.get(
    "/security/counters",
    response_model=ApiResponse[SecurityCountersResponse],
    include_in_schema=False,
)
async def get_security_counters(
    controller: MonitorController = Depends(get_monitor_controller),
) -> ApiResponse[SecurityCountersResponse]:
    data = controller.get_security_counters()
    return ApiResponse(
        success=True,
        message="Security violation counters retrieved successfully",
        data=data,
    )


# ---------- Logs Endpoints ----------

@router.get(
    "/logs",
    response_model=ApiResponse[LogListResponse],
    summary="Get Critical Infrastructure and Security Boundary Logs",
    description="ดึง Critical Error Logs (Node Down, SkyPilot Burst Failed, OOM) และ Security Violation Logs โดยผ่านการ Mask PII, ตัด Source Code ใน Pod และแปลง user_id เป็นรหัสแฝงแบบทางเดียว (anon_id) ในรูปแบบ CamelCase เสมอ",
)
@router.get(
    "/v1/logs",
    response_model=ApiResponse[LogListResponse],
    include_in_schema=False,
)
async def get_critical_logs(
    severity: Optional[str] = Query(None, description="กรองตามความรุนแรง เช่น CRITICAL, ERROR, WARNING, INFO"),
    category: Optional[str] = Query(None, description="กรองตามหมวดหมู่ เช่น INFRASTRUCTURE, SECURITY_VIOLATION, BURST, CONTAINER"),
    event_type: Optional[str] = Query(None, description="กรองตามประเภทเหตุการณ์ เช่น NODE_DOWN, SKY_BURST_FAILED, OOM_KILLED"),
    limit: int = Query(50, ge=1, le=200, description="จำนวนรายการสูงสุด"),
    offset: int = Query(0, ge=0, description="ลำดับเริ่มต้น"),
    controller: MonitorController = Depends(get_monitor_controller),
) -> ApiResponse[LogListResponse]:
    data = controller.get_critical_logs(
        severity=severity,
        category=category,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(
        success=True,
        message="Infrastructure and security logs retrieved successfully",
        data=data,
    )


@router.post(
    "/logs",
    response_model=ApiResponse[InfrastructureLogItem],
    status_code=http_status.HTTP_201_CREATED,
    summary="Ingest Infrastructure or Security Log from Collector",
    description="รับข้อมูล Log โครงสร้างพื้นฐาน หรือ Security Boundary Violation จาก Collector โดยระบบจะทำ Data Masking, ตัด Source Code ใน Pod และแปลง user_id เป็น anon_id ก่อนบันทึกลงฐานข้อมูล",
)
@router.post(
    "/v1/logs",
    response_model=ApiResponse[InfrastructureLogItem],
    status_code=http_status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def ingest_log(
    body: CreateInfrastructureLogRequest,
    controller: MonitorController = Depends(get_monitor_controller),
) -> ApiResponse[InfrastructureLogItem]:
    data = controller.create_log(body)
    return ApiResponse(
        success=True,
        message="Log ingested and masked successfully",
        data=data,
    )

