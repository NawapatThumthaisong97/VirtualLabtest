"""
Billing Routes
API Endpoints สำหรับการสรุปยอดค่าใช้จ่าย (Billing Aggregation) และส่งออกรายงาน (Export CSV/PDF)
จำกัดสิทธิ์เฉพาะ Role Admin ผ่าน RBAC Middleware และใช้กลไก Soft-Delete
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.controllers.billing_controller import BillingController
from app.middlewares.auth import get_current_user
from app.middlewares.rbac import verify_permission
from app.models.user import User
from app.schemas.billing_schema import (
    BillingReportListResponse,
    BillingSummaryResponse,
)
from app.schemas.response import ApiResponse
from app.services.billing_service import BillingService

router = APIRouter(
    dependencies=[Depends(verify_permission("billing:read:global"))]
)


def get_billing_controller(db: Session = Depends(get_db)) -> BillingController:
    """Dependency provider สำหรับ BillingController"""
    service = BillingService(db=db)
    return BillingController(service)


# ---------- Billing Aggregation Summary Endpoints ----------

@router.get(
    "/billing/summary",
    response_model=ApiResponse[BillingSummaryResponse],
    summary="Get Aggregated Billing Summary",
    description="ดึงและคำนวณยอดรวมค่าใช้จ่ายจากตาราง usage_records โดยจัดกลุ่มตามรายวิชา (course), รูปแบบคลัสเตอร์ (cluster), หรือรหัสแฝง (anon_id)",
)
@router.get(
    "/v1/billing/summary",
    response_model=ApiResponse[BillingSummaryResponse],
    include_in_schema=False,
)
@router.get(
    "/billing",
    response_model=ApiResponse[BillingSummaryResponse],
    include_in_schema=False,
)
@router.get(
    "/v1/billing",
    response_model=ApiResponse[BillingSummaryResponse],
    include_in_schema=False,
)
async def get_billing_summary(
    group_by: str = Query("course", description="เกณฑ์การจัดกลุ่ม: course, cluster, หรือ anon_id"),
    start_date: Optional[datetime] = Query(None, description="เวลาเริ่มต้น (ISO Format)"),
    end_date: Optional[datetime] = Query(None, description="เวลาสิ้นสุด (ISO Format)"),
    course_id: Optional[UUID] = Query(None, description="กรองเฉพาะรายวิชา"),
    is_cloud: Optional[bool] = Query(None, description="กรองเฉพาะ Cloud (AWS) หรือ Local K3s"),
    controller: BillingController = Depends(get_billing_controller),
) -> ApiResponse[BillingSummaryResponse]:
    data = controller.get_billing_summary(
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        course_id=course_id,
        is_cloud=is_cloud,
    )
    return ApiResponse(
        success=True,
        message="Billing summary retrieved successfully",
        data=data,
    )


# ---------- Export Endpoints ----------

@router.get(
    "/billing/export",
    summary="Export Billing Report as CSV or PDF",
    description="ประมวลผลและส่งออกไฟล์รายงานค่าใช้จ่ายในรูปแบบ CSV หรือ PDF สำหรับฝ่ายบริหาร โดยบังคับใช้ Strict Anonymity (ไม่มี PII)",
)
@router.get(
    "/v1/billing/export",
    include_in_schema=False,
)
async def export_billing_report(
    format: str = Query("csv", description="รูปแบบไฟล์ที่ต้องการ: csv หรือ pdf"),
    group_by: str = Query("course", description="เกณฑ์การจัดกลุ่ม: course, cluster, หรือ anon_id"),
    start_date: Optional[datetime] = Query(None, description="เวลาเริ่มต้น (ISO Format)"),
    end_date: Optional[datetime] = Query(None, description="เวลาสิ้นสุด (ISO Format)"),
    course_id: Optional[UUID] = Query(None, description="กรองเฉพาะรายวิชา"),
    is_cloud: Optional[bool] = Query(None, description="กรองเฉพาะ Cloud (AWS) หรือ Local K3s"),
    current_user: User = Depends(get_current_user),
    controller: BillingController = Depends(get_billing_controller),
):
    file_bytes, media_type, file_name = controller.export_billing_report(
        group_by=group_by,
        export_format=format,
        start_date=start_date,
        end_date=end_date,
        course_id=course_id,
        is_cloud=is_cloud,
        current_user_id=current_user.id,
    )

    headers = {
        "Content-Disposition": f'attachment; filename="{file_name}"',
        "X-Report-Filename": file_name,
    }
    return Response(content=file_bytes, media_type=media_type, headers=headers)


# ---------- Report History & Soft-Delete Endpoints ----------

@router.get(
    "/billing/reports",
    response_model=ApiResponse[BillingReportListResponse],
    summary="List Billing Export Reports History",
    description="ดึงรายการประวัติการออกรายงานค่าใช้จ่ายที่ผ่านมา (ซ่อนรายการที่ถูก Soft-Delete แล้ว)",
)
@router.get(
    "/v1/billing/reports",
    response_model=ApiResponse[BillingReportListResponse],
    include_in_schema=False,
)
async def list_billing_reports(
    limit: int = Query(50, ge=1, le=200, description="จำนวนรายการสูงสุด"),
    offset: int = Query(0, ge=0, description="ลำดับเริ่มต้น"),
    controller: BillingController = Depends(get_billing_controller),
) -> ApiResponse[BillingReportListResponse]:
    data = controller.list_reports(
        limit=limit,
        offset=offset,
        include_deleted=False,
    )
    return ApiResponse(
        success=True,
        message="Billing reports history retrieved successfully",
        data=data,
    )


@router.delete(
    "/billing/reports/{report_id}",
    response_model=ApiResponse[dict],
    dependencies=[Depends(verify_permission("billing:manage:global"))],
    summary="Soft-Delete a Billing Report",
    description="ลบประวัติการออกรายงานด้วยกลไก Soft-Delete โดยบันทึกเวลา deleted_at แทนการลบจริง",
)
@router.delete(
    "/v1/billing/reports/{report_id}",
    response_model=ApiResponse[dict],
    dependencies=[Depends(verify_permission("billing:manage:global"))],
    include_in_schema=False,
)
async def soft_delete_billing_report(
    report_id: UUID,
    controller: BillingController = Depends(get_billing_controller),
) -> ApiResponse[dict]:
    controller.soft_delete_report(report_id)
    return ApiResponse(
        success=True,
        message="Billing report soft-deleted successfully",
        data={"reportId": str(report_id), "isDeleted": True},
    )
