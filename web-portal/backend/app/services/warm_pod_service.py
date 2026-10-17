"""
Warm Pod Service
pod ของ lab ที่รันรอไว้บนเครื่องในห้องแลปก่อนคาบ (1 เครื่อง = 1 pod = นักศึกษา 1 คน)

นักศึกษานั่งที่เครื่องแลปซึ่งเป็น K3s worker เอง ตอนกด Start ถ้าเครื่องที่นั่งอยู่มี warm pod ว่าง
backend แจก pod นั้นให้ทันที (ไม่กี่วินาที) ไม่ต้องรอ SkyPilot (~5 นาทีบน K3s)
ไม่มี (นั่งนอกห้องแลป / pod ยังไม่พร้อม / มีคนใช้อยู่แล้ว) → launch ผ่าน SkyPilot แบบเดิม

DaemonSet 1 ตัวต่อ 1 lab image (แยกจาก DaemonSet pre-pull ที่เป็นแค่ holder เบา ๆ เพราะตัวนี้รัน
lab จริง กิน CPU / RAM จริง) pod มี label vlab/warm-state:
- free: ยังไม่มีใครใช้
- claimed: แจกให้ session แล้ว (annotation vlab/session-id) DaemonSet ไม่สร้าง pod ใหม่บนเครื่องนี้
  เพราะ selector ไม่ได้ดู label นี้ จบ session → ลบ pod → DaemonSet สร้างตัวใหม่ที่สะอาดให้คนถัดไป
"""
import re
from typing import Any, Optional

from kubernetes.client.rest import ApiException

from app.configs.settings import settings
from app.services.prewarm_service import (CONTROL_PLANE_LABEL, IMAGE_ANNOTATION, daemonset_name,
                                          k8s_image_ref)

WARM_LABEL = "vlab/warm"
WARM_DS_LABEL = "vlab/warm-ds"
STATE_LABEL = "vlab/warm-state"
LAB_IMAGE_ANNOTATION = "vlab/lab-image-id"
SESSION_ANNOTATION = "vlab/session-id"
# pod ของ lab ทุกแบบ (warm / SkyPilot ที่บังคับลงเครื่องตัวเอง) NetworkPolicy vlab-lab-isolation เลือกด้วย label นี้
LAB_LABEL = "vlab/lab"
LOCALHOST = "127.0.0.1"

# ชื่อ pod ของ DaemonSet = <ชื่อ DaemonSet>-xxxxx reconciler / delete ใช้ prefix นี้แยก session ของ
# warm pod ออกจาก session seed ที่มี k8s_pod_name แต่ไม่ได้มาจาก launch จริง
WARM_POD_PREFIX = "warm-"


def warm_daemonset_name(lab_image) -> str:
    return daemonset_name(k8s_image_ref(lab_image), prefix="warm")


def _number(requirement: Optional[str]) -> Optional[float]:
    """"2+" / "0.5" ของ SkyPilot → ค่าขั้นต่ำ (ใช้เป็น request ของ k8s)"""
    match = re.search(r"\d+(\.\d+)?", requirement or "")
    return float(match.group(0)) if match else None


def _cpu(requirement: Optional[str]) -> Optional[str]:
    n = _number(requirement)
    return f"{int(n * 1000)}m" if n else None


def _memory(requirement_gb: Optional[str]) -> Optional[str]:
    # เป็น Mi จำนวนเต็ม "0.05Gi" k8s รับแต่เตือน fractional byte value (dry-run กับ cluster จริง)
    n = _number(requirement_gb)
    return f"{max(1, int(n * 1024))}Mi" if n else None


def lab_envs(lab_image, env: str = "staging") -> dict[str, str]:
    """env ของ lab แบบเดียวกับ SessionService._lab_envs (create_session ใช้ env="staging")"""
    envs = {k: str(v) for k, v in (lab_image.env_vars or {}).items()}
    envs["APP_ENV"] = env
    return envs


def _host_port(port: int) -> dict:
    """LAB_ISOLATION_ENABLED: ผูก hostPort กับ 127.0.0.1 เครื่องอื่นเรียกผ่าน Tailscale IP ไม่ได้
    ไม่เปิด = ผูกทุก IP ของเครื่อง (ใครอยู่ใน tailnet ก็เปิด http://<IP เครื่อง>:<port> ได้)
    """
    mapping = {"containerPort": port, "hostPort": port}
    if settings.LAB_ISOLATION_ENABLED:
        mapping["hostIP"] = LOCALHOST
    return mapping


def build_warm_daemonset(lab_image) -> dict:
    """DaemonSet ที่รัน lab จริงบนทุก worker

    พอร์ตใช้ hostPort = เปิดที่ IP ของเครื่องนั้นตรง ๆ นักศึกษาที่นั่งเครื่องนั้นเปิด http://<IP เครื่อง>:<port>
    ข้อจำกัด: 1 เครื่องมี warm pod ที่ใช้พอร์ตเดียวกันได้แค่ 1 ตัว (2 lab ที่ใช้ 8080 พร้อมกัน ตัวที่ 2 จะ Pending)
    """
    name = warm_daemonset_name(lab_image)
    image = k8s_image_ref(lab_image)
    ports = lab_image.get_skypilot_resources().get("ports") or []

    container: dict[str, Any] = {
        "name": "lab",
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "env": [{"name": k, "value": v} for k, v in lab_envs(lab_image).items()],
        "ports": [_host_port(int(p)) for p in ports],
    }
    # entrypoint ว่าง = ใช้ ENTRYPOINT / CMD ของ image เอง (แบบเดียวกับ AWS VM mode)
    # ใช้ sh ไม่ใช้ bash เพราะ image เล็ก ๆ (busybox) ไม่มี bash ส่วน "/bin/bash /run.sh" ก็ยังรันได้
    entrypoint = (lab_image.entrypoint_script or "").strip()
    if entrypoint:
        container["command"] = ["/bin/sh", "-c", entrypoint]
    if lab_image.workdir:
        container["workingDir"] = lab_image.workdir
    requests = {k: v for k, v in (("cpu", _cpu(lab_image.cpu_requirement)),
                                  ("memory", _memory(lab_image.memory_requirement))) if v}
    if requests:
        container["resources"] = {"requests": requests}

    return {
        "apiVersion": "apps/v1",
        "kind": "DaemonSet",
        "metadata": {
            "name": name,
            "labels": {WARM_LABEL: "true"},
            "annotations": {IMAGE_ANNOTATION: image, LAB_IMAGE_ANNOTATION: str(lab_image.id)},
        },
        "spec": {
            "selector": {"matchLabels": {WARM_DS_LABEL: name}},
            "template": {
                "metadata": {
                    "labels": {WARM_LABEL: "true", WARM_DS_LABEL: name, STATE_LABEL: "free",
                               LAB_LABEL: "true"},
                    "annotations": {LAB_IMAGE_ANNOTATION: str(lab_image.id)},
                },
                "spec": {
                    "affinity": {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [{"matchExpressions": [
                            {"key": CONTROL_PLANE_LABEL, "operator": "DoesNotExist"},
                        ]}],
                    }}},
                    "terminationGracePeriodSeconds": 5,
                    "containers": [container],
                },
            },
        },
    }


class WarmPodService:
    """จัดการ warm pod ผ่าน KubernetesService (.v1, .apps_v1)"""

    def __init__(self, k8s, namespace: Optional[str] = None):
        self.v1 = k8s.v1
        self.apps_v1 = k8s.apps_v1
        self.namespace = namespace or settings.K8S_DEFAULT_NAMESPACE

    # ---------------------------------------------------------------- DaemonSet (scheduler ใช้)

    def list_managed(self) -> dict[str, str]:
        """lab_image_id -> ชื่อ DaemonSet ของ warm pod ทุกตัว"""
        items = self.apps_v1.list_namespaced_daemon_set(
            self.namespace, label_selector=f"{WARM_LABEL}=true"
        ).items
        return {
            (ds.metadata.annotations or {}).get(LAB_IMAGE_ANNOTATION, ""): ds.metadata.name
            for ds in items
        }

    def ensure(self, lab_image) -> bool:
        """สร้าง DaemonSet ของ lab image ถ้ายังไม่มี คืน True ถ้าสร้างใหม่ (409 = มีแล้ว ถือว่าผ่าน)"""
        try:
            self.apps_v1.create_namespaced_daemon_set(self.namespace, build_warm_daemonset(lab_image))
            return True
        except ApiException as e:
            if e.status == 409:
                return False
            raise

    def remove(self, name: str) -> None:
        """คาบจบ: ลบ DaemonSet แต่ปล่อย pod ที่มีคนใช้อยู่ไว้ (Orphan) แล้วลบเฉพาะ pod ที่ยังว่าง

        ถ้าลบแบบปกติ pod ทุกตัวหายตาม นักศึกษาที่ยังทำ lab อยู่หลังคาบจบจะโดนตัดกลางทาง
        pod ที่ถูกปล่อยไว้จะถูกลบตอน session จบ (DELETE / reconciler ตอนถึง expires_at)
        """
        try:
            self.apps_v1.delete_namespaced_daemon_set(name, self.namespace, propagation_policy="Orphan")
        except ApiException as e:
            if e.status != 404:
                raise
        free = self.v1.list_namespaced_pod(
            self.namespace, label_selector=f"{WARM_DS_LABEL}={name},{STATE_LABEL}=free"
        ).items
        for pod in free:
            self.delete_pod(pod.metadata.name)

    # ---------------------------------------------------------------- launch / delete (session ใช้)

    def node_for_ip(self, ip: Optional[str]) -> Optional[tuple[str, str]]:
        """(ชื่อ node, IP) ของ worker ที่ Ready และมี InternalIP ตรงกับ IP ที่ request มา

        นี่คือการเช็กว่า "นั่งอยู่ที่เครื่องนั้นจริง" หน้าเว็บเรียก backend ตรง ๆ ไม่ผ่าน proxy จึงใช้
        IP ของ connection ได้ ห้ามเชื่อ header X-Forwarded-For เพราะใครก็ใส่เองได้
        """
        if not ip:
            return None
        for node in self.v1.list_node().items:
            if CONTROL_PLANE_LABEL in (node.metadata.labels or {}):
                continue
            status = node.status
            ready = any(c.type == "Ready" and c.status == "True" for c in (status.conditions or []))
            if not ready:
                continue
            for addr in status.addresses or []:
                if addr.type == "InternalIP" and addr.address == ip:
                    return node.metadata.name, addr.address
        return None

    def find_free_pod(self, node: str, lab_image_id) -> Optional[Any]:
        """warm pod ที่ว่าง พร้อมใช้ (Running + Ready) ของ lab image นี้บนเครื่องนี้"""
        pods = self.v1.list_namespaced_pod(
            self.namespace,
            label_selector=f"{WARM_LABEL}=true,{STATE_LABEL}=free",
            field_selector=f"spec.nodeName={node}",
        ).items
        for pod in pods:
            if (pod.metadata.annotations or {}).get(LAB_IMAGE_ANNOTATION) != str(lab_image_id):
                continue
            if pod.metadata.deletion_timestamp is not None or pod.status.phase != "Running":
                continue
            if any(c.type == "Ready" and c.status == "True" for c in (pod.status.conditions or [])):
                return pod
        return None

    def claim(self, pod, session_id) -> bool:
        """แจก pod ให้ session ถ้ามีคนแย่งไปก่อน (resourceVersion เปลี่ยน) k8s ตอบ 409 → คืน False

        ใส่ resourceVersion ไว้ใน patch = เงื่อนไขว่า pod ต้องยังเป็นตัวเดิมที่เห็นตอน find_free_pod
        กัน 2 request ที่มาจากเครื่องเดียวกันพร้อมกันได้ pod ตัวเดียวกัน
        """
        try:
            self.v1.patch_namespaced_pod(pod.metadata.name, self.namespace, {
                "metadata": {
                    "resourceVersion": pod.metadata.resource_version,
                    "labels": {STATE_LABEL: "claimed"},
                    "annotations": {SESSION_ANNOTATION: str(session_id)},
                },
            })
            return True
        except ApiException as e:
            if e.status == 409:
                return False
            raise

    def pod_exists(self, name: str) -> bool:
        try:
            pod = self.v1.read_namespaced_pod(name, self.namespace)
        except ApiException as e:
            if e.status == 404:
                return False
            raise
        return pod.metadata.deletion_timestamp is None

    def delete_pod(self, name: str) -> None:
        try:
            self.v1.delete_namespaced_pod(name, self.namespace)
        except ApiException as e:
            if e.status != 404:
                raise

    # ---------------------------------------------------------------- ดูสถานะ (API)

    def list_pods(self) -> list[dict[str, Any]]:
        pods = self.v1.list_namespaced_pod(self.namespace, label_selector=f"{WARM_LABEL}=true").items
        result = []
        for p in pods:
            labels, ann = p.metadata.labels or {}, p.metadata.annotations or {}
            result.append({
                "pod": p.metadata.name,
                "node": p.spec.node_name,
                "lab_image_id": ann.get(LAB_IMAGE_ANNOTATION),
                "state": labels.get(STATE_LABEL),
                "session_id": ann.get(SESSION_ANNOTATION),
                "phase": p.status.phase if p.status else None,
                "ready": any(c.type == "Ready" and c.status == "True"
                             for c in ((p.status.conditions or []) if p.status else [])),
            })
        return sorted(result, key=lambda r: (r["node"] or "", r["pod"]))


def warm_endpoints(node_ip: str, lab_image) -> dict[str, str]:
    """endpoint แบบเดียวกับของ SkyPilot ({"8080": "http://..."}) ชี้เครื่องที่นั่งอยู่ (hostPort)

    LAB_ISOLATION_ENABLED = localhost (เปิดได้แค่จากเครื่องนั้น ซึ่งคือเครื่องที่กด Start อยู่แล้ว)
    """
    host = "localhost" if settings.LAB_ISOLATION_ENABLED else node_ip
    ports = lab_image.get_skypilot_resources().get("ports") or []
    return {str(p): f"http://{host}:{p}" for p in ports}
