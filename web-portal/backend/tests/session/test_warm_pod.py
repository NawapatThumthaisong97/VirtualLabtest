"""
กลุ่ม 5: warm pod — กด Start จากเครื่องแลปที่มี pod รอไว้ ได้ pod นั้นทันทีแทนการ launch ผ่าน SkyPilot
"""
from datetime import timedelta

import pytest
from kubernetes.client.rest import ApiException

from app.configs.settings import settings
from app.exceptions.domain import SessionAlreadyExistsError
from app.models.session import SessionEndReason, SessionStatus
from app.services import session_service
from app.services.warm_pod_service import WarmPodService, warm_daemonset_name
from tests.fakes import FakeK8s
from tests.session.conftest import sessions_of

MASTER_IP = "100.125.244.48"
PETE_IP = "100.83.96.97"
THINKPAD_IP = "100.93.121.17"
OUTSIDE_IP = "100.64.0.99"


@pytest.fixture
def k8s(monkeypatch):
    fake = FakeK8s()
    fake.add_node("master", control_plane=True, ip=MASTER_IP)
    fake.add_node("worker-pete", ip=PETE_IP)
    fake.add_node("thinkpad", ip=THINKPAD_IP)
    monkeypatch.setattr(settings, "WARM_POD_ENABLED", True)
    monkeypatch.setattr(session_service, "get_warm_pod_service", lambda: WarmPodService(fake, "default"))
    return fake


@pytest.fixture
def warm_pod(k8s, world):
    """warm pod ว่างของ lab K3s บน worker-pete"""
    return k8s.add_warm_pod(warm_daemonset_name(world.k8s_image), "worker-pete", world.k8s_image.id)


class TestWarmLaunch:
    """Launch from a lab machine with a warm pod"""

    def test_claims_pod_on_own_machine(self, svc, db, world, fake_sky, k8s, warm_pod):
        """Request from worker-pete gets its warm pod: RUNNING right away, no SkyPilot"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert result["launch_mode"] == "warm_pod"
        assert (result["cluster_name"], result["node_name"]) == (None, "worker-pete")
        assert result["endpoints"] == {"8080": f"http://{PETE_IP}:8080", "5173": f"http://{PETE_IP}:5173",
                                       "8443": f"http://{PETE_IP}:8443"}
        assert fake_sky.launched == []

        [s] = sessions_of(db, world.user)
        assert (s.status, s.k8s_pod_name, s.node_name, s.sky_cluster_name) == (
            SessionStatus.RUNNING, warm_pod.metadata.name, "worker-pete", None)
        assert s.expires_at - s.started_at == timedelta(minutes=60)
        assert warm_pod.metadata.labels["vlab/warm-state"] == "claimed"
        assert warm_pod.metadata.annotations["vlab/session-id"] == str(s.id)

    @pytest.mark.parametrize("ip", [OUTSIDE_IP, MASTER_IP, None],
                             ids=["not a cluster node", "control-plane", "no client ip"])
    def test_not_a_lab_machine(self, svc, world, fake_sky, k8s, warm_pod, ip):
        """Request not from a worker falls back to SkyPilot"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=ip)

        assert result["launch_mode"] == "skypilot"
        assert len(fake_sky.launched) == 1
        assert warm_pod.metadata.labels["vlab/warm-state"] == "free"

    def test_pod_on_other_machine_not_used(self, svc, world, fake_sky, k8s, warm_pod):
        """Warm pod on worker-pete is not given to someone sitting at thinkpad"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=THINKPAD_IP)

        assert result["launch_mode"] == "skypilot"
        assert warm_pod.metadata.labels["vlab/warm-state"] == "free"

    @pytest.mark.parametrize("case", ["claimed", "not ready", "pending", "other lab image"])
    def test_no_usable_pod(self, svc, world, fake_sky, k8s, case):
        """Claimed / not ready / pending / other image pod is not used"""
        kwargs = {"claimed": dict(state="claimed"), "not ready": dict(ready=False),
                  "pending": dict(phase="Pending"), "other lab image": {}}[case]
        image_id = world.aws_image.id if case == "other lab image" else world.k8s_image.id
        k8s.add_warm_pod(warm_daemonset_name(world.k8s_image), "worker-pete", image_id, **kwargs)

        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert result["launch_mode"] == "skypilot"

    def test_node_not_ready(self, svc, world, fake_sky, k8s):
        """NotReady machine is not trusted even if the IP matches"""
        k8s.nodes = []
        k8s.add_node("worker-pete", ready=False, ip=PETE_IP)
        k8s.add_warm_pod(warm_daemonset_name(world.k8s_image), "worker-pete", world.k8s_image.id)

        assert svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)["launch_mode"] == "skypilot"

    def test_claim_conflict(self, svc, world, fake_sky, k8s, warm_pod):
        """Someone else claimed the pod first (409): fall back to SkyPilot, no double use"""
        k8s.patch_conflict = True

        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        assert result["launch_mode"] == "skypilot"

    def test_k3s_down(self, svc, world, fake_sky, k8s, warm_pod):
        """K3s API unreachable: still launches through SkyPilot"""
        k8s.error = ApiException(status=503, reason="Service Unavailable")

        assert svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)["launch_mode"] == "skypilot"

    def test_disabled(self, svc, world, fake_sky, k8s, warm_pod, monkeypatch):
        """WARM_POD_ENABLED=false: never uses warm pods"""
        monkeypatch.setattr(settings, "WARM_POD_ENABLED", False)

        assert svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)["launch_mode"] == "skypilot"
        assert warm_pod.metadata.labels["vlab/warm-state"] == "free"

    def test_aws_lab_ignores_warm_pod(self, svc, world, fake_sky, k8s, warm_pod):
        """AWS lab never uses K3s warm pods"""
        result = svc.create_session(world.user.id, world.aws_lab.id, client_ip=PETE_IP)

        assert result["launch_mode"] == "skypilot"
        assert warm_pod.metadata.labels["vlab/warm-state"] == "free"


class TestWarmDuplicateStart:
    """Start again while a warm session exists"""

    def test_running_warm_session_409(self, svc, world, fake_sky, k8s, warm_pod):
        """Warm session still has its pod: 409"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        with pytest.raises(SessionAlreadyExistsError):
            svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

    def test_pod_gone_allows_new_start(self, svc, db, world, fake_sky, k8s, warm_pod):
        """Warm pod disappeared: old session closed (LOST), new one starts"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        k8s.pods.clear()

        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        old, new = sessions_of(db, world.user)
        assert (old.status, old.end_reason) == (SessionStatus.STOPPED, SessionEndReason.LOST)
        assert new.status == SessionStatus.RUNNING


class TestWarmDeleteAndReconcile:
    """Delete / reconcile warm sessions"""

    def test_delete_removes_pod(self, svc, db, world, fake_sky, k8s, warm_pod):
        """DELETE removes the pod (DaemonSet makes a fresh one) and never calls sky.down"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)

        out = svc.delete_session(result["session_id"])

        assert out["cluster_stopped"] is True
        assert k8s.deleted_pods == [warm_pod.metadata.name]
        assert fake_sky.downed == []
        [s] = sessions_of(db, world.user)
        assert (s.status, s.end_reason) == (SessionStatus.STOPPED, SessionEndReason.USER_DELETE)

    def test_reconcile_expired(self, svc, db, world, fake_sky, k8s, warm_pod):
        """Past expires_at: reconciler deletes the pod and marks EXPIRED (no SkyPilot autostop)"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        [s] = sessions_of(db, world.user)
        s.expires_at = s.started_at - timedelta(minutes=1)
        db.commit()

        out = svc.reconcile_sessions()

        db.refresh(s)
        assert (s.status, s.end_reason) == (SessionStatus.STOPPED, SessionEndReason.EXPIRED)
        assert k8s.deleted_pods == [warm_pod.metadata.name]
        assert out["stopped"] == [warm_pod.metadata.name]
        assert fake_sky.status_calls == []  # ไม่มี cluster ของ SkyPilot ให้ถาม

    def test_reconcile_pod_gone(self, svc, db, world, fake_sky, k8s, warm_pod):
        """Pod gone before expires_at: LOST"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        k8s.pods.clear()

        svc.reconcile_sessions()

        [s] = sessions_of(db, world.user)
        assert (s.status, s.end_reason) == (SessionStatus.STOPPED, SessionEndReason.LOST)

    def test_reconcile_k3s_down(self, svc, db, world, fake_sky, k8s, warm_pod):
        """K3s unreachable: warm sessions are not touched"""
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        k8s.error = ApiException(status=503, reason="Service Unavailable")

        svc.reconcile_sessions()

        [s] = sessions_of(db, world.user)
        assert s.status == SessionStatus.RUNNING

    def test_seed_pod_name_untouched(self, svc, db, fake_sky, k8s, add_session):
        """Seed session with a non-warm k8s_pod_name (lab-se301-sophia) is left alone"""
        s = add_session(SessionStatus.RUNNING, cluster=None)
        s.k8s_pod_name = "lab-se301-sophia"
        db.commit()

        svc.reconcile_sessions()

        db.refresh(s)
        assert s.status == SessionStatus.RUNNING
        assert k8s.deleted_pods == []
