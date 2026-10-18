"""
Monitor Schemas
Schema สำหรับ Resource Allocation Metrics, Security Counters และ Infrastructure Logs
สืบทอดจาก CamelModel เพื่อส่งออกในรูปแบบ CamelCase เสมอ
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import Field

from app.schemas.base import CamelModel


class LogSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class LogCategory(str, Enum):
    INFRASTRUCTURE = "INFRASTRUCTURE"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    BURST = "BURST"
    CONTAINER = "CONTAINER"


class ResourceMetric(CamelModel):
    total: float = Field(..., description="จำนวนรวมทั้งหมดของทรัพยากร")
    allocated: float = Field(..., description="จำนวนที่ถูกจองหรือใช้งานอยู่")
    available: float = Field(..., description="จำนวนที่ยังคงเหลือให้ใช้งานได้")
    utilization_percent: float = Field(..., description="เปอร์เซ็นต์การใช้งาน")
    unit: str = Field(..., description="หน่วย เช่น cores, MB, GB")


class SubnetMetrics(CamelModel):
    nat_subnet: str = Field(..., description="วง Network / NAT Subnet เช่น 192.168.1.0/24")
    room_name: Optional[str] = Field(None, description="ชื่อห้องแลป เช่น Lab Room 1")
    node_count: int = Field(default=0, description="จำนวน Node ในวงนี้")
    active_sessions: int = Field(default=0, description="จำนวน Active Sessions")
    cpu_allocated: float = Field(default=0.0, description="CPU ที่ถูกจัดสรร (cores)")
    ram_allocated_mb: float = Field(default=0.0, description="RAM ที่ถูกจัดสรร (MB)")


class ProviderMetrics(CamelModel):
    provider: str = Field(..., description="ผู้ให้บริการโครงสร้างพื้นฐาน เช่น aws หรือ local_k3s")
    status: str = Field(default="healthy", description="สถานะของผู้ให้บริการ")
    active_sessions: int = Field(default=0, description="จำนวน Active Sessions")
    cpu_total: float = Field(default=0.0, description="CPU รวมทั้งหมด")
    cpu_allocated: float = Field(default=0.0, description="CPU ที่ถูกจัดสรร")
    ram_total_mb: float = Field(default=0.0, description="RAM รวมทั้งหมด (MB)")
    ram_allocated_mb: float = Field(default=0.0, description="RAM ที่ถูกจัดสรร (MB)")
    subnets: Optional[list[SubnetMetrics]] = Field(default=None, description="แยกตามวง NAT สำหรับ Local K3s")


class SecurityCountersResponse(CamelModel):
    squid_egress_drops: int = Field(default=0, description="จำนวนครั้งที่ Squid Proxy ดรอป Traffic นอก Allowlist")
    kyverno_policy_blocks: int = Field(default=0, description="จำนวนครั้งที่ OPA/Kyverno บล็อกการตั้งค่าอันตราย")
    tailscale_cross_cluster_attempts: int = Field(default=0, description="จำนวนการพยายามเชื่อมต่อข้าม Cluster ใน Tailscale")
    total_violations: int = Field(default=0, description="จำนวนรวมการละเมิดความปลอดภัยทั้งหมด")
    last_violation_timestamp: Optional[datetime] = Field(None, description="เวลาที่เกิดการละเมิดล่าสุด")


class ClusterMetricsSummary(CamelModel):
    total_active_sessions: int = Field(default=0, description="Active Sessions ทั้งหมดในระบบ")
    cpu: ResourceMetric = Field(..., description="ภาพรวม CPU รวมทั้งระบบ")
    ram: ResourceMetric = Field(..., description="ภาพรวม RAM รวมทั้งระบบ")


class ClusterMetricsResponse(CamelModel):
    summary: ClusterMetricsSummary = Field(..., description="สรุปภาพรวมทรัพยากร")
    by_provider: list[ProviderMetrics] = Field(..., description="สถิติทรัพยากรแยกตาม Provider (AWS / Local K3s)")
    security_violation_counters: SecurityCountersResponse = Field(..., description="ตัวเลขสถิติการละเมิดความปลอดภัย")


class InfrastructureLogItem(CamelModel):
    id: str = Field(..., description="ID ประจำ Log Entry")
    timestamp: datetime = Field(..., description="วันเวลาที่เกิดเหตุการณ์ (ISO Format)")
    severity: LogSeverity = Field(..., description="ระดับความรุนแรงของ Log")
    category: LogCategory = Field(..., description="หมวดหมู่ของเหตุการณ์")
    event_type: str = Field(..., description="ประเภทเหตุการณ์ เช่น NODE_DOWN, SKY_BURST_FAILED, OOM_KILLED")
    source: str = Field(..., description="ต้นทางของเหตุการณ์ เช่น worker-01, skypilot-aws, squid-proxy")
    message: str = Field(..., description="ข้อความแจ้งเตือนที่ผ่านการ Masking แล้ว")
    anon_id: Optional[str] = Field(None, description="HMAC-SHA256 Pseudonymized ID ของผู้ใช้ เช่น anon_8f92a1")
    cluster_or_subnet: Optional[str] = Field(None, description="Cluster หรือวง NAT ที่เกี่ยวข้อง")
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="ข้อมูลแวดล้อมเพิ่มเติมที่ไม่มี PII")


class LogListResponse(CamelModel):
    logs: list[InfrastructureLogItem] = Field(default_factory=list, description="รายการ Log")
    total: int = Field(default=0, description="จำนวน Log ทั้งหมดตามเงื่อนไข")


class CreateInfrastructureLogRequest(CamelModel):
    timestamp: Optional[datetime] = Field(None, description="วันเวลาที่เกิดเหตุการณ์ (หากไม่ระบุจะใช้เวลาปัจจุบัน)")
    severity: LogSeverity = Field(..., description="ระดับความรุนแรงของ Log (critical, error, warning, info)")
    category: LogCategory = Field(..., description="หมวดหมู่ของเหตุการณ์")
    event_type: str = Field(..., description="ประเภทเหตุการณ์ เช่น NODE_DOWN, SKY_BURST_FAILED, SQUID_EGRESS_DROP")
    source: str = Field(..., description="ต้นทางของเหตุการณ์")
    message: str = Field(..., description="ข้อความแจ้งเตือนดิบ (จะถูก Masking อัตโนมัติก่อนบันทึก)")
    user_id: Optional[str] = Field(None, description="UUID ของผู้ใช้งานที่เกี่ยวข้อง (จะถูกแปลงเป็น anon_id อัตโนมัติ)")
    cluster_or_subnet: Optional[str] = Field(None, description="Cluster หรือวง NAT ที่เกี่ยวข้อง")
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="ข้อมูลแวดล้อมเพิ่มเติม")

