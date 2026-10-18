"""
MonitorRepository
Data access layer สำหรับดึงข้อมูล Session Traces, คำนวณ Resource Allocations,
และจัดการ Event Logs และ Security Counters สำหรับ SIEM
"""

from datetime import datetime, timezone, timedelta
import ipaddress
import re
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session as DbSession
from sqlalchemy import func

from app.models.infrastructure_log import InfrastructureLog
from app.models.lab import Lab, RunTarget
from app.models.lab_image import LabImage
from app.models.session import Session as SessionModel, SessionStatus, SessionEndReason
from app.schemas.monitor_schema import (
    LogCategory,
    LogSeverity,
    InfrastructureLogItem,
    SecurityCountersResponse,
    SubnetMetrics,
)


class MonitorRepository:
    """Repository สำหรับระบบ Monitor / Metrics / Logs"""

    # Static in-memory storage สำหรับ Security Counters และ Boundary Audit Events
    _security_counters = {
        "squid_egress_drops": 42,
        "kyverno_policy_blocks": 15,
        "tailscale_cross_cluster_attempts": 7,
        "last_violation_timestamp": datetime.now(timezone.utc) - timedelta(minutes=12),
    }

    _infrastructure_logs: list[dict[str, Any]] = [
        {
            "id": "log-001",
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=45),
            "severity": LogSeverity.CRITICAL,
            "category": LogCategory.INFRASTRUCTURE,
            "event_type": "NODE_DOWN",
            "source": "k3s-worker-lab1-04",
            "message": "Node k3s-worker-lab1-04 status changed to NotReady: Kubelet stopped posting node status",
            "user_id": None,
            "cluster_or_subnet": "192.168.1.0/24",
            "metadata": {"node": "k3s-worker-lab1-04", "condition": "Ready=False"},
        },
        {
            "id": "log-002",
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=30),
            "severity": LogSeverity.ERROR,
            "category": LogCategory.BURST,
            "event_type": "SKY_BURST_FAILED",
            "source": "skypilot-aws-controller",
            "message": "SkyPilot AWS Cloud burst failed: InsufficientInstanceCapacity in ap-southeast-1a for g4dn.xlarge",
            "user_id": "b3978d2d-4dba-4eb5-b2f7-3d64da1dae20",
            "cluster_or_subnet": "aws-ap-southeast-1",
            "metadata": {"instanceType": "g4dn.xlarge", "region": "ap-southeast-1"},
        },
        {
            "id": "log-003",
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=20),
            "severity": LogSeverity.ERROR,
            "category": LogCategory.CONTAINER,
            "event_type": "OOM_KILLED",
            "source": "k3s-worker-lab2-02",
            "message": "Pod container exceeded memory limit (cgroup limit: 4096MB) and was terminated with OOMKilled",
            "user_id": "c447913e-c85b-432f-aca3-346f4c1d2e37",
            "cluster_or_subnet": "192.168.2.0/24",
            "metadata": {"pod": "warm-pod-ai-lab-9f12", "memoryLimitMb": 4096},
        },
        {
            "id": "log-004",
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=15),
            "severity": LogSeverity.WARNING,
            "category": LogCategory.SECURITY_VIOLATION,
            "event_type": "SQUID_EGRESS_DROP",
            "source": "squid-proxy-egress",
            "message": "Squid Proxy dropped TCP traffic to external destination 198.51.100.24:443 (Domain outside strict allowlist)",
            "user_id": "388faa77-f790-438e-98bf-67e9b3994fc0",
            "cluster_or_subnet": "192.168.1.0/24",
            "metadata": {"destination": "198.51.100.24:443", "protocol": "TCP"},
        },
        {
            "id": "log-005",
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=12),
            "severity": LogSeverity.CRITICAL,
            "category": LogCategory.SECURITY_VIOLATION,
            "event_type": "OPA_KYVERNO_BLOCK",
            "source": "kyverno-admission-controller",
            "message": "Kyverno policy disallow-privileged-containers blocked pod creation with securityContext.privileged=true",
            "user_id": "79b86136-1523-4710-8e8f-bcfa62342c3c",
            "cluster_or_subnet": "192.168.2.0/24",
            "metadata": {"policy": "disallow-privileged-containers", "resource": "Pod"},
        },
        {
            "id": "log-006",
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=5),
            "severity": LogSeverity.WARNING,
            "category": LogCategory.SECURITY_VIOLATION,
            "event_type": "TAILSCALE_CROSS_CLUSTER_ATTEMPT",
            "source": "tailscale-acl-filter",
            "message": "Blocked unauthorized cross-cluster access attempt from node in Lab Room 1 to Lab Room 2 control plane",
            "user_id": "1de330da-7c12-4eca-a5be-ee928e92c7f3",
            "cluster_or_subnet": "192.168.1.0/24",
            "metadata": {"srcIp": "100.64.0.12", "dstIp": "100.64.1.5"},
        },
    ]

    def __init__(self, db: DbSession):
        self.db = db

    @staticmethod
    def _parse_cpu_requirement(cpu_str: Optional[str]) -> float:
        """แปลง CPU requirement เช่น '2+', '4', '0.5' เป็นตัวเลข float"""
        if not cpu_str:
            return 2.0
        match = re.search(r"(\d+(?:\.\d+)?)", str(cpu_str))
        if match:
            return float(match.group(1))
        return 2.0

    @staticmethod
    def _extract_nat_subnet(node_name: Optional[str]) -> str:
        """
        จัดกลุ่ม Node เข้าวง NAT Subnet เช่น
        - k3s-worker-lab1-* หรือ 192.168.1.* -> 192.168.1.0/24 (Lab Room 1)
        - k3s-worker-lab2-* หรือ 192.168.2.* -> 192.168.2.0/24 (Lab Room 2)
        - ค่าอื่น ๆ -> default subnet
        """
        if not node_name:
            return "192.168.1.0/24"
        text_str = str(node_name).strip()
        if "lab2" in text_str.lower() or "192.168.2" in text_str:
            return "192.168.2.0/24"
        if "lab3" in text_str.lower() or "192.168.3" in text_str:
            return "192.168.3.0/24"
        try:
            ip_obj = ipaddress.ip_address(text_str)
            network = ipaddress.ip_network(f"{ip_obj}/24", strict=False)
            return str(network)
        except ValueError:
            return "192.168.1.0/24"

    def get_active_sessions_data(self) -> list[dict[str, Any]]:
        """
        ดึงข้อมูล Active Sessions ทั้งหมดจาก DB พร้อมรายละเอียด resource
        """
        query = (
            self.db.query(SessionModel, Lab, LabImage)
            .outerjoin(Lab, SessionModel.lab_id == Lab.id)
            .outerjoin(LabImage, SessionModel.lab_image_id == LabImage.id)
            .filter(SessionModel.status.in_([SessionStatus.RUNNING, SessionStatus.PENDING]))
        )

        results = []
        for session, lab, lab_image in query.all():
            is_aws = (
                session.is_cloud
                or (lab and lab.run_target == RunTarget.AWS)
                or (session.sky_cluster_name and "aws" in session.sky_cluster_name.lower())
            )
            cpu = self._parse_cpu_requirement(lab_image.cpu_requirement if lab_image else "2")
            ram_mb = float(lab_image.size_mb) if lab_image and lab_image.size_mb else 4096.0

            results.append({
                "session_id": session.id,
                "user_id": session.user_id,
                "status": session.status,
                "is_aws": is_aws,
                "node_name": session.node_name,
                "nat_subnet": self._extract_nat_subnet(session.node_name),
                "cpu_allocated": cpu,
                "ram_allocated_mb": ram_mb,
                "created_at": session.started_at,
            })
        return results

    def get_security_counters(self) -> dict[str, Any]:
        """ดึงตัวเลขสถิติ Security Violation Counters"""
        return dict(self._security_counters)

    def increment_security_counter(self, counter_name: str, count: int = 1) -> None:
        """เพิ่มค่าตัวนับ Security Violation Counter"""
        if counter_name in self._security_counters:
            self._security_counters[counter_name] += count
            self._security_counters["last_violation_timestamp"] = datetime.now(timezone.utc)

    def get_infrastructure_logs(
        self,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        ดึง Critical Error Logs และ Security Violation Logs พร้อมรองรับ Filter
        ดึงจากตาราง infrastructure_logs ในฐานข้อมูล และรวม Session failures
        """
        all_logs: list[dict[str, Any]] = []

        # 1. ดึงจากตาราง infrastructure_logs ใน DB ก่อน
        try:
            db_query = self.db.query(InfrastructureLog)
            if severity:
                db_query = db_query.filter(func.lower(InfrastructureLog.severity) == severity.lower())
            if category:
                db_query = db_query.filter(func.lower(InfrastructureLog.category) == category.lower())
            if event_type:
                db_query = db_query.filter(func.lower(InfrastructureLog.event_type) == event_type.lower())

            db_records = db_query.order_by(InfrastructureLog.timestamp.desc()).all()
            for r in db_records:
                all_logs.append({
                    "id": str(r.id),
                    "timestamp": r.timestamp,
                    "severity": r.severity,
                    "category": r.category,
                    "event_type": r.event_type,
                    "source": r.source,
                    "message": r.message,
                    "anon_id": r.anon_id,
                    "user_id": None,
                    "cluster_or_subnet": r.cluster_or_subnet,
                    "metadata": r.metadata_json or {},
                })
        except Exception:
            pass

        # 2. รวม in-memory default logs หากยังไม่มีข้อมูลใน DB
        if not all_logs:
            all_logs.extend(self._infrastructure_logs)

        # 3. ดึง sessions ที่ failed ใน DB เพื่อสร้าง log entry เชื่อมโยงเหตุการณ์
        failed_sessions = (
            self.db.query(SessionModel)
            .filter(
                SessionModel.status.in_([SessionStatus.FAILED, SessionStatus.STOPPED]),
                SessionModel.end_reason.in_([
                    SessionEndReason.LAUNCH_FAILED,
                    SessionEndReason.LOST,
                    SessionEndReason.STALE_PENDING,
                ]),
            )
            .order_by(SessionModel.ended_at.desc())
            .limit(20)
            .all()
        )

        for s in failed_sessions:
            is_aws = s.is_cloud or (s.sky_cluster_name and "aws" in s.sky_cluster_name.lower())
            event_type_val = "SKY_BURST_FAILED" if is_aws else "NODE_DOWN"
            category_val = LogCategory.BURST if is_aws else LogCategory.INFRASTRUCTURE
            all_logs.append({
                "id": f"sess-fail-{s.id}",
                "timestamp": s.ended_at or s.started_at or datetime.now(timezone.utc),
                "severity": LogSeverity.ERROR,
                "category": category_val,
                "event_type": event_type_val,
                "source": s.sky_cluster_name or "cluster-controller",
                "message": f"Session {s.id} failed with reason: {s.end_reason.value if s.end_reason else 'Unknown'}",
                "user_id": s.user_id,
                "cluster_or_subnet": "aws-ap-southeast-1" if is_aws else "192.168.1.0/24",
                "metadata": {"sessionId": str(s.id), "endReason": s.end_reason.value if s.end_reason else None},
            })

        # กรองข้อมูลตาม Parameters
        filtered = all_logs
        if severity:
            sev_upper = severity.upper()
            filtered = [item for item in filtered if (item.get("severity").value if hasattr(item.get("severity"), "value") else str(item.get("severity"))).upper() == sev_upper]
        if category:
            cat_upper = category.upper()
            filtered = [item for item in filtered if (item.get("category").value if hasattr(item.get("category"), "value") else str(item.get("category"))).upper() == cat_upper]
        if event_type:
            et_upper = event_type.upper()
            filtered = [item for item in filtered if str(item.get("event_type", "")).upper() == et_upper]

        # เรียงตามเวลาใหม่สุดก่อน
        filtered.sort(
            key=lambda x: x.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        total = len(filtered)
        paginated = filtered[offset : offset + limit]
        return paginated, total

    def save_log(self, entry: dict[str, Any]) -> InfrastructureLog:
        """
        บันทึก Log Entry ลงฐานข้อมูล table infrastructure_logs
        และอัปเดต Security Violation Counters
        """
        log_id = uuid4()
        if entry.get("id"):
            try:
                log_id = UUID(str(entry["id"]))
            except Exception:
                pass

        timestamp = entry.get("timestamp") or datetime.now(timezone.utc)
        sev = entry.get("severity")
        severity_val = sev.value.lower() if hasattr(sev, "value") else str(sev).lower()
        cat = entry.get("category")
        category_val = cat.value.lower() if hasattr(cat, "value") else str(cat).lower()

        db_log = InfrastructureLog(
            id=log_id,
            timestamp=timestamp,
            severity=severity_val,
            category=category_val,
            event_type=str(entry.get("event_type")),
            source=str(entry.get("source")),
            message=str(entry.get("message")),
            anon_id=entry.get("anon_id"),
            cluster_or_subnet=entry.get("cluster_or_subnet"),
            metadata_json=entry.get("metadata") or {},
        )
        self.db.add(db_log)
        self.db.commit()
        self.db.refresh(db_log)

        # อัปเดต security counters หากเป็น security violation
        event_type_str = str(entry.get("event_type", "")).upper()
        if "SQUID" in event_type_str:
            self._security_counters["squid_egress_drops"] += 1
            self._security_counters["last_violation_timestamp"] = timestamp
        elif "KYVERNO" in event_type_str or "OPA" in event_type_str:
            self._security_counters["kyverno_policy_blocks"] += 1
            self._security_counters["last_violation_timestamp"] = timestamp
        elif "TAILSCALE" in event_type_str:
            self._security_counters["tailscale_cross_cluster_attempts"] += 1
            self._security_counters["last_violation_timestamp"] = timestamp

        return db_log

    def add_log_entry(self, entry: dict[str, Any]) -> None:
        """บันทึก Log Entry ใหม่"""
        if "id" not in entry:
            entry["id"] = f"log-{uuid4().hex[:8]}"
        if "timestamp" not in entry:
            entry["timestamp"] = datetime.now(timezone.utc)
        self._infrastructure_logs.append(entry)

