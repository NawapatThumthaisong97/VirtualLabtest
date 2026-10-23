"""
BillingRepository
Data access layer สำหรับการรวบรวมและคำนวณสถิติค่าใช้จ่ายจาก usage_records
และจัดการประวัติรายงานการส่งออกด้วยระบบ Soft-Delete
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DbSession
from sqlalchemy import func, desc

from app.models.billing_report import BillingReport
from app.models.courses import Course
from app.models.lab import Lab
from app.models.session import Session as SessionModel
from app.models.usage_record import UsageRecord


class BillingRepository:
    """Repository สำหรับระบบคำนวณค่าใช้จ่าย (Billing) และประวัติรายงาน"""

    def __init__(self, db: DbSession):
        self.db = db

    def _base_usage_query(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
    ):
        """สร้าง Base Query โดย Join usage_records เข้ากับ sessions, labs, และ courses"""
        query = (
            self.db.query(UsageRecord, SessionModel, Lab, Course)
            .join(SessionModel, UsageRecord.session_id == SessionModel.id)
            .outerjoin(Lab, SessionModel.lab_id == Lab.id)
            .outerjoin(Course, Lab.course_id == Course.id)
        )

        if start_date:
            query = query.filter(UsageRecord.recorded_at >= start_date)
        if end_date:
            query = query.filter(UsageRecord.recorded_at <= end_date)
        if course_id:
            query = query.filter(Lab.course_id == course_id)
        if is_cloud is not None:
            query = query.filter(SessionModel.is_cloud == is_cloud)

        return query

    def aggregate_by_course(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """
        จัดกลุ่มยอดค่าใช้จ่ายตามรายวิชา (Course)
        """
        query = (
            self.db.query(
                Course.id.label("course_id"),
                Course.code.label("course_code"),
                Course.name.label("course_name"),
                func.count(func.distinct(UsageRecord.session_id)).label("total_sessions"),
                func.coalesce(func.sum(UsageRecord.cpu_seconds), 0).label("sum_cpu_seconds"),
                func.coalesce(func.sum(UsageRecord.gpu_seconds), 0).label("sum_gpu_seconds"),
                func.coalesce(func.sum(UsageRecord.ram_mb_hours), 0).label("sum_ram_mb_hours"),
                func.coalesce(func.sum(UsageRecord.est_cost_thb), 0).label("sum_cost_thb"),
            )
            .join(SessionModel, UsageRecord.session_id == SessionModel.id)
            .outerjoin(Lab, SessionModel.lab_id == Lab.id)
            .outerjoin(Course, Lab.course_id == Course.id)
        )

        if start_date:
            query = query.filter(UsageRecord.recorded_at >= start_date)
        if end_date:
            query = query.filter(UsageRecord.recorded_at <= end_date)
        if course_id:
            query = query.filter(Lab.course_id == course_id)
        if is_cloud is not None:
            query = query.filter(SessionModel.is_cloud == is_cloud)

        rows = query.group_by(Course.id, Course.code, Course.name).order_by(desc("sum_cost_thb")).all()

        results = []
        for r in rows:
            course_code = r.course_code or "UNASSIGNED"
            course_name = r.course_name or "General / Ad-hoc Lab"
            cpu_hours = round(float(r.sum_cpu_seconds) / 3600.0, 2)
            gpu_hours = round(float(r.sum_gpu_seconds) / 3600.0, 2)
            ram_hours = round(float(r.sum_ram_mb_hours), 2)
            cost_thb = round(float(r.sum_cost_thb), 2)

            results.append({
                "group_key": course_code,
                "group_name": f"{course_code}: {course_name}" if r.course_code else course_name,
                "course_id": str(r.course_id) if r.course_id else None,
                "total_sessions": int(r.total_sessions),
                "total_cpu_hours": cpu_hours,
                "total_gpu_hours": gpu_hours,
                "total_ram_mb_hours": ram_hours,
                "total_cost_thb": cost_thb,
                "is_cloud": None,
                "anon_id": None,
            })
        return results

    def aggregate_by_cluster(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """
        จัดกลุ่มยอดค่าใช้จ่ายตามรูปแบบ Cluster (AWS SkyPilot vs Local K3s)
        """
        query = (
            self.db.query(
                SessionModel.is_cloud.label("is_cloud"),
                SessionModel.service_type.label("service_type"),
                func.count(func.distinct(UsageRecord.session_id)).label("total_sessions"),
                func.coalesce(func.sum(UsageRecord.cpu_seconds), 0).label("sum_cpu_seconds"),
                func.coalesce(func.sum(UsageRecord.gpu_seconds), 0).label("sum_gpu_seconds"),
                func.coalesce(func.sum(UsageRecord.ram_mb_hours), 0).label("sum_ram_mb_hours"),
                func.coalesce(func.sum(UsageRecord.est_cost_thb), 0).label("sum_cost_thb"),
            )
            .join(SessionModel, UsageRecord.session_id == SessionModel.id)
            .outerjoin(Lab, SessionModel.lab_id == Lab.id)
        )

        if start_date:
            query = query.filter(UsageRecord.recorded_at >= start_date)
        if end_date:
            query = query.filter(UsageRecord.recorded_at <= end_date)
        if course_id:
            query = query.filter(Lab.course_id == course_id)
        if is_cloud is not None:
            query = query.filter(SessionModel.is_cloud == is_cloud)

        rows = query.group_by(SessionModel.is_cloud, SessionModel.service_type).order_by(desc("sum_cost_thb")).all()

        results = []
        for r in rows:
            is_cloud_val = bool(r.is_cloud)
            cluster_label = "AWS SkyPilot (Cloud)" if is_cloud_val else "Local K3s (On-Premises)"
            svc_name = r.service_type.value if hasattr(r.service_type, "value") else str(r.service_type)
            group_key = f"{'aws' if is_cloud_val else 'local_k3s'}_{svc_name}"
            group_name = f"{cluster_label} - {svc_name.upper()}"

            cpu_hours = round(float(r.sum_cpu_seconds) / 3600.0, 2)
            gpu_hours = round(float(r.sum_gpu_seconds) / 3600.0, 2)
            ram_hours = round(float(r.sum_ram_mb_hours), 2)
            cost_thb = round(float(r.sum_cost_thb), 2)

            results.append({
                "group_key": group_key,
                "group_name": group_name,
                "course_id": None,
                "total_sessions": int(r.total_sessions),
                "total_cpu_hours": cpu_hours,
                "total_gpu_hours": gpu_hours,
                "total_ram_mb_hours": ram_hours,
                "total_cost_thb": cost_thb,
                "is_cloud": is_cloud_val,
                "anon_id": None,
            })
        return results

    def aggregate_by_nat_subnet(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """
        จัดกลุ่มยอดค่าใช้จ่ายตามวง NAT Subnet ของแต่ละห้อง/คลาวด์
        """
        query = (
            self.db.query(
                SessionModel.is_cloud.label("is_cloud"),
                SessionModel.node_name.label("node_name"),
                func.count(func.distinct(UsageRecord.session_id)).label("total_sessions"),
                func.coalesce(func.sum(UsageRecord.cpu_seconds), 0).label("sum_cpu_seconds"),
                func.coalesce(func.sum(UsageRecord.gpu_seconds), 0).label("sum_gpu_seconds"),
                func.coalesce(func.sum(UsageRecord.ram_mb_hours), 0).label("sum_ram_mb_hours"),
                func.coalesce(func.sum(UsageRecord.est_cost_thb), 0).label("sum_cost_thb"),
            )
            .join(SessionModel, UsageRecord.session_id == SessionModel.id)
            .outerjoin(Lab, SessionModel.lab_id == Lab.id)
        )

        if start_date:
            query = query.filter(UsageRecord.recorded_at >= start_date)
        if end_date:
            query = query.filter(UsageRecord.recorded_at <= end_date)
        if course_id:
            query = query.filter(Lab.course_id == course_id)
        if is_cloud is not None:
            query = query.filter(SessionModel.is_cloud == is_cloud)

        rows = query.group_by(SessionModel.is_cloud, SessionModel.node_name).all()

        subnet_buckets: dict[str, dict[str, Any]] = {}
        for r in rows:
            is_cloud_val = bool(r.is_cloud)
            if is_cloud_val:
                subnet_cidr = "10.0.0.0/16"
                subnet_name = "AWS Cloud (Private Subnet)"
            else:
                node = str(r.node_name or "").lower()
                if "lab2" in node or "192.168.2" in node:
                    subnet_cidr = "192.168.2.0/24"
                    subnet_name = "Local K3s (Room 2 NAT)"
                elif "lab3" in node or "192.168.3" in node:
                    subnet_cidr = "192.168.3.0/24"
                    subnet_name = "Local K3s (Room 3 NAT)"
                else:
                    subnet_cidr = "192.168.1.0/24"
                    subnet_name = "Local K3s (Room 1 NAT)"

            if subnet_cidr not in subnet_buckets:
                subnet_buckets[subnet_cidr] = {
                    "group_key": subnet_cidr,
                    "group_name": f"{subnet_name} - {subnet_cidr}",
                    "course_id": None,
                    "total_sessions": 0,
                    "total_cpu_seconds": 0,
                    "total_gpu_seconds": 0,
                    "total_ram_mb_hours": 0.0,
                    "total_cost_thb": 0.0,
                    "is_cloud": is_cloud_val,
                    "nat_subnet": subnet_cidr,
                    "anon_id": None,
                }

            b = subnet_buckets[subnet_cidr]
            b["total_sessions"] += int(r.total_sessions)
            b["total_cpu_seconds"] += int(r.sum_cpu_seconds)
            b["total_gpu_seconds"] += int(r.sum_gpu_seconds)
            b["total_ram_mb_hours"] += float(r.sum_ram_mb_hours)
            b["total_cost_thb"] += float(r.sum_cost_thb)

        results = []
        for b in subnet_buckets.values():
            results.append({
                "group_key": b["group_key"],
                "group_name": b["group_name"],
                "course_id": None,
                "total_sessions": b["total_sessions"],
                "total_cpu_hours": round(b["total_cpu_seconds"] / 3600.0, 2),
                "total_gpu_hours": round(b["total_gpu_seconds"] / 3600.0, 2),
                "total_ram_mb_hours": round(b["total_ram_mb_hours"], 2),
                "total_cost_thb": round(b["total_cost_thb"], 2),
                "is_cloud": b["is_cloud"],
                "nat_subnet": b["nat_subnet"],
                "anon_id": None,
            })

        results.sort(key=lambda x: x["total_cost_thb"], reverse=True)
        return results

    def aggregate_by_user(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        course_id: Optional[UUID] = None,
        is_cloud: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """
        จัดกลุ่มยอดค่าใช้จ่ายตาม user_id จาก sessions เพื่อเตรียมนำไปแปลงเป็น anon_id
        (Strict Anonymity: ไม่ดึงชื่อ/อีเมลจากตาราง users เด็ดขาด)
        """
        query = (
            self.db.query(
                SessionModel.user_id.label("user_id"),
                func.count(func.distinct(UsageRecord.session_id)).label("total_sessions"),
                func.coalesce(func.sum(UsageRecord.cpu_seconds), 0).label("sum_cpu_seconds"),
                func.coalesce(func.sum(UsageRecord.gpu_seconds), 0).label("sum_gpu_seconds"),
                func.coalesce(func.sum(UsageRecord.ram_mb_hours), 0).label("sum_ram_mb_hours"),
                func.coalesce(func.sum(UsageRecord.est_cost_thb), 0).label("sum_cost_thb"),
            )
            .join(SessionModel, UsageRecord.session_id == SessionModel.id)
            .outerjoin(Lab, SessionModel.lab_id == Lab.id)
        )

        if start_date:
            query = query.filter(UsageRecord.recorded_at >= start_date)
        if end_date:
            query = query.filter(UsageRecord.recorded_at <= end_date)
        if course_id:
            query = query.filter(Lab.course_id == course_id)
        if is_cloud is not None:
            query = query.filter(SessionModel.is_cloud == is_cloud)

        rows = query.group_by(SessionModel.user_id).order_by(desc("sum_cost_thb")).all()

        results = []
        for r in rows:
            cpu_hours = round(float(r.sum_cpu_seconds) / 3600.0, 2)
            gpu_hours = round(float(r.sum_gpu_seconds) / 3600.0, 2)
            ram_hours = round(float(r.sum_ram_mb_hours), 2)
            cost_thb = round(float(r.sum_cost_thb), 2)

            results.append({
                "raw_user_id": r.user_id,
                "course_id": None,
                "total_sessions": int(r.total_sessions),
                "total_cpu_hours": cpu_hours,
                "total_gpu_hours": gpu_hours,
                "total_ram_mb_hours": ram_hours,
                "total_cost_thb": cost_thb,
                "is_cloud": None,
            })
        return results

    def create_report_record(
        self,
        title: str,
        group_by: str,
        export_format: str,
        file_name: str,
        total_cost_thb: float,
        total_records: int,
        created_by: UUID,
    ) -> BillingReport:
        """บันทึกประวัติการออกรายงานลงฐานข้อมูล"""
        report = BillingReport(
            title=title,
            group_by=group_by,
            export_format=export_format,
            file_name=file_name,
            total_cost_thb=Decimal(str(round(total_cost_thb, 2))),
            total_records=total_records,
            created_by=created_by,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def list_reports(
        self,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> tuple[list[BillingReport], int]:
        """
        ดึงรายการประวัติรายงาน โดยใช้กลไก Soft-Delete
        (ไม่แสดงแถวที่มี deleted_at เว้นแต่จะระบุ include_deleted=True)
        """
        query = self.db.query(BillingReport)
        if not include_deleted:
            query = query.filter(BillingReport.deleted_at.is_(None))

        total = query.count()
        reports = query.order_by(desc(BillingReport.created_at)).offset(offset).limit(limit).all()
        return reports, total

    def get_report_by_id(self, report_id: UUID) -> Optional[BillingReport]:
        """ดึงรายงานตาม ID (ไม่ดึงรายการที่ถูก soft-delete)"""
        return (
            self.db.query(BillingReport)
            .filter(BillingReport.id == report_id, BillingReport.deleted_at.is_(None))
            .first()
        )

    def soft_delete_report(self, report_id: UUID) -> bool:
        """
        ทำการ Soft-Delete รายงานตามข้อกำหนด
        โดยตั้งค่า deleted_at เป็นเวลาปัจจุบัน ห้ามลบแถวออกจากฐานข้อมูลจริง
        """
        report = self.get_report_by_id(report_id)
        if not report:
            return False

        report.deleted_at = func.now()
        self.db.commit()
        return True
