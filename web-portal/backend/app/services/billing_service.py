"""
BillingService
Business logic สำหรับการคำนวณและสรุปยอดค่าใช้จ่าย (Billing Aggregation)
และบริการส่งออกรายงาน (Export CSV/PDF) โดยยึดหลัก OOP, การตั้งชื่อตัวแปร snake_case,
และบังคับใช้การลบประวัติแบบ Soft-Delete เท่านั้น
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.exceptions.domain import NotFoundError, ValidationError
from app.repositories.billing_repository import BillingRepository
from app.schemas.billing_schema import (
    BillingGroupBy,
    BillingItem,
    BillingReportListResponse,
    BillingReportResponse,
    BillingSummaryResponse,
    ExportFormat,
)
from app.services.billing_export_service import BillingExportService
from app.services.log_masker_service import LogMaskerService


class BillingService:
    """Service สำหรับจัดการระบบ Billing, Aggregation, Anonymized Export และ Audit Reports"""

    def __init__(
        self,
        db: DbSession,
        billing_repo: Optional[BillingRepository] = None,
        log_masker: Optional[LogMaskerService] = None,
        export_service: Optional[BillingExportService] = None,
    ):
        self.db = db
        self.billing_repo = billing_repo or BillingRepository(db)
        self.log_masker = log_masker or LogMaskerService()
        self.export_service = export_service or BillingExportService()

    def get_billing_summary(
        self,
        group_by: str = BillingGroupBy.COURSE.value,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
    ) -> BillingSummaryResponse:
        """
        ดึงและคำนวณยอดรวมค่าใช้จ่ายจาก usage_records โดยจัดกลุ่มตาม:
        - course: รายวิชา
        - cluster: รูปแบบ Cluster (AWS SkyPilot vs Local K3s)
        - anon_id: รหัสแฝงแบบทางเดียว (HMAC-SHA256) ของกลุ่มผู้ใช้งาน (Strict Anonymity)
        """
        clean_group_by = str(group_by).strip().lower()

        if clean_group_by == BillingGroupBy.COURSE.value:
            raw_items = self.billing_repo.aggregate_by_course(
                start_date=start_date,
                end_date=end_date,
                course_id=course_id,
                is_cloud=is_cloud,
            )
            billing_items = [BillingItem(**item) for item in raw_items]

        elif clean_group_by == BillingGroupBy.CLUSTER.value:
            raw_items = self.billing_repo.aggregate_by_cluster(
                start_date=start_date,
                end_date=end_date,
                course_id=course_id,
                is_cloud=is_cloud,
            )
            billing_items = [BillingItem(**item) for item in raw_items]

        elif clean_group_by in (BillingGroupBy.ANON_ID.value, "user", "pseudonym"):
            raw_items = self.billing_repo.aggregate_by_user(
                start_date=start_date,
                end_date=end_date,
                course_id=course_id,
                is_cloud=is_cloud,
            )
            # แปลง user_id ให้เป็น anon_id ด้วย HMAC-SHA256 โดยเด็ดขาด ห้ามแสดง user_id จริง
            billing_items = []
            for item in raw_items:
                raw_uid = item.get("raw_user_id")
                anon_id = self.log_masker.pseudonymize_user_id(raw_uid) or "anon_unknown"
                billing_items.append(
                    BillingItem(
                        group_key=anon_id,
                        group_name=f"User {anon_id}",
                        course_id=None,
                        anon_id=anon_id,
                        total_sessions=item["total_sessions"],
                        total_cpu_hours=item["total_cpu_hours"],
                        total_gpu_hours=item["total_gpu_hours"],
                        total_ram_mb_hours=item["total_ram_mb_hours"],
                        total_cost_thb=item["total_cost_thb"],
                        is_cloud=None,
                    )
                )
        else:
            raise ValidationError(f"Invalid group_by parameter: '{group_by}'. Allowed: course, cluster, anon_id")

        total_cost_thb = round(sum(item.total_cost_thb for item in billing_items), 2)
        total_sessions = sum(item.total_sessions for item in billing_items)
        total_cpu_hours = round(sum(item.total_cpu_hours for item in billing_items), 2)
        total_gpu_hours = round(sum(item.total_gpu_hours for item in billing_items), 2)
        total_ram_mb_hours = round(sum(item.total_ram_mb_hours for item in billing_items), 2)

        return BillingSummaryResponse(
            group_by=clean_group_by,
            total_cost_thb=total_cost_thb,
            total_sessions=total_sessions,
            total_cpu_hours=total_cpu_hours,
            total_gpu_hours=total_gpu_hours,
            total_ram_mb_hours=total_ram_mb_hours,
            items=billing_items,
            period_start=start_date,
            period_end=end_date,
        )

    def export_billing_report(
        self,
        group_by: str = BillingGroupBy.COURSE.value,
        export_format: str = ExportFormat.CSV.value,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
        current_user_id: Optional[UUID] = None,
    ) -> tuple[bytes, str, str]:
        """
        ประมวลผลข้อมูลและ Export รายงานค่าใช้จ่ายคืนค่าเป็น binary bytes
        คืนค่า (file_bytes, media_type, file_name)
        พร้อมบันทึกประวัติรายงานลงฐานข้อมูล
        """
        format_clean = str(export_format).strip().lower()
        if format_clean not in (ExportFormat.CSV.value, ExportFormat.PDF.value):
            raise ValidationError(f"Unsupported export format '{export_format}'. Allowed: csv, pdf")

        summary = self.get_billing_summary(
            group_by=group_by,
            start_date=start_date,
            end_date=end_date,
            course_id=course_id,
            is_cloud=is_cloud,
        )

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_title = f"Billing Aggregation Report ({group_by.upper()})"

        if format_clean == ExportFormat.CSV.value:
            file_bytes = self.export_service.generate_csv(
                title=report_title,
                group_by=group_by,
                items=summary.items,
                total_cost_thb=summary.total_cost_thb,
            )
            media_type = "text/csv; charset=utf-8"
            file_name = f"billing_report_{group_by}_{timestamp_str}.csv"
        else:
            file_bytes = self.export_service.generate_pdf(
                title=report_title,
                group_by=group_by,
                items=summary.items,
                total_cost_thb=summary.total_cost_thb,
            )
            media_type = "application/pdf"
            file_name = f"billing_report_{group_by}_{timestamp_str}.pdf"

        # บันทึกประวัติการส่งออก (Audit Trail)
        if current_user_id:
            self.billing_repo.create_report_record(
                title=report_title,
                group_by=group_by,
                export_format=format_clean,
                file_name=file_name,
                total_cost_thb=summary.total_cost_thb,
                total_records=len(summary.items),
                created_by=current_user_id,
            )

        return file_bytes, media_type, file_name

    def list_reports(
        self,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> BillingReportListResponse:
        """ดึงรายการประวัติการออกรายงาน (ไม่รวมรายการที่ถูก soft-delete)"""
        records, total = self.billing_repo.list_reports(
            limit=limit,
            offset=offset,
            include_deleted=include_deleted,
        )

        report_dtos = [
            BillingReportResponse(
                id=str(r.id),
                title=r.title,
                group_by=r.group_by,
                export_format=r.export_format,
                file_name=r.file_name,
                total_cost_thb=float(r.total_cost_thb),
                total_records=r.total_records,
                created_at=r.created_at,
                created_by=str(r.created_by),
                is_deleted=r.is_deleted,
            )
            for r in records
        ]
        return BillingReportListResponse(reports=report_dtos, total=total)

    def soft_delete_report(self, report_id: UUID) -> bool:
        """
        ลบข้อมูลประวัติการออกรายงานด้วยกลไก Soft-Delete
        """
        is_success = self.billing_repo.soft_delete_report(report_id)
        if not is_success:
            raise NotFoundError(f"Billing report with id {report_id} not found")
        return True
