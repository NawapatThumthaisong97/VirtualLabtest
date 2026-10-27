"""
Admin Monitor Service
ข้อมูลจริงของการ์ดหน้า admin overview (docs/ADMIN_MONITOR.md) — ไม่มีค่าตั้งต้นหรือ mock
ต่อ K3s ไม่ได้ = cluster down + ไม่มีห้อง ไม่เดาตัวเลขแทน

ห้อง = label vlab/room บน worker (ansible role k3s-agent ใส่ให้จาก vlab_room ใน inventory)
คอม 1 เครื่องในห้อง = 1 worker node
"""
from collections import Counter
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from app.configs.settings import settings
from app.models.class_slot import ClassSlot
from app.models.courses import Course
from app.models.session import Session as SessionModel, SessionStatus
from app.schemas.admin_monitor_schema import (
    ClusterMapItem,
    ControlPlane,
    InfraMapResponse,
    RoomMapItem,
    RoomSlot,
    RoomUsageItem,
    RoomUsageResponse,
)
from app.services.prewarm_service import CONTROL_PLANE_LABEL
from app.utils.logger import logger

ROOM_LABEL = "vlab/room"
UNASSIGNED_ROOM = "unassigned"
K3S_CLUSTER_ID = "k3s-main"


def _is_ready(node) -> bool:
    return any(c.type == "Ready" and c.status == "True" for c in (node.status.conditions or []))


def _room_status(total: int, ready: int) -> str:
    if ready == 0:
        return "down"
    return "ok" if ready == total else "warn"


class AdminMonitorService:
    def __init__(self, db: DbSession, k8s=None):
        self.db = db
        self.k8s = k8s  # KubernetesService หรือ None (ต่อ K3s ไม่ได้)

    def _list_nodes(self) -> Optional[list]:
        if self.k8s is None:
            return None
        try:
            return self.k8s.v1.list_node().items
        except Exception as e:
            logger.warning(f"[admin monitor] cannot list nodes: {e}")
            return None

    def _nodes_in_use(self) -> Counter:
        """ชื่อ node -> จำนวน session บนเครื่องแลปที่ RUNNING"""
        rows = (
            self.db.query(SessionModel.node_name)
            .filter(
                SessionModel.status == SessionStatus.RUNNING,
                SessionModel.is_cloud.is_(False),
                SessionModel.node_name.isnot(None),
                SessionModel.deleted_at.is_(None),
            )
            .all()
        )
        return Counter(r.node_name for r in rows)

    def _rooms(self, nodes: list, in_use: Counter) -> list[RoomMapItem]:
        groups: dict[str, list] = {}
        for node in nodes:
            labels = node.metadata.labels or {}
            if CONTROL_PLANE_LABEL in labels:
                continue
            groups.setdefault(labels.get(ROOM_LABEL) or UNASSIGNED_ROOM, []).append(node)

        rooms = []
        for room, members in groups.items():
            ready = sum(1 for n in members if _is_ready(n))
            rooms.append(RoomMapItem(
                room=room,
                status=_room_status(len(members), ready),
                pcs_total=len(members),
                pcs_ready=ready,
                pcs_in_use=sum(1 for n in members if in_use[n.metadata.name] > 0),
                nodes=sorted(n.metadata.name for n in members),
            ))
        # unassigned ไว้ท้ายสุด
        return sorted(rooms, key=lambda r: (r.room == UNASSIGNED_ROOM, r.room))

    def room_capacities(self) -> Optional[dict[str, int]]:
        """ห้อง → จำนวนเครื่อง (ไม่นับ unassigned) ต่อ K3s ไม่ได้ = None (จองห้องข้ามการเช็กจำนวนเครื่อง)"""
        nodes = self._list_nodes()
        if nodes is None:
            return None
        return {r.room: r.pcs_total for r in self._rooms(nodes, Counter()) if r.room != UNASSIGNED_ROOM}

    def get_infra_map(self) -> InfraMapResponse:
        nodes = self._list_nodes()
        if nodes is None:
            k3s = ClusterMapItem(id=K3S_CLUSTER_ID, type="k3s", status="down", control_plane=None, rooms=[])
        else:
            cp = next((n for n in nodes if CONTROL_PLANE_LABEL in (n.metadata.labels or {})), None)
            cp_ready = cp is not None and _is_ready(cp)
            rooms = self._rooms(nodes, self._nodes_in_use())
            if not cp_ready:
                status = "down"
            elif any(r.status != "ok" for r in rooms):
                status = "warn"
            else:
                status = "ok"
            k3s = ClusterMapItem(
                id=K3S_CLUSTER_ID, type="k3s", status=status,
                control_plane=ControlPlane(node=cp.metadata.name if cp else None, ready=cp_ready),
                rooms=rooms,
            )

        aws_running = (
            self.db.query(SessionModel)
            .filter(
                SessionModel.is_cloud.is_(True),
                SessionModel.status.in_([SessionStatus.RUNNING, SessionStatus.PENDING]),
                SessionModel.deleted_at.is_(None),
            )
            .count()
        )
        aws = ClusterMapItem(id="aws", type="cloud", status="unknown",
                             region=settings.AWS_REGION, instances_running=aws_running)
        return InfraMapResponse(clusters=[k3s, aws])

    def _room_slot(self, node_names: list[str]) -> Optional[RoomSlot]:
        """คาบที่คนในห้องนี้ใช้มากที่สุด (ห้องเดียวอาจมีคนเปิด lab นอกคาบปนอยู่)"""
        rows = (
            self.db.query(SessionModel.class_slot_id)
            .filter(
                SessionModel.status == SessionStatus.RUNNING,
                SessionModel.node_name.in_(node_names),
                SessionModel.class_slot_id.isnot(None),
                SessionModel.deleted_at.is_(None),
            )
            .all()
        )
        if not rows:
            return None
        slot_id, _ = Counter(r.class_slot_id for r in rows).most_common(1)[0]
        found = (
            self.db.query(ClassSlot, Course)
            .join(Course, ClassSlot.course_id == Course.id)
            .filter(ClassSlot.id == slot_id)
            .first()
        )
        if found is None:
            return None
        slot, course = found
        return RoomSlot(course=course.name, starts_at=slot.starts_at, ends_at=slot.ends_at,
                        status=slot.status.value)

    def get_rooms_usage(self) -> RoomUsageResponse:
        nodes = self._list_nodes()
        if nodes is None:
            return RoomUsageResponse(rooms=[])
        items = []
        for room in self._rooms(nodes, self._nodes_in_use()):
            items.append(RoomUsageItem(
                room=room.room,
                pcs_in_use=room.pcs_in_use,
                pcs_total=room.pcs_total,
                state="launched" if room.pcs_in_use > 0 else "idle",
                slot=self._room_slot(room.nodes) if room.pcs_in_use > 0 else None,
            ))
        return RoomUsageResponse(rooms=items)
