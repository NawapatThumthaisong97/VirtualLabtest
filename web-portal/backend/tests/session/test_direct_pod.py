"""
กลุ่ม 7: pod ตรง — กดจากเครื่องแลปที่ไม่มี warm pod สร้าง pod ด้วย k8s API บนเครื่องนั้น ไม่ผ่าน SkyPilot
(docs/archive/LAB_DIRECT_POD.md)
"""
from datetime import timedelta

import pytest
from kubernetes.client.rest import ApiException

from app.configs.settings import settings
from app.exceptions.domain import ClusterOperationError, SessionAlreadyExistsError
from app.models.session import SessionEndReason, SessionStatus
from app.services import session_service
from app.services.warm_pod_service import build_lab_pod, warm_daemonset_name
from tests.session.conftest import sessions_of
from tests.session.test_warm_pod import OUTSIDE_IP, PETE_IP, k8s  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def no_warm_pod(monkeypatch):
    """ไม่มีคาบ = ไม่มี warm pod (เปิดฟีเจอร์ไว้ ให้ทาง "รอ warm pod ที่กำลังขึ้น" ทำงานเหมือนของจริง)"""
    monkeypatch.setattr(settings, "WARM_POD_ENABLED", True)
    monkeypatch.setattr(settings, "LAB_ISOLATION_ENABLED", True)


class TestPodSpec:
    """build_lab_pod: same container as the warm pod, pinned to the machine"""

    def test_spec(self, world):
        """nodeSelector = machine, vlab/lab label, hostPort on 127.0.0.1, requests, env, entrypoint"""
        pod = build_lab_pod(world.k8s_image, "worker-pete", "0123456789abcdef")

        assert pod["metadata"]["name"] == "lab-pod-01234567"
        assert pod["metadata"]["labels"]["vlab/lab"] == "true"
        assert pod["metadata"]["annotations"]["vlab/lab-image-id"] == str(world.k8s_image.id)
        assert pod["spec"]["nodeSelector"] == {"kubernetes.io/hostname": "worker-pete"}
        [c] = pod["spec"]["containers"]
        assert c["image"].endswith("skypilot/music-lab:lab-01")
        assert {p["hostIP"] for p in c["ports"]} == {"127.0.0.1"}
        assert {p["hostPort"] for p in c["ports"]} == {8080, 5173, 8443}
        assert c["command"] == ["/bin/sh", "-c", "/bin/bash /run.sh"]
        assert {"name": "IDE_PASSWORD", "value": "x"} in c["env"]


class TestLaunch:
    """Start from a lab machine without a warm pod"""

    def test_pod_on_own_machine(self, svc, db, world, fake_sky, k8s):
        """Pod created on worker-pete: RUNNING, localhost endpoints, expires_at, no SkyPilot"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert (result["launch_mode"], result["run_target"], result["node_name"]) == ("pod", "kubernetes", "worker-pete")
        assert result["cluster_name"] is None
        assert result["endpoints"] == {"8080": "http://localhost:8080", "5173": "http://localhost:5173",
                                       "8443": "http://localhost:8443"}
        assert fake_sky.launched == []
        [body] = k8s.created_pods
        assert body["spec"]["nodeSelector"] == {"kubernetes.io/hostname": "worker-pete"}

        [s] = sessions_of(db, world.user)
        assert (s.status, s.k8s_pod_name, s.node_name, s.sky_cluster_name, s.is_cloud) == (
            SessionStatus.RUNNING, body["metadata"]["name"], "worker-pete", None, False)
        assert s.k8s_pod_name.startswith("lab-pod-")
        assert body["metadata"]["annotations"]["vlab/session-id"] == str(s.id)
        assert timedelta(minutes=59) < s.expires_at - s.started_at < timedelta(minutes=61)

    def test_outside_still_ec2(self, svc, world, fake_sky, k8s):
        """Not a lab machine: EC2 through SkyPilot, no pod"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=OUTSIDE_IP)

        assert (result["launch_mode"], result["run_target"]) == ("skypilot", "aws")
        assert k8s.created_pods == []

    def test_skypilot_switch(self, svc, world, fake_sky, k8s, monkeypatch):
        """LAB_MACHINE_LAUNCH=skypilot: backup path through SkyPilot, no direct pod"""
        monkeypatch.setattr(settings, "LAB_MACHINE_LAUNCH", "skypilot")

        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert (result["launch_mode"], result["run_target"]) == ("skypilot", "kubernetes")
        assert k8s.created_pods == []


class TestLaunchFailure:
    """Pod that will never come up: error, pod deleted, session FAILED, log kept"""

    @pytest.mark.parametrize("outcome, text", [
        ("unschedulable", "ไม่มีที่ว่าง"),
        ("image_pull", "ImagePullBackOff"),
        ("pending", "not ready after"),
    ], ids=["machine full", "image pull", "timeout"])
    def test_fails_cleanly(self, svc, db, world, fake_sky, k8s, caplog, outcome, text):
        """Unschedulable / ImagePullBackOff / timeout → ClusterOperationError, pod deleted, FAILED / LAUNCH_FAILED"""
        k8s.pod_outcome = outcome

        with pytest.raises(ClusterOperationError, match=text):
            svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        [body] = k8s.created_pods
        name = body["metadata"]["name"]
        assert k8s.deleted_pods == [name]
        [s] = sessions_of(db, world.user)
        assert (s.status, s.end_reason) == (SessionStatus.FAILED, SessionEndReason.LAUNCH_FAILED)
        assert f"log of {name}" in caplog.text   # เก็บ log ไว้ก่อนลบ pod
        assert fake_sky.launched == []           # เครื่องเต็มไม่ส่งไป EC2

    def test_machine_full_fails_fast(self, svc, world, fake_sky, k8s):
        """Unschedulable is known right away: no waiting until the timeout"""
        k8s.pod_outcome = "unschedulable"

        with pytest.raises(ClusterOperationError):
            svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert session_service.time.slept < settings.DIRECT_POD_READY_TIMEOUT

    def test_create_rejected(self, svc, db, world, fake_sky, k8s, monkeypatch):
        """k8s refuses to create the pod: error, session FAILED"""
        def refuse(namespace, body):
            raise ApiException(status=403, reason="Forbidden")
        monkeypatch.setattr(k8s, "create_namespaced_pod", refuse)

        with pytest.raises(ClusterOperationError, match="Forbidden"):
            svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        [s] = sessions_of(db, world.user)
        assert s.status == SessionStatus.FAILED


class TestWaitForStartingWarmPod:
    """Warm pod being recreated (previous student just closed): wait for it instead of a second pod"""

    def test_waits_then_gets_warm_pod(self, svc, world, fake_sky, k8s):
        """Starting warm pod becomes Ready while waiting: warm pod, no direct pod"""
        pod = k8s.add_warm_pod(warm_daemonset_name(world.k8s_image), "worker-pete", world.k8s_image.id, ready=False)

        def becomes_ready(clock):
            pod.status.conditions[0].status = "True"
        session_service.time.on_sleep = becomes_ready

        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert result["launch_mode"] == "warm_pod"
        assert k8s.created_pods == []

    def test_gives_up_then_direct_pod(self, svc, world, fake_sky, k8s):
        """Never becomes Ready within WARM_POD_WAIT_SECONDS: direct pod"""
        k8s.add_warm_pod(warm_daemonset_name(world.k8s_image), "worker-pete", world.k8s_image.id, ready=False)

        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert result["launch_mode"] == "pod"
        assert session_service.time.slept >= settings.WARM_POD_WAIT_SECONDS

    def test_no_starting_pod_no_wait(self, svc, world, fake_sky, k8s):
        """No warm pod at all (no class): direct pod without waiting for warm pods"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert session_service.time.slept < settings.WARM_POD_WAIT_SECONDS


class TestLifecycle:
    """Delete / reconcile / Start again — same paths as warm pod"""

    def test_delete_removes_pod(self, svc, db, world, fake_sky, k8s):
        """DELETE removes the pod, no sky.down"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        out = svc.delete_session(result["session_id"])

        assert out["cluster_stopped"] is True
        assert k8s.deleted_pods == [k8s.created_pods[0]["metadata"]["name"]]
        assert fake_sky.downed == []

    def test_reconcile_expired(self, svc, db, world, fake_sky, k8s):
        """Past expires_at: reconciler deletes the pod, EXPIRED"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        [s] = sessions_of(db, world.user)
        s.expires_at = s.started_at - timedelta(minutes=1)
        db.commit()

        svc.reconcile_sessions()

        db.refresh(s)
        assert (s.status, s.end_reason) == (SessionStatus.STOPPED, SessionEndReason.EXPIRED)
        assert k8s.deleted_pods == [s.k8s_pod_name]

    def test_reconcile_stale_pending_deletes_pod(self, svc, db, world, fake_sky, k8s):
        """PENDING left behind (backend died mid-launch): STALE_PENDING and the pod is deleted"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        [s] = sessions_of(db, world.user)
        s.status = SessionStatus.PENDING
        s.started_at = s.started_at - timedelta(hours=1)
        db.commit()

        svc.reconcile_sessions()

        db.refresh(s)
        assert (s.status, s.end_reason) == (SessionStatus.FAILED, SessionEndReason.STALE_PENDING)
        assert k8s.deleted_pods == [s.k8s_pod_name]

    def test_start_again_409(self, svc, world, fake_sky, k8s):
        """Pod still there: 409"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        with pytest.raises(SessionAlreadyExistsError):
            svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

    def test_pod_gone_allows_new_start(self, svc, db, world, fake_sky, k8s):
        """Pod disappeared: old session LOST, new pod"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        k8s.pods.clear()

        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        old, new = sessions_of(db, world.user)
        assert (old.status, old.end_reason) == (SessionStatus.STOPPED, SessionEndReason.LOST)
        assert new.status == SessionStatus.RUNNING
