"""
MonitorController
Controller สำหรับระบบ Monitor / Metrics / Logs
ทำหน้าที่เป็นตัวกลางระหว่าง Route และ Service
"""

from typing import Optional
from app.schemas.monitor_schema import (
    ClusterMetricsResponse,
    LogListResponse,
    SecurityCountersResponse,
)
from app.services.monitor_service import MonitorService


class MonitorController:
    """Controller สำหรับจัดการการร้องขอเกี่ยวกับ Cluster Metrics, Security Counters และ Logs"""

    def __init__(self, monitor_service: MonitorService):
        self.monitor_service = monitor_service

    def get_cluster_metrics(
        self,
        provider: Optional[str] = None,
        nat_subnet: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> ClusterMetricsResponse:
        """ดึงข้อมูลภาพรวมสถานะทรัพยากร (CPU, RAM, Active Sessions) และ Security Counters"""
        return self.monitor_service.get_cluster_metrics(
            provider=provider,
            nat_subnet=nat_subnet,
            group_by=group_by,
        )

    def get_security_counters(self) -> SecurityCountersResponse:
        """ดึงสถิติตัวนับการละเมิดความปลอดภัย (Squid, Kyverno, Tailscale)"""
        return self.monitor_service.get_security_counters()

    def get_critical_logs(
        self,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> LogListResponse:
        """ดึงรายการ Critical Logs และ Security Violation Logs ที่ผ่านการทำ Data Masking แล้ว"""
        return self.monitor_service.get_critical_logs(
            severity=severity,
            category=category,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )
