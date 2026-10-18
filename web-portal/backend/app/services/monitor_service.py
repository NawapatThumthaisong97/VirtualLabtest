"""
MonitorService
Business logic สำหรับคำนวณ Cluster Resource Metrics, Security Violation Counters
และจัดการ Infrastructure & Security Logs พร้อมทั้งทำ Data Masking ผ่าน LogMaskerService
"""

from typing import Any, Optional
from sqlalchemy.orm import Session as DbSession

from app.repositories.monitor_repository import MonitorRepository
from app.schemas.monitor_schema import (
    ClusterMetricsResponse,
    ClusterMetricsSummary,
    InfrastructureLogItem,
    LogListResponse,
    ProviderMetrics,
    ResourceMetric,
    SecurityCountersResponse,
    SubnetMetrics,
)
from app.services.kubernetes_service import KubernetesService, get_kubernetes_service
from app.services.log_masker_service import LogMaskerService
from app.utils.logger import logger


class MonitorService:
    """Service สำหรับเฝ้าระวังทรัพยากร, ความปลอดภัย และ Logs ระดับโครงสร้างพื้นฐาน (SIEM-Ready)"""

    # Baseline Capacities
    LOCAL_K3S_TOTAL_CPU = 64.0
    LOCAL_K3S_TOTAL_RAM_MB = 131072.0  # 128 GB
    AWS_TOTAL_CPU = 128.0
    AWS_TOTAL_RAM_MB = 262144.0  # 256 GB

    SUBNET_ROOM_MAP = {
        "192.168.1.0/24": "Lab Room 1 (Software Lab)",
        "192.168.2.0/24": "Lab Room 2 (AI/Data Lab)",
        "192.168.3.0/24": "Lab Room 3 (Network Lab)",
    }

    def __init__(
        self,
        db: DbSession,
        monitor_repo: Optional[MonitorRepository] = None,
        log_masker: Optional[LogMaskerService] = None,
        k8s_service: Optional[KubernetesService] = None,
    ):
        self.db = db
        self.monitor_repo = monitor_repo or MonitorRepository(db)
        self.log_masker = log_masker or LogMaskerService()
        self.k8s_service = k8s_service

    def _get_k8s_capacity(self) -> tuple[float, float, int]:
        """
        ดึง capacity สด ๆ จาก Kubernetes API หากเชื่อมต่อได้
        คืนค่า (total_cpu, total_ram_mb, node_count)
        """
        if self.k8s_service:
            try:
                nodes = self.k8s_service.get_nodes()
                total_cpu = 0.0
                total_ram_kb = 0.0
                for node in nodes:
                    cpu_val = node.get("cpu")
                    mem_val = str(node.get("memory") or "0")
                    if cpu_val:
                        try:
                            total_cpu += float(cpu_val)
                        except ValueError:
                            pass
                    if "Ki" in mem_val:
                        total_ram_kb += float(mem_val.replace("Ki", ""))
                total_ram_mb = total_ram_kb / 1024.0 if total_ram_kb > 0 else self.LOCAL_K3S_TOTAL_RAM_MB
                total_cpu = total_cpu if total_cpu > 0 else self.LOCAL_K3S_TOTAL_CPU
                return total_cpu, total_ram_mb, len(nodes)
            except Exception as e:
                logger.warning(f"Failed to query k8s nodes capacity: {e}")

        return self.LOCAL_K3S_TOTAL_CPU, self.LOCAL_K3S_TOTAL_RAM_MB, 8

    def get_cluster_metrics(
        self,
        provider: Optional[str] = None,
        nat_subnet: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> ClusterMetricsResponse:
        """
        คำนวณภาพรวมทรัพยากร (CPU, RAM, Active Sessions)
        รองรับการ Filter/Group ระหว่าง AWS SkyPilot และ Local K3s แยกตามวง NAT
        """
        sessions = self.monitor_repo.get_active_sessions_data()
        k3s_total_cpu, k3s_total_ram_mb, k3s_node_count = self._get_k8s_capacity()

        # แยก Sessions ตาม Provider
        aws_sessions = [s for s in sessions if s.get("is_aws")]
        k3s_sessions = [s for s in sessions if not s.get("is_aws")]

        # คำนวณฝั่ง AWS SkyPilot
        aws_active_count = len(aws_sessions)
        aws_cpu_alloc = sum(s.get("cpu_allocated", 0.0) for s in aws_sessions)
        aws_ram_alloc = sum(s.get("ram_allocated_mb", 0.0) for s in aws_sessions)

        # คำนวณฝั่ง Local K3s
        k3s_active_count = len(k3s_sessions)
        k3s_cpu_alloc = sum(s.get("cpu_allocated", 0.0) for s in k3s_sessions)
        k3s_ram_alloc = sum(s.get("ram_allocated_mb", 0.0) for s in k3s_sessions)

        # แยกย่อย Local K3s ตามวง NAT
        subnet_groups: dict[str, dict[str, Any]] = {
            "192.168.1.0/24": {
                "active_sessions": 0,
                "cpu_allocated": 0.0,
                "ram_allocated_mb": 0.0,
                "node_count": 4,
            },
            "192.168.2.0/24": {
                "active_sessions": 0,
                "cpu_allocated": 0.0,
                "ram_allocated_mb": 0.0,
                "node_count": 4,
            },
        }

        for s in k3s_sessions:
            sub = s.get("nat_subnet") or "192.168.1.0/24"
            if sub not in subnet_groups:
                subnet_groups[sub] = {
                    "active_sessions": 0,
                    "cpu_allocated": 0.0,
                    "ram_allocated_mb": 0.0,
                    "node_count": 2,
                }
            subnet_groups[sub]["active_sessions"] += 1
            subnet_groups[sub]["cpu_allocated"] += s.get("cpu_allocated", 0.0)
            subnet_groups[sub]["ram_allocated_mb"] += s.get("ram_allocated_mb", 0.0)

        # Filter ตาม nat_subnet ถ้ามีการระบุ
        if nat_subnet:
            subnet_groups = {k: v for k, v in subnet_groups.items() if k == nat_subnet}

        subnets_metric_list = [
            SubnetMetrics(
                nat_subnet=sub,
                room_name=self.SUBNET_ROOM_MAP.get(sub, f"Room {sub}"),
                node_count=data["node_count"],
                active_sessions=data["active_sessions"],
                cpu_allocated=round(data["cpu_allocated"], 2),
                ram_allocated_mb=round(data["ram_allocated_mb"], 2),
            )
            for sub, data in subnet_groups.items()
        ]

        # สร้าง Provider Metrics
        providers_list: list[ProviderMetrics] = []

        local_k3s_metric = ProviderMetrics(
            provider="local_k3s",
            status="healthy",
            active_sessions=k3s_active_count,
            cpu_total=round(k3s_total_cpu, 2),
            cpu_allocated=round(k3s_cpu_alloc, 2),
            ram_total_mb=round(k3s_total_ram_mb, 2),
            ram_allocated_mb=round(k3s_ram_alloc, 2),
            subnets=subnets_metric_list,
        )

        aws_metric = ProviderMetrics(
            provider="aws",
            status="healthy",
            active_sessions=aws_active_count,
            cpu_total=round(self.AWS_TOTAL_CPU, 2),
            cpu_allocated=round(aws_cpu_alloc, 2),
            ram_total_mb=round(self.AWS_TOTAL_RAM_MB, 2),
            ram_allocated_mb=round(aws_ram_alloc, 2),
            subnets=None,
        )

        # กรองตาม provider query parameter
        if provider:
            prov_lower = provider.lower()
            if prov_lower in ("aws", "cloud", "skypilot"):
                providers_list.append(aws_metric)
            elif prov_lower in ("local_k3s", "k3s", "local"):
                providers_list.append(local_k3s_metric)
            else:
                providers_list.extend([local_k3s_metric, aws_metric])
        else:
            providers_list.extend([local_k3s_metric, aws_metric])

        # สรุปภาพรวมรวมทั้งระบบ
        total_active_sessions = len(sessions)
        overall_cpu_total = k3s_total_cpu + self.AWS_TOTAL_CPU
        overall_cpu_alloc = k3s_cpu_alloc + aws_cpu_alloc
        overall_cpu_avail = max(overall_cpu_total - overall_cpu_alloc, 0.0)
        cpu_util_pct = (overall_cpu_alloc / overall_cpu_total * 100.0) if overall_cpu_total > 0 else 0.0

        overall_ram_total = k3s_total_ram_mb + self.AWS_TOTAL_RAM_MB
        overall_ram_alloc = k3s_ram_alloc + aws_ram_alloc
        overall_ram_avail = max(overall_ram_total - overall_ram_alloc, 0.0)
        ram_util_pct = (overall_ram_alloc / overall_ram_total * 100.0) if overall_ram_total > 0 else 0.0

        summary = ClusterMetricsSummary(
            total_active_sessions=total_active_sessions,
            cpu=ResourceMetric(
                total=round(overall_cpu_total, 2),
                allocated=round(overall_cpu_alloc, 2),
                available=round(overall_cpu_avail, 2),
                utilization_percent=round(cpu_util_pct, 2),
                unit="cores",
            ),
            ram=ResourceMetric(
                total=round(overall_ram_total, 2),
                allocated=round(overall_ram_alloc, 2),
                available=round(overall_ram_avail, 2),
                utilization_percent=round(ram_util_pct, 2),
                unit="MB",
            ),
        )

        sec_counters = self.get_security_counters()

        return ClusterMetricsResponse(
            summary=summary,
            by_provider=providers_list,
            security_violation_counters=sec_counters,
        )

    def get_security_counters(self) -> SecurityCountersResponse:
        """ดึงตัวเลขสถิติการละเมิดความปลอดภัย (Squid, OPA/Kyverno, Tailscale)"""
        counters = self.monitor_repo.get_security_counters()
        squid_drops = int(counters.get("squid_egress_drops", 0))
        kyverno_blocks = int(counters.get("kyverno_policy_blocks", 0))
        tailscale_attempts = int(counters.get("tailscale_cross_cluster_attempts", 0))
        total = squid_drops + kyverno_blocks + tailscale_attempts

        return SecurityCountersResponse(
            squid_egress_drops=squid_drops,
            kyverno_policy_blocks=kyverno_blocks,
            tailscale_cross_cluster_attempts=tailscale_attempts,
            total_violations=total,
            last_violation_timestamp=counters.get("last_violation_timestamp"),
        )

    def get_critical_logs(
        self,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> LogListResponse:
        """
        ดึงรายการ Critical Logs และ Security Violation Logs
        พร้อมทำการ Mask PII, ตัด Source Code, และแปลง user_id เป็น anon_id ผ่าน LogMaskerService
        """
        raw_logs, total = self.monitor_repo.get_infrastructure_logs(
            severity=severity,
            category=category,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )

        sanitized_logs: list[InfrastructureLogItem] = []
        for raw_entry in raw_logs:
            masked = self.log_masker.mask_log_record(raw_entry)
            sanitized_logs.append(
                InfrastructureLogItem(
                    id=str(masked.get("id")),
                    timestamp=masked.get("timestamp"),
                    severity=masked.get("severity"),
                    category=masked.get("category"),
                    event_type=str(masked.get("event_type")),
                    source=str(masked.get("source")),
                    message=str(masked.get("message")),
                    anon_id=masked.get("anon_id"),
                    cluster_or_subnet=masked.get("cluster_or_subnet"),
                    metadata=masked.get("metadata") or {},
                )
            )

        return LogListResponse(logs=sanitized_logs, total=total)
