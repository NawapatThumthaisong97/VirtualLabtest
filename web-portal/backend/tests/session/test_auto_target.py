"""
กลุ่ม 6: กฎเดียวทุก lab — เครื่องแลป → K8s, ที่อื่น → AWS (docs/archive/RUN_TARGET_AUTO.md, docs/archive/LAB_DIRECT_POD.md)
"""
import pytest

from app.configs.settings import settings
from app.models.lab import Lab, LabStatus, RunTarget
from app.schemas.lab_schema import LabUpdateRequest
from app.services import session_service
from app.repositories.lab_repository import LabRepository
from app.services.lab_service import LabService
from app.services.session_service import resolve_run_target
from app.services.warm_pod_service import warm_daemonset_name
from tests.session.conftest import sessions_of
from tests.session.test_warm_pod import OUTSIDE_IP, PETE_IP, k8s  # noqa: F401 (fixture)


@pytest.fixture
def auto_lab(db, world):
    """lab AUTO ใช้ image เดียวกับ lab K3s (music-lab มีทั้ง registry ในบ้านและ ECR)"""
    lab = Lab(course_id=world.course.id, title="AUTO lab", order_no=10,
              image_id=world.k8s_image.id, run_target=RunTarget.AUTO, status=LabStatus.PUBLISHED)
    db.add(lab)
    db.commit()
    return lab


def launched_cloud(fake_sky) -> str:
    [(_, task)] = fake_sky.launched
    [res] = list(task.resources)
    return str(res.cloud).lower()


class TestResolve:
    """resolve_run_target: which target is launched"""

    @pytest.mark.parametrize("node, expected", [
        (("worker-pete", PETE_IP), RunTarget.KUBERNETES),
        (None, RunTarget.AWS),
    ], ids=["lab machine", "outside"])
    def test_table(self, node, expected):
        """Picks by machine only (labs.run_target is ignored)"""
        assert resolve_run_target(node) == expected


class TestAutoLaunch:
    """AUTO lab: Start from a lab machine → K8s, from elsewhere → AWS"""

    @pytest.fixture(autouse=True)
    def isolated(self, monkeypatch):
        monkeypatch.setattr(settings, "LAB_ISOLATION_ENABLED", True)

    def test_lab_machine_gets_direct_pod(self, svc, world, fake_sky, k8s, auto_lab, monkeypatch):
        """From worker-pete, no warm pod: pod created directly on worker-pete, no SkyPilot"""
        monkeypatch.setattr(settings, "WARM_POD_ENABLED", False)

        result = svc.create_session(world.user.id, auto_lab.id, client_ip=PETE_IP)

        assert (result["launch_mode"], result["run_target"], result["node_name"]) == ("pod", "kubernetes", "worker-pete")
        assert fake_sky.launched == []

    def test_lab_machine_skypilot_switch(self, svc, db, world, fake_sky, k8s, auto_lab, monkeypatch):
        """LAB_MACHINE_LAUNCH=skypilot (backup path): SkyPilot on K8s pinned to worker-pete, no ECR token"""
        monkeypatch.setattr(settings, "WARM_POD_ENABLED", False)
        monkeypatch.setattr(settings, "LAB_MACHINE_LAUNCH", "skypilot")

        result = svc.create_session(world.user.id, auto_lab.id, client_ip=PETE_IP)

        assert result["run_target"] == "kubernetes"
        assert "kubernetes" in launched_cloud(fake_sky)
        [(_, task)] = fake_sky.launched
        [res] = list(task.resources)
        pod_config = res._cluster_config_overrides["kubernetes"]["pod_config"]
        assert pod_config["spec"]["nodeSelector"] == {"kubernetes.io/hostname": "worker-pete"}
        assert "ECR_TOKEN" not in (task.secrets or {})
        [s] = sessions_of(db, world.user)
        assert s.is_cloud is False

    def test_lab_machine_gets_warm_pod(self, svc, world, fake_sky, k8s, auto_lab):
        """From worker-pete with a free warm pod: warm pod, no SkyPilot"""
        k8s.add_warm_pod(warm_daemonset_name(world.k8s_image), "worker-pete", world.k8s_image.id)

        result = svc.create_session(world.user.id, auto_lab.id, client_ip=PETE_IP)

        assert (result["launch_mode"], result["run_target"]) == ("warm_pod", "kubernetes")
        assert fake_sky.launched == []

    @pytest.mark.parametrize("ip", [OUTSIDE_IP, None], ids=["outside ip", "no ip"])
    def test_outside_goes_aws(self, svc, db, world, fake_sky, k8s, auto_lab, ip):
        """Not a lab machine: burst to AWS with ECR token, is_cloud true"""
        result = svc.create_session(world.user.id, auto_lab.id, client_ip=ip)

        assert result["run_target"] == "aws"
        assert "aws" in launched_cloud(fake_sky)
        [(_, task)] = fake_sky.launched
        assert task.secrets["ECR_TOKEN"].get_secret_value() == "fake-ecr-token"
        [s] = sessions_of(db, world.user)
        assert s.is_cloud is True

    def test_k8s_unreachable_goes_aws(self, svc, world, fake_sky, auto_lab, monkeypatch):
        """Cannot look up the node (K3s down): AUTO falls back to AWS instead of failing"""
        def broken():
            raise RuntimeError("k3s down")
        monkeypatch.setattr(session_service, "get_warm_pod_service", broken)

        result = svc.create_session(world.user.id, auto_lab.id, client_ip=PETE_IP)

        assert result["run_target"] == "aws"

    def test_looks_up_machine_even_when_features_off(self, svc, world, fake_sky, k8s, auto_lab, monkeypatch):
        """WARM_POD / LAB_ISOLATION off: still knows it is a lab machine (SkyPilot switch: K8s, just not pinned)"""
        monkeypatch.setattr(settings, "WARM_POD_ENABLED", False)
        monkeypatch.setattr(settings, "LAB_ISOLATION_ENABLED", False)
        monkeypatch.setattr(settings, "LAB_MACHINE_LAUNCH", "skypilot")

        result = svc.create_session(world.user.id, auto_lab.id, client_ip=PETE_IP)

        assert result["run_target"] == "kubernetes"
        [(_, task)] = fake_sky.launched
        [res] = list(task.resources)
        assert not res._cluster_config_overrides

    def test_k8s_lab_from_outside_goes_aws(self, svc, world, fake_sky, k8s):
        """Lab set to KUBERNETES, started from outside: AWS like every lab (labs.run_target ignored)"""
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=OUTSIDE_IP)

        assert result["run_target"] == "aws"
        assert "aws" in launched_cloud(fake_sky)

    def test_aws_lab_from_lab_machine_gets_pod(self, svc, world, fake_sky, k8s, monkeypatch):
        """Lab set to AWS, started from a lab machine: K8s pod (labs.run_target ignored, no EC2 cost)"""
        monkeypatch.setattr(settings, "WARM_POD_ENABLED", False)

        result = svc.create_session(world.user.id, world.aws_lab.id, client_ip=PETE_IP)

        assert (result["launch_mode"], result["run_target"]) == ("pod", "kubernetes")
        assert fake_sky.launched == []


class TestLabApi:
    """Lab API can set run_target"""

    def test_update_to_auto_and_ignore_null(self, db, world):
        """PATCH run_target=auto works; explicit null keeps the current value"""
        service = LabService(db, LabRepository(db))

        lab = service.update_lab(world.k8s_lab.id, LabUpdateRequest(run_target="auto"))
        assert lab.run_target == RunTarget.AUTO

        lab = service.update_lab(world.k8s_lab.id, LabUpdateRequest(run_target=None))
        assert lab.run_target == RunTarget.AUTO
