"""
FakeSky — ตัวแทน module `sky` ตอนเทส (ไม่สร้าง cluster จริง ไม่ต่อ SkyPilot API server)

ใช้คู่กับ monkeypatch.setattr(session_service, "sky", fake) โค้ดจริงเรียก sky.launch / sky.down
เหมือนเดิม แต่ได้คำตอบตามที่เทสตั้งไว้ และ FakeSky จดไว้ว่าถูกเรียกอะไรบ้าง

ของจริงคืน request_id แล้วต้อง sky.get(...) อีกที ที่นี่จำลองด้วย FakeRequest ที่ถือค่าหรือ
exception ไว้ให้ get คืน / raise
"""
import sky
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
