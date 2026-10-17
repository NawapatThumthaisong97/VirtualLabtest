"""
Prewarm: DaemonSet pre-pull + scheduler (ไม่ต่อ K3s จริง ใช้ FakeK8s)
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.configs.settings import PrewarmTarget, settings
from app.exceptions.domain import PrewarmNotFoundError
from app.services.prewarm_scheduler import sync_prewarm
from app.services.prewarm_service import PrewarmService, build_daemonset, daemonset_name
from tests.fakes import FakeK8s

HELLO_V1 = "100.127.74.48:5001/vlab/hello:v1"
HELLO_V2 = "100.127.74.48:5001/vlab/hello:v2"
NOW = datetime(2026, 10, 17, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def k8s():
    fake = FakeK8s()
    fake.add_node("master", control_plane=True)
    fake.add_node("worker-pete")
    fake.add_node("thinkpad")
    return fake


@pytest.fixture
def prewarm(k8s):
    return PrewarmService(k8s, namespace="default")


def target(image, start=timedelta(minutes=-5), end=timedelta(minutes=55)):
    return PrewarmTarget(image=image, start_at=NOW + start, end_at=NOW + end)


class TestManifest:
    """DaemonSet manifest"""

    def test_name_is_valid_k8s_name(self):
        """Name: lowercase, '-', at most 63 chars, unique per image"""
        name = daemonset_name(HELLO_V1)
        assert name.startswith("prewarm-hello-v1-")
        assert len(name) <= 63 and name == name.lower()
        assert daemonset_name(HELLO_V2) != name
        # repo เดียวกันคนละ registry ต้องไม่ชน
        assert daemonset_name("10.0.0.9:5001/vlab/hello:v1") != name

    def test_registry_port_is_not_tag(self):
        """Registry port is not mistaken for the tag"""
        assert daemonset_name("10.0.0.1:5001/vlab/hello").startswith("prewarm-hello-latest-")

    def test_long_name_is_cut(self):
        """Very long repo / tag still fits in 63 chars"""
        assert len(daemonset_name(f"r/{'x' * 80}:{'y' * 80}")) <= 63

    def test_workers_only(self):
        """Never scheduled on control-plane (master)"""
        spec = build_daemonset(HELLO_V1)["spec"]["template"]["spec"]
        expr = spec["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"][
            "nodeSelectorTerms"][0]["matchExpressions"][0]
        assert expr == {"key": "node-role.kubernetes.io/control-plane", "operator": "DoesNotExist"}
        assert "tolerations" not in spec

    def test_pulls_image_once(self):
        """Container uses the image with IfNotPresent and tiny resources"""
        manifest = build_daemonset(HELLO_V1)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert container["image"] == HELLO_V1
        assert container["imagePullPolicy"] == "IfNotPresent"
        assert container["resources"]["requests"] == {"cpu": "10m", "memory": "16Mi"}
        assert manifest["metadata"]["annotations"]["vlab/image"] == HELLO_V1
        assert manifest["metadata"]["labels"]["vlab/prewarm"] == "true"


class TestEnsureRemove:
    """Create / delete DaemonSet"""

    def test_ensure_twice(self, prewarm, k8s):
        """ensure is idempotent (409 counts as success)"""
        assert prewarm.ensure(HELLO_V1) is True
        assert prewarm.ensure(HELLO_V1) is False
        assert list(k8s.daemonsets) == [daemonset_name(HELLO_V1)]

    def test_remove_missing(self, prewarm, k8s):
        """Removing a DaemonSet that is already gone does not raise"""
        prewarm.remove("prewarm-gone")
        assert k8s.deleted == ["prewarm-gone"]

    def test_list_managed(self, prewarm):
        """list_managed maps image -> DaemonSet name"""
        prewarm.ensure(HELLO_V1)
        assert prewarm.list_managed() == {HELLO_V1: daemonset_name(HELLO_V1)}


class TestStatus:
    """Per-node status"""

    def test_per_worker_state(self, prewarm, k8s):
        """pulled / pulling / error per worker, master not listed"""
        prewarm.ensure(HELLO_V1)
        name = daemonset_name(HELLO_V1)
        k8s.ds_status[name] = (2, 1)
        k8s.add_pod(name, "worker-pete", running_after=172)
        k8s.add_pod(name, "thinkpad", waiting="ContainerCreating")

        [ds] = prewarm.status()

        assert (ds["image"], ds["desired"], ds["ready"], ds["all_pulled"]) == (HELLO_V1, 2, 1, False)
        assert ds["nodes"] == [
            {"node": "thinkpad", "state": "pulling", "reason": "ContainerCreating",
             "pulled_in_seconds": None, "node_ready": True},
            {"node": "worker-pete", "state": "pulled", "reason": None, "pulled_in_seconds": 172.0,
             "node_ready": True},
        ]

    @pytest.mark.parametrize("reason", ["ErrImagePull", "ImagePullBackOff"])
    def test_pull_error(self, prewarm, k8s, reason):
        """Image that cannot be pulled shows error with the reason"""
        prewarm.ensure(HELLO_V1)
        k8s.add_pod(daemonset_name(HELLO_V1), "worker-pete", waiting=reason)

        nodes = {n["node"]: n for n in prewarm.status()[0]["nodes"]}

        assert (nodes["worker-pete"]["state"], nodes["worker-pete"]["reason"]) == ("error", reason)

    def test_worker_without_pod(self, prewarm, k8s):
        """Worker with no pod yet shows waiting"""
        prewarm.ensure(HELLO_V1)
        k8s.add_pod(daemonset_name(HELLO_V1), "worker-pete")  # pod ยังไม่มี container status

        nodes = {n["node"]: n["state"] for n in prewarm.status()[0]["nodes"]}

        assert nodes == {"thinkpad": "waiting", "worker-pete": "pulling"}

    def test_not_ready_worker(self, prewarm, k8s):
        """NotReady worker (e.g. workerfilm) says so instead of waiting forever"""
        k8s.add_node("workerfilm", ready=False)
        prewarm.ensure(HELLO_V1)

        nodes = {n["node"]: n["reason"] for n in prewarm.status()[0]["nodes"]}

        assert nodes["workerfilm"] == "node NotReady"
        assert nodes["worker-pete"] == "no pod yet"

    def test_all_pulled(self, prewarm, k8s):
        """Every Ready worker pulled: all_pulled is true"""
        prewarm.ensure(HELLO_V1)
        for w in ("worker-pete", "thinkpad"):
            k8s.add_pod(daemonset_name(HELLO_V1), w, running_after=5)

        assert prewarm.status()[0]["all_pulled"] is True

    def test_worker_just_dropped(self, prewarm, k8s):
        """Regression: worker NotReady for a few seconds is not all_pulled even if its pod still says pulled

        เทสจริง 2026-10-17 worker-pete หลุด 28 วินาที DaemonSet ลด desired เหลือ 1 แล้ว slot ยังขึ้น READY
        """
        k8s.nodes = []
        k8s.add_node("worker-pete", ready=False, not_ready_for=timedelta(seconds=10))
        k8s.add_node("thinkpad")
        prewarm.ensure(HELLO_V1)
        name = daemonset_name(HELLO_V1)
        k8s.ds_status[name] = (1, 1)  # ตัวนับของ DaemonSet บอกว่าครบ
        for w in ("worker-pete", "thinkpad"):
            k8s.add_pod(name, w, running_after=5)  # pod ของ worker-pete ยังค้างเป็น running

        [ds] = prewarm.status()

        nodes = {n["node"]: (n["state"], n["node_ready"]) for n in ds["nodes"]}
        assert nodes["worker-pete"] == ("pulled", False)
        assert ds["all_pulled"] is False

    def test_long_dead_worker_ignored(self, prewarm, k8s):
        """Worker NotReady longer than the grace period (powered off) does not block all_pulled"""
        k8s.add_node("workerfilm", ready=False, not_ready_for=timedelta(days=48))
        prewarm.ensure(HELLO_V1)
        for w in ("worker-pete", "thinkpad"):
            k8s.add_pod(daemonset_name(HELLO_V1), w, running_after=5)

        assert prewarm.status()[0]["all_pulled"] is True

    def test_no_workers(self, prewarm, k8s):
        """No worker at all is never all_pulled"""
        k8s.nodes = []
        prewarm.ensure(HELLO_V1)

        assert prewarm.status()[0]["all_pulled"] is False

    def test_pods_of_other_daemonset_ignored(self, prewarm, k8s):
        """Each DaemonSet only counts its own pods"""
        prewarm.ensure(HELLO_V1)
        prewarm.ensure(HELLO_V2)
        k8s.add_pod(daemonset_name(HELLO_V2), "worker-pete", running_after=3)

        v1 = prewarm.status(daemonset_name(HELLO_V1))[0]

        assert {n["state"] for n in v1["nodes"]} == {"waiting"}

    def test_unknown_name(self, prewarm):
        """Unknown DaemonSet name raises not found (404)"""
        with pytest.raises(PrewarmNotFoundError):
            prewarm.status("prewarm-nope")


class TestScheduler:
    """Prewarm scheduler"""

    def test_creates_in_window(self, prewarm, k8s, monkeypatch):
        """Creates DaemonSet A and B when their window starts"""
        monkeypatch.setattr(settings, "PREWARM_TARGETS", [target(HELLO_V1), target(HELLO_V2)])

        result = sync_prewarm(prewarm, now=NOW)

        assert result == {"created": [HELLO_V1, HELLO_V2], "removed": [], "slots": {}}
        assert set(prewarm.list_managed()) == {HELLO_V1, HELLO_V2}

    def test_not_yet(self, prewarm, k8s, monkeypatch):
        """Does nothing before start_at"""
        monkeypatch.setattr(settings, "PREWARM_TARGETS", [target(HELLO_V1, start=timedelta(minutes=1))])

        assert sync_prewarm(prewarm, now=NOW) == {"created": [], "removed": [], "slots": {}}
        assert k8s.daemonsets == {}

    def test_removes_after_window(self, prewarm, k8s, monkeypatch):
        """Removes DaemonSet once end_at has passed, keeps the other"""
        prewarm.ensure(HELLO_V1)
        prewarm.ensure(HELLO_V2)
        monkeypatch.setattr(settings, "PREWARM_TARGETS", [
            target(HELLO_V1, start=timedelta(hours=-2), end=timedelta(minutes=-1)),
            target(HELLO_V2),
        ])

        result = sync_prewarm(prewarm, now=NOW)

        assert result == {"created": [], "removed": [HELLO_V1], "slots": {}}
        assert set(prewarm.list_managed()) == {HELLO_V2}

    def test_steady_state(self, prewarm, k8s, monkeypatch):
        """Second run with nothing changed does no calls"""
        monkeypatch.setattr(settings, "PREWARM_TARGETS", [target(HELLO_V1)])
        sync_prewarm(prewarm, now=NOW)

        assert sync_prewarm(prewarm, now=NOW + timedelta(minutes=1)) == {"created": [], "removed": [], "slots": {}}
        assert len(k8s.created) == 1

    def test_naive_time_rejected(self):
        """Target time without timezone is rejected"""
        with pytest.raises(ValueError):
            PrewarmTarget(image=HELLO_V1, start_at=datetime(2026, 10, 17, 14),
                          end_at=datetime(2026, 10, 17, 15))
