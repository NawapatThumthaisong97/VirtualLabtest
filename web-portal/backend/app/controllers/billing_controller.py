"""
BillingController
Controller สำหรับระบบคำนวณค่าใช้จ่าย (Billing) และการส่งออกรายงาน (Export CSV/PDF)
ทำหน้าที่เป็นตัวกลางระหว่าง Route และ Service
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from app.schemas.billing_schema import (
    BillingReportListResponse,
    BillingSummaryResponse,
)
from app.services.billing_service import BillingService


class BillingController:
    """Controller สำหรับจัดการการร้องขอเกี่ยวกับข้อมูลสรุปค่าใช้จ่ายและการส่งออกรายงาน"""

    def __init__(self, billing_service: BillingService):
        self.billing_service = billing_service

    def get_billing_summary(
        self,
        group_by: str = "course",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
    ) -> BillingSummaryResponse:
        """ดึงและคำนวณข้อมูลสรุปยอดค่าใช้จ่ายตามเกณฑ์ที่ระบุ"""
        return self.billing_service.get_billing_summary(
            group_by=group_by,
            start_date=start_date,
            end_date=end_date,
            course_id=course_id,
            is_cloud=is_cloud,
        )

    def export_billing_report(
        self,
        group_by: str = "course",
        export_format: str = "csv",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
        current_user_id: Optional[UUID] = None,
    ) -> tuple[bytes, str, str]:
        """ประมวลผลข้อมูลและสร้างไฟล์รายงานสำหรับส่งออก คืนค่า (file_bytes, media_type, file_name)"""
        return self.billing_service.export_billing_report(
            group_by=group_by,
            export_format=export_format,
            start_date=start_date,
            end_date=end_date,
            course_id=course_id,
            is_cloud=is_cloud,
            current_user_id=current_user_id,
        )

    def list_reports(
        self,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> BillingReportListResponse:
        """ดึงรายการประวัติการออกรายงาน (Soft-Delete Aware)"""
        return self.billing_service.list_reports(
            limit=limit,
            offset=offset,
            include_deleted=include_deleted,
        )

    def soft_delete_report(self, report_id: UUID) -> bool:
        """ลบประวัติการออกรายงานด้วยกลไก Soft-Delete"""
        return self.billing_service.soft_delete_report(report_id)
