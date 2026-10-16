"""
Prewarm Service
ดึง image ของ lab ลงทุก worker ล่วงหน้าด้วย DaemonSet (1 DaemonSet ต่อ 1 image)

pod ที่ node ยังไม่มี image ใช้ ~2 นาที 52 วินาทีกว่าจะขึ้น ถ้า image อยู่ใน cache แล้วเหลือ ~4 วินาที
(วัดไว้ใน script/prepull.sh) พอ pod ของ DaemonSet ขึ้นครบ containerd ของทุก node จะเก็บ layer
ไว้ ลบ DaemonSet ทิ้งแล้ว cache ก็ยังอยู่

DaemonSet ที่ระบบนี้สร้างมี label vlab/prewarm=true และเก็บ image เต็มไว้ใน annotation vlab/image
scheduler ใช้ annotation นี้เทียบว่า image ไหนมี DaemonSet แล้ว ไม่ต้องพึ่งชื่อ
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from kubernetes.client.rest import ApiException

from app.configs.settings import settings
from app.exceptions.domain import PrewarmNotFoundError

MANAGED_LABEL = "vlab/prewarm"
IMAGE_ANNOTATION = "vlab/image"
POD_LABEL = "vlab/prewarm-ds"
CONTROL_PLANE_LABEL = "node-role.kubernetes.io/control-plane"

# waiting reason ที่แปลว่า pull ไม่ผ่าน ไม่ใช่แค่ยังไม่เสร็จ
PULL_ERROR_REASONS = {"ErrImagePull", "ImagePullBackOff", "InvalidImageName",
                      "ErrImageNeverPull", "CreateContainerError"}


def daemonset_name(image: str) -> str:
    """prewarm-<repo>-<tag>-<hash> ชื่อ resource ของ k8s ต้องเป็นตัวเล็ก ตัวเลข และ '-' ไม่เกิน 63 ตัว

    ต่อ hash ของ image เต็มไว้ท้าย เพราะ repo ชื่อเดียวกันจาก registry ต่างกันต้องได้คนละชื่อ
    """
    ref = image.rsplit("@", 1)[0]
    repo, _, tag = ref.rpartition(":")
    if "/" in tag or not repo:
        # ':' ที่เจอเป็นของ port ของ registry ไม่ใช่ tag
        repo, tag = ref, "latest"
    slug = re.sub(r"[^a-z0-9-]+", "-", f"{repo.split('/')[-1]}-{tag}".lower()).strip("-")
    digest = hashlib.sha1(image.encode()).hexdigest()[:6]
    return f"prewarm-{slug[:46].rstrip('-')}-{digest}"


def build_daemonset(image: str) -> dict:
    """manifest ของ DaemonSet ที่ pull image ลงทุก worker แล้วนอนรอเฉย ๆ

    container ใช้ image ตัวที่จะ pull เอง k8s ต้องดึง image มาก่อนถึงจะรันได้ ซึ่งคือสิ่งที่ต้องการ
    พอ container ขึ้น (Ready) แปลว่า node นั้น pull เสร็จแล้ว image จึงต้องมี /bin/sh กับ sleep

    ไม่ลง master (Pete ตัดสินใจ 2026-10-17) master ไม่มี taint เลยต้องกันด้วย nodeAffinity
    """
    name = daemonset_name(image)
    return {
        "apiVersion": "apps/v1",
        "kind": "DaemonSet",
        "metadata": {
            "name": name,
            "labels": {MANAGED_LABEL: "true"},
            "annotations": {IMAGE_ANNOTATION: image},
        },
        "spec": {
            "selector": {"matchLabels": {POD_LABEL: name}},
            "template": {
                "metadata": {"labels": {MANAGED_LABEL: "true", POD_LABEL: name}},
                "spec": {
                    "affinity": {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [{"matchExpressions": [
                            {"key": CONTROL_PLANE_LABEL, "operator": "DoesNotExist"},
                        ]}],
                    }}},
                    # ไม่ได้ทำงานอะไรอยู่ ลบแล้วไม่ต้องรอ
                    "terminationGracePeriodSeconds": 0,
                    "containers": [{
                        "name": "holder",
                        "image": image,
                        # tag latest ค่า default ของ k8s คือ Always จะ pull ซ้ำทุกครั้ง
                        "imagePullPolicy": "IfNotPresent",
                        # sleep infinity ใช้ไม่ได้กับ busybox บางรุ่น
                        "command": ["/bin/sh", "-c", "while true; do sleep 3600; done"],
                        "resources": {
                            "requests": {"cpu": "10m", "memory": "16Mi"},
                            "limits": {"cpu": "50m", "memory": "32Mi"},
                        },
                    }],
                },
            },
        },
    }


class PrewarmService:
    """สร้าง / ลบ / ดูสถานะ DaemonSet pre-pull ผ่าน KubernetesService (.v1, .apps_v1)"""

    def __init__(self, k8s, namespace: Optional[str] = None):
        self.v1 = k8s.v1
        self.apps_v1 = k8s.apps_v1
        self.namespace = namespace or settings.K8S_DEFAULT_NAMESPACE

    def list_managed(self) -> dict[str, str]:
        """image -> ชื่อ DaemonSet ของทุกตัวที่ระบบนี้สร้าง"""
        items = self.apps_v1.list_namespaced_daemon_set(
            self.namespace, label_selector=f"{MANAGED_LABEL}=true"
        ).items
        return {
            (ds.metadata.annotations or {}).get(IMAGE_ANNOTATION, ""): ds.metadata.name
            for ds in items
        }

    def ensure(self, image: str) -> bool:
        """สร้าง DaemonSet ของ image ถ้ายังไม่มี คืน True ถ้าสร้างใหม่

        409 = มีอยู่แล้ว (เช่น backend อีกตัวสร้างไปก่อน) ถือว่าผ่าน
        """
        try:
            self.apps_v1.create_namespaced_daemon_set(self.namespace, build_daemonset(image))
            return True
        except ApiException as e:
            if e.status == 409:
                return False
            raise

    def remove(self, name: str) -> None:
        """ลบ DaemonSet และ pod ของมัน image ที่ pull ไว้ยังอยู่บน node"""
        try:
            self.apps_v1.delete_namespaced_daemon_set(
                name, self.namespace, propagation_policy="Background"
            )
        except ApiException as e:
            if e.status != 404:
                raise

    def status(self, name: Optional[str] = None) -> list[dict[str, Any]]:
        """สถานะของทุก DaemonSet (หรือตัวเดียวถ้าให้ name) พร้อมสถานะราย worker

        worker ที่ยังไม่มี pod ของ DaemonSet ก็แสดงด้วย (state = waiting) จะได้เห็นว่าขาดเครื่องไหน
        """
        selector = f"{MANAGED_LABEL}=true"
        daemonsets = self.apps_v1.list_namespaced_daemon_set(self.namespace, label_selector=selector).items
        if name is not None:
            daemonsets = [ds for ds in daemonsets if ds.metadata.name == name]
            if not daemonsets:
                raise PrewarmNotFoundError(f"Prewarm DaemonSet {name} not found")

        pods = self.v1.list_namespaced_pod(self.namespace, label_selector=selector).items
        # worker -> (Ready ไหม, นับเป็นเครื่องที่ต้องมี image ไหม)
        # node ที่ไม่ Ready (เช่น workerfilm ปิดเครื่อง) DaemonSet จะไม่วาง pod ให้ ถ้าไม่บอกเหตุผล
        # จะดูเหมือนรอ pull อยู่ตลอด
        now = datetime.now(timezone.utc)
        workers = {
            n.metadata.name: _node_info(n, now) for n in self.v1.list_node().items
            if CONTROL_PLANE_LABEL not in (n.metadata.labels or {})
        }

        result = []
        for ds in daemonsets:
            ds_name = ds.metadata.name
            by_node = {
                p.spec.node_name: _pod_state(p) for p in pods
                if (p.metadata.labels or {}).get(POD_LABEL) == ds_name and p.spec.node_name
            }
            nodes = []
            for w, (ready, _) in sorted(workers.items()):
                node = by_node.get(w) or {"node": w, "state": "waiting",
                                          "reason": "no pod yet" if ready else "node NotReady",
                                          "pulled_in_seconds": None}
                # pod ของ node ที่หลุดยังรายงาน running ค่าเดิมค้างอยู่ ต้องดู node แยก
                nodes.append({**node, "node_ready": ready})
            # pod บน node ที่ไม่ใช่ worker ในรายการ (เช่น node เพิ่งถูกลบ) ก็แสดงไว้ด้วย
            nodes += [{**s, "node_ready": False} for n, s in by_node.items() if n not in workers]

            # ไม่ใช้ number_ready >= desired ของ DaemonSet: ตอน worker หลุด k8s ลด desired ลงตาม
            # (เทสจริง 2026-10-17 worker-pete หลุด 28 วินาที slot ยังขึ้น READY ทั้งที่เหลือ worker เดียว)
            counted = [n for n in nodes if workers.get(n["node"], (False, False))[1]]
            all_pulled = bool(counted) and all(n["node_ready"] and n["state"] == "pulled" for n in counted)

            st = ds.status
            result.append({
                "name": ds_name,
                "image": (ds.metadata.annotations or {}).get(IMAGE_ANNOTATION),
                "created_at": ds.metadata.creation_timestamp,
                "desired": (st.desired_number_scheduled or 0) if st else 0,
                "ready": (st.number_ready or 0) if st else 0,
                "all_pulled": all_pulled,
                "nodes": nodes,
            })
        return result


def _node_info(node, now: datetime) -> tuple[bool, bool]:
    """(Ready ไหม, นับเป็นเครื่องที่ต้องมี image ไหม)

    นับ = Ready อยู่ หรือเพิ่งหลุดไม่เกิน PREWARM_NODE_GRACE_MINUTES (อาจแค่เน็ตกระตุก เดี๋ยวกลับมา)
    เครื่องที่หลุดนานกว่านั้นถือว่าปิดเครื่องไปแล้ว ไม่นับ ไม่งั้นเครื่องที่ดับถาวรจะทำให้ไม่มีวันครบ
    """
    conditions = (node.status.conditions or []) if getattr(node, "status", None) else []
    cond = next((c for c in conditions if c.type == "Ready"), None)
    if cond is not None and cond.status == "True":
        return True, True
    since = getattr(cond, "last_transition_time", None) if cond is not None else None
    grace = timedelta(minutes=settings.PREWARM_NODE_GRACE_MINUTES)
    return False, since is not None and now - since <= grace


def _pod_state(pod) -> dict[str, Any]:
    """pulled = container ขึ้นแล้ว (image อยู่บน node แล้ว) / pulling / error"""
    state: dict[str, Any] = {"node": pod.spec.node_name, "state": "pulling", "reason": None,
                             "pulled_in_seconds": None}
    statuses = pod.status.container_statuses if pod.status else None
    if not statuses:
        return state
    cs = statuses[0].state
    if cs.running is not None:
        state["state"] = "pulled"
        state["pulled_in_seconds"] = _seconds_between(pod.metadata.creation_timestamp,
                                                      cs.running.started_at)
    elif cs.waiting is not None:
        state["reason"] = cs.waiting.reason
        if cs.waiting.reason in PULL_ERROR_REASONS:
            state["state"] = "error"
    elif cs.terminated is not None:
        # holder วนไม่จบ ถ้าจบแปลว่า pull ได้แต่รันไม่ได้ เช่น image ไม่มี /bin/sh
        state["state"] = "error"
        state["reason"] = cs.terminated.reason
    return state


def _seconds_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 1)
