"""
FakeSky — ตัวแทน module `sky` ตอนเทส (ไม่สร้าง cluster จริง ไม่ต่อ SkyPilot API server)
FakeK8s สำหรับเทส prewarm อยู่ท้ายไฟล์

ใช้คู่กับ monkeypatch.setattr(session_service, "sky", fake) โค้ดจริงเรียก sky.launch / sky.down
เหมือนเดิม แต่ได้คำตอบตามที่เทสตั้งไว้ และ FakeSky จดไว้ว่าถูกเรียกอะไรบ้าง

ของจริงคืน request_id แล้วต้อง sky.get(...) อีกที ที่นี่จำลองด้วย FakeRequest ที่ถือค่าหรือ
exception ไว้ให้ get คืน / raise
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as _ns

import sky
from kubernetes.client.rest import ApiException
from sky.exceptions import ClusterDoesNotExist


class FakeRequest:
    def __init__(self, value=None, exc=None):
        self.value = value
        self.exc = exc


class FakeSky:
    # ของพวกนี้ใช้ของจริงได้ ไม่ต้องต่ออะไร
    Task = sky.Task
    StatusRefreshMode = sky.StatusRefreshMode
    ClusterStatus = sky.ClusterStatus

    def __init__(self):
        # สถานะของโลกจำลอง: cluster ที่ "มีอยู่" ตอนนี้ (ชื่อ -> ClusterStatus)
        self.clusters: dict[str, sky.ClusterStatus] = {}

        # ปุ่มให้เทสตั้งพฤติกรรม
        self.launch_error: Exception | None = None
        self.job_statuses: list[str] = ["RUNNING"]  # คืนตามลำดับ ตัวสุดท้ายคืนซ้ำ
        self.endpoints_map = {"8080": "10.0.0.5:8080"}
        self.status_error: Exception | None = None
        self.down_error: Exception | None = None
        self.log_tail = "setup failed: no-such-tag\n"

        # สิ่งที่ถูกเรียก ให้เทส assert
        self.launched: list[tuple[str, sky.Task]] = []
        self.downed: list[str] = []
        self.status_calls: list[tuple[list[str], object]] = []
        self.tailed: list[tuple[str, int]] = []
        self._next_job_id = 1

    def get(self, request: FakeRequest):
        if request.exc is not None:
            raise request.exc
        return request.value

    def launch(self, task, cluster_name):
        self.launched.append((cluster_name, task))
        if self.launch_error is not None:
            return FakeRequest(exc=self.launch_error)
        self.clusters[cluster_name] = sky.ClusterStatus.UP
        job_id, self._next_job_id = self._next_job_id, self._next_job_id + 1
        return FakeRequest(value=(job_id, object()))

    def stream_and_get(self, request):
        return self.get(request)

    def job_status(self, cluster_name, job_ids):
        status = self.job_statuses.pop(0) if len(self.job_statuses) > 1 else self.job_statuses[0]
        return FakeRequest(value={job_ids[0]: status})

    def endpoints(self, cluster):
        return FakeRequest(value=dict(self.endpoints_map))

    def status(self, cluster_names=None, refresh=None):
        names = list(cluster_names or [])
        self.status_calls.append((names, refresh))
        if self.status_error is not None:
            return FakeRequest(exc=self.status_error)
        # ของจริงคืน object ที่อ่านแบบ dict ได้ (.get('name') / .get('status'))
        return FakeRequest(value=[
            {"name": n, "status": self.clusters[n]} for n in names if n in self.clusters
        ])

    def down(self, cluster_name):
        self.downed.append(cluster_name)
        if self.down_error is not None:
            return FakeRequest(exc=self.down_error)
        if cluster_name not in self.clusters:
            return FakeRequest(exc=ClusterDoesNotExist(cluster_name))
        del self.clusters[cluster_name]
        return FakeRequest(value=None)

    def tail_logs(self, cluster_name, job_id, follow, tail=0, output_stream=None):
        self.tailed.append((cluster_name, job_id))
        output_stream.write(self.log_tail)
        return 0


# ---------------------------------------------------------------- Kubernetes

def _match(labels: dict, selector: str | None) -> bool:
    """label selector แบบ k=v,k=v (เท่าที่โค้ดเราใช้)"""
    if not selector:
        return True
    return all((labels or {}).get(k) == v for k, v in (part.split("=", 1) for part in selector.split(",")))


class FakeK8s:
    """ตัวแทน KubernetesService (.v1 / .apps_v1) ตอนเทส prewarm / warm pod ไม่ต่อ cluster จริง

    เก็บ DaemonSet ที่สร้างไว้ใน dict ส่วน pod / node ให้เทสใส่เองผ่าน add_pod / add_warm_pod / add_node
    object ที่คืนเป็น SimpleNamespace ที่มี attribute ชื่อเดียวกับของ kubernetes client
    """

    def __init__(self):
        self.daemonsets: dict[str, dict] = {}   # ชื่อ -> manifest
        self.ds_status: dict[str, tuple[int, int]] = {}  # ชื่อ -> (desired, ready)
        self.ds_delete_policy: dict[str, str] = {}  # ชื่อ -> propagation_policy ตอนลบ
        self.pods: list = []
        self.nodes: list = []
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.deleted_pods: list[str] = []
        self.error: Exception | None = None  # ตั้งไว้ = ทุกคำสั่ง raise (จำลอง K3s ล่ม)
        self.patch_conflict = False          # ตั้งไว้ = patch pod ได้ 409 (มีคนแย่งไปก่อน)
        self._rv = 0
        self.v1 = self
        self.apps_v1 = self

    def _check(self):
        if self.error is not None:
            raise self.error

    # ---- ตั้งโลก
    def add_node(self, name, control_plane=False, ready=True, not_ready_for=timedelta(days=1), ip=None):
        """not_ready_for = หลุดมานานแค่ไหน (ใช้เมื่อ ready=False) ค่าเริ่มต้น 1 วัน = ปิดเครื่องไปแล้ว"""
        labels = {"node-role.kubernetes.io/control-plane": "true"} if control_plane else {}
        since = datetime.now(timezone.utc) - (not_ready_for if not ready else timedelta(days=30))
        condition = _ns(type="Ready", status="True" if ready else "Unknown", last_transition_time=since)
        addresses = [_ns(type="InternalIP", address=ip), _ns(type="Hostname", address=name)] if ip else []
        self.nodes.append(_ns(metadata=_ns(name=name, labels=labels),
                              status=_ns(conditions=[condition], addresses=addresses)))

    def add_pod(self, ds_name, node, running_after=None, waiting=None, terminated=None):
        """pod ของ DaemonSet pre-pull: running_after = วินาทีจากสร้าง pod ถึง container ขึ้น / waiting = reason"""
        created = datetime(2026, 10, 17, 7, 0, tzinfo=timezone.utc)
        state = _ns(running=None, waiting=None, terminated=None)
        if running_after is not None:
            state.running = _ns(started_at=created + timedelta(seconds=running_after))
        if waiting is not None:
            state.waiting = _ns(reason=waiting)
        if terminated is not None:
            state.terminated = _ns(reason=terminated)
        has_status = running_after is not None or waiting or terminated
        self.pods.append(_ns(
            metadata=_ns(name=f"{ds_name}-{len(self.pods)}", labels={"vlab/prewarm": "true", "vlab/prewarm-ds": ds_name},
                         annotations={}, creation_timestamp=created, deletion_timestamp=None,
                         resource_version="1"),
            spec=_ns(node_name=node),
            status=_ns(phase="Running", conditions=[], container_statuses=[_ns(state=state)] if has_status else None),
        ))

    def add_warm_pod(self, ds_name, node, lab_image_id, state="free", ready=True, phase="Running",
                     session_id=None):
        """pod ของ DaemonSet warm pod คืน pod ที่สร้าง (ชื่อ <ds>-<node>)"""
        self._rv += 1
        annotations = {"vlab/lab-image-id": str(lab_image_id)}
        if session_id:
            annotations["vlab/session-id"] = str(session_id)
        pod = _ns(
            metadata=_ns(name=f"{ds_name}-{node}", labels={"vlab/warm": "true", "vlab/warm-ds": ds_name,
                                                          "vlab/warm-state": state},
                         annotations=annotations, creation_timestamp=None, deletion_timestamp=None,
                         resource_version=str(self._rv)),
            spec=_ns(node_name=node),
            status=_ns(phase=phase, conditions=[_ns(type="Ready", status="True" if ready else "False")],
                       container_statuses=None),
        )
        self.pods.append(pod)
        return pod

    def pod(self, name):
        return next((p for p in self.pods if p.metadata.name == name), None)

    # ---- AppsV1Api
    def create_namespaced_daemon_set(self, namespace, body):
        self._check()
        name = body["metadata"]["name"]
        if name in self.daemonsets:
            raise ApiException(status=409, reason="AlreadyExists")
        self.daemonsets[name] = body
        self.created.append(name)

    def delete_namespaced_daemon_set(self, name, namespace, propagation_policy=None):
        self._check()
        self.deleted.append(name)
        self.ds_delete_policy[name] = propagation_policy
        if self.daemonsets.pop(name, None) is None:
            raise ApiException(status=404, reason="NotFound")

    def list_namespaced_daemon_set(self, namespace, label_selector=None):
        self._check()
        items = []
        for name, body in self.daemonsets.items():
            if not _match(body["metadata"].get("labels"), label_selector):
                continue
            desired, ready = self.ds_status.get(name, (0, 0))
            items.append(_ns(
                metadata=_ns(name=name, annotations=body["metadata"].get("annotations"),
                             creation_timestamp=None),
                status=_ns(desired_number_scheduled=desired, number_ready=ready),
            ))
        return _ns(items=items)

    # ---- CoreV1Api
    def list_namespaced_pod(self, namespace, label_selector=None, field_selector=None):
        self._check()
        node = field_selector.split("=", 1)[1] if field_selector else None
        return _ns(items=[p for p in self.pods if _match(p.metadata.labels, label_selector)
                          and (node is None or p.spec.node_name == node)])

    def read_namespaced_pod(self, name, namespace):
        self._check()
        pod = self.pod(name)
        if pod is None:
            raise ApiException(status=404, reason="NotFound")
        return pod

    def patch_namespaced_pod(self, name, namespace, body):
        self._check()
        pod = self.pod(name)
        if pod is None:
            raise ApiException(status=404, reason="NotFound")
        rv = body["metadata"].get("resourceVersion")
        if self.patch_conflict or (rv is not None and rv != pod.metadata.resource_version):
            raise ApiException(status=409, reason="Conflict")
        pod.metadata.labels.update(body["metadata"].get("labels", {}))
        pod.metadata.annotations.update(body["metadata"].get("annotations", {}))
        self._rv += 1
        pod.metadata.resource_version = str(self._rv)
        return pod

    def delete_namespaced_pod(self, name, namespace):
        self._check()
        self.deleted_pods.append(name)
        pod = self.pod(name)
        if pod is None:
            raise ApiException(status=404, reason="NotFound")
        self.pods.remove(pod)

    def list_node(self):
        self._check()
        return _ns(items=list(self.nodes))
