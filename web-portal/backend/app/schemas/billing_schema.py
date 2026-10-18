"""
Billing Schemas
Schema สำหรับ Billing Aggregation และ Anonymized Export API
สืบทอดจาก CamelModel เพื่อส่งออกในรูปแบบ CamelCase เสมอ
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import Field

from app.schemas.base import CamelModel


class BillingGroupBy(str, Enum):
    COURSE = "course"
    CLUSTER = "cluster"
    ANON_ID = "anon_id"


class ExportFormat(str, Enum):
    CSV = "csv"
    PDF = "pdf"


class BillingItem(CamelModel):
    group_key: str = Field(..., description="Key ประจำกลุ่ม เช่น รหัสวิชา, ประเภทคลัสเตอร์, หรือ anon_id")
    group_name: Optional[str] = Field(None, description="ชื่อที่ใช้แสดง เช่น CS101 - Intro to CS หรือ AWS SkyPilot Cloud")
    total_sessions: int = Field(default=0, description="จำนวน Sessions รวมในกลุ่มนี้")
    total_cpu_hours: float = Field(default=0.0, description="จำนวน CPU-Hours รวม")
    total_gpu_hours: float = Field(default=0.0, description="จำนวน GPU-Hours รวม")
    total_ram_mb_hours: float = Field(default=0.0, description="จำนวน RAM (MB-Hours) รวม")
    total_cost_thb: float = Field(default=0.0, description="ยอดค่าใช้จ่ายรวม (บาท)")
    is_cloud: Optional[bool] = Field(None, description="สถานะว่าเป็น Cloud (AWS) หรือไม่")
    course_id: Optional[str] = Field(None, description="ID ของรายวิชา (ถ้าจัดกลุ่มตามวิชา)")
    anon_id: Optional[str] = Field(None, description="HMAC-SHA256 Pseudonymized ID (ถ้าจัดกลุ่มตาม anon_id)")


class BillingSummaryResponse(CamelModel):
    group_by: str = Field(..., description="เกณฑ์การจัดกลุ่ม: course, cluster, หรือ anon_id")
    total_cost_thb: float = Field(default=0.0, description="ยอดค่าใช้จ่ายรวมทั้งสิ้น (บาท)")
    total_sessions: int = Field(default=0, description="จำนวน Sessions ทั้งหมดที่คำนวณ")
    total_cpu_hours: float = Field(default=0.0, description="จำนวน CPU-Hours รวมทั้งสิ้น")
    total_gpu_hours: float = Field(default=0.0, description="จำนวน GPU-Hours รวมทั้งสิ้น")
    total_ram_mb_hours: float = Field(default=0.0, description="จำนวน RAM MB-Hours รวมทั้งสิ้น")
    items: list[BillingItem] = Field(default_factory=list, description="รายการสรุปแยกตามกลุ่ม")
    period_start: Optional[datetime] = Field(None, description="วันเริ่มต้นรอบการคำนวณ")
    period_end: Optional[datetime] = Field(None, description="วันสิ้นสุดรอบการคำนวณ")


class BillingReportResponse(CamelModel):
    id: str = Field(..., description="ID ของรายงาน")
    title: str = Field(..., description="ชื่อรายงาน")
    group_by: str = Field(..., description="เกณฑ์การจัดกลุ่มที่ส่งออก")
    export_format: str = Field(..., description="รูปแบบไฟล์ (csv, pdf)")
    file_name: str = Field(..., description="ชื่อไฟล์รายงาน")
    total_cost_thb: float = Field(default=0.0, description="ยอดค่าใช้จ่ายรวมในรายงาน")
    total_records: int = Field(default=0, description="จำนวนแถวในรายงาน")
    created_at: datetime = Field(..., description="เวลาที่สร้างรายงาน")
    created_by: str = Field(..., description="User ID ของผู้สร้างรายงาน")
    is_deleted: bool = Field(default=False, description="สถานะว่าถูก Soft-Delete หรือไม่")


class BillingReportListResponse(CamelModel):
    reports: list[BillingReportResponse] = Field(default_factory=list, description="รายการประวัติรายงาน")
    total: int = Field(default=0, description="จำนวนรายงานทั้งหมด")
