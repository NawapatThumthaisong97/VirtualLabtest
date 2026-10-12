"""
กลุ่ม 1: ตัวสร้าง SkyPilot task (create_fastapi_task) และชื่อ cluster

ไม่ต่อ DB ไม่เรียก cluster ใช้ sky.Task.from_yaml_config ตรวจว่า SkyPilot รับ config ได้จริง
เคสที่มี "regression" ในชื่อคือบั๊กที่เคยเจอตอนเทสกับ cluster / AWS จริง
"""
import shlex

import pytest
import sky
from sky.utils import common_utils

from app.exceptions.domain import ClusterOperationError
from app.models.lab import RunTarget
from app.configs.settings import settings
from tests.conftest import AMI, ECR_HOST, REGISTRY


def build(service, image, target=RunTarget.KUBERNETES):
    return service.create_fastapi_task(image, "music-lab-1", env="staging", run_target=target)


def docker_run_argv(task: dict) -> list[str]:
    """แยก run: ของ AWS กลับเป็น argument แบบที่ shell จะเห็น"""
    return shlex.split(task["run"])


# ---------------------------------------------------------------- K3s

class TestK8sTask:
    def test_normal_lab(self, service, make_image):
        task = build(service, make_image())

        assert task["name"] == "music-lab-1"
        assert task["resources"] == {
            "infra": "kubernetes",
            "cpus": "2+",
            "memory": "4+",
            "disk_size": 50,
            "image_id": f"docker:{REGISTRY}/skypilot/music-lab:lab-01",
            "ports": [8080, 5173, 8443],
            "autostop": {"idle_minutes": 60, "down": True, "wait_for": "none"},
        }
        assert task["envs"] == {"IDE_PASSWORD": "musiclab", "APP_ENV": "staging"}
        assert task["run"] == "/bin/bash /run.sh"
        assert "workdir" not in task
        sky.Task.from_yaml_config(task)

    def test_no_ports_means_no_ports_key(self, service, make_image):
        task = build(service, make_image(exposed_ports=[]))
        assert "ports" not in task["resources"]

    def test_lifespan_becomes_autostop(self, service, make_image):
        task = build(service, make_image(lifespan_minutes=15))
        assert task["resources"]["autostop"]["idle_minutes"] == 15

    def test_workdir(self, service, make_image):
        assert build(service, make_image(workdir="/app"))["workdir"] == "/app"

    def test_regression_env_with_yaml_special_chars(self, service, make_image):
        """เดิมต่อ YAML ด้วย f-string ค่าที่มี ':' หรือ '#' ทำให้ YAML พัง"""
        task = build(service, make_image(env_vars={"A": "a: b # c", "N": 5}))

        assert task["envs"]["A"] == "a: b # c"
        assert task["envs"]["N"] == "5"
        assert sky.Task.from_yaml_config(task).envs["A"] == "a: b # c"

    def test_regression_multiline_entrypoint(self, service, make_image):
        """เดิม run: เยื้องแค่บรรทัดแรก บรรทัดที่ 2 หลุดออกจาก YAML"""
        task = build(service, make_image(entrypoint_script="echo 1\necho 2"))
        assert sky.Task.from_yaml_config(task).run == "echo 1\necho 2"

    def test_regression_does_not_mutate_orm_env_vars(self, service, make_image):
        """เดิมใส่ APP_ENV ลง dict ของ ORM ตรง ๆ ถ้า commit จะติดไปใน DB"""
        image = make_image()
        build(service, image)
        assert image.env_vars == {"IDE_PASSWORD": "musiclab"}


# ---------------------------------------------------------------- AWS

class TestAwsTask:
    @pytest.mark.parametrize("missing", ["AWS_LAB_AMI", "ECR_REGISTRY_HOST"])
    def test_not_configured(self, service, make_image, monkeypatch, missing):
        monkeypatch.setattr(settings, missing, None)
        with pytest.raises(ClusterOperationError):
            build(service, make_image(), RunTarget.AWS)

    def test_resources(self, service, make_image):
        task = build(service, make_image(), RunTarget.AWS)

        assert task["resources"] == {
            "infra": "aws/ap-southeast-1",
            "instance_type": "m7i-flex.large",
            "disk_size": 30,
            "image_id": AMI,
            "ports": [8080, 5173, 8443],
            "autostop": {"idle_minutes": 60, "down": True, "wait_for": "none"},
        }

    def test_env_goes_to_container_not_vm(self, service, make_image):
        """envs: ของ task อยู่บน VM ไม่เข้า container เลยต้องส่งเป็น -e ของ docker run"""
        task = build(service, make_image(), RunTarget.AWS)
        argv = docker_run_argv(task)

        assert "envs" not in task
        assert argv[argv.index("IDE_PASSWORD=musiclab") - 1] == "-e"
        assert "APP_ENV=staging" in argv

    def test_setup_logs_in_and_pulls_from_ecr(self, service, make_image):
        setup = build(service, make_image(), RunTarget.AWS)["setup"]

        assert f'echo "$ECR_TOKEN" | sudo docker login -u AWS --password-stdin {ECR_HOST}' in setup
        assert f"sudo docker pull {ECR_HOST}/skypilot/music-lab:lab-01" in setup

    def test_ports_and_workdir(self, service, make_image):
        argv = docker_run_argv(build(service, make_image(workdir="/app"), RunTarget.AWS))

        for port in (8080, 5173, 8443):
            assert f"{port}:{port}" in argv
        assert argv[argv.index("-w") + 1] == "/app"

    def test_quotes_special_values(self, service, make_image):
        image = make_image(env_vars={"A": "a: b # c; rm -rf /"})
        argv = docker_run_argv(build(service, image, RunTarget.AWS))
        assert "A=a: b # c; rm -rf /" in argv

    def test_regression_multiline_entrypoint_stays_in_container(self, service, make_image):
        """เดิมต่อ entrypoint ท้าย docker run ตรง ๆ บรรทัดที่ 2 ไปรันบน VM"""
        task = build(service, make_image(entrypoint_script="echo 1\necho 2"), RunTarget.AWS)
        argv = docker_run_argv(task)

        assert argv[-3:] == ["/bin/bash", "-c", "echo 1\necho 2"]
        assert argv[-4] == f"{ECR_HOST}/skypilot/music-lab:lab-01"

    def test_regression_empty_entrypoint_uses_image_entrypoint(self, service, make_image):
        """code-server ตั้ง ENTRYPOINT ไว้ ถ้าต่อคำสั่งจะกลายเป็น argument ของมันแล้วพัง"""
        task = build(service, make_image(entrypoint_script=""), RunTarget.AWS)
        assert docker_run_argv(task)[-1] == f"{ECR_HOST}/skypilot/music-lab:lab-01"

    def test_secret_is_accepted_and_not_in_envs(self, service, make_image):
        task = build(service, make_image(), RunTarget.AWS)
        sky_task = sky.Task.from_yaml_config(task, secrets_overrides=[("ECR_TOKEN", "dummy")])

        secret = sky_task.secrets["ECR_TOKEN"]
        assert secret.get_secret_value() == "dummy"
        assert "dummy" not in str(secret)  # SkyPilot เก็บเป็น SecretStr แสดงผลเป็น ***
        assert "ECR_TOKEN" not in (sky_task.envs or {})


# ---------------------------------------------------------------- ชื่อ cluster

class TestClusterName:
    @pytest.mark.parametrize("repository, prefix", [
        ("skypilot/music-lab", "music-lab-"),
        ("org/My_Lab.v2", "my-lab-v2-"),
        ("x/___", "lab-"),
        ("org/2048-game", "lab-2048-game-"),   # regression: SkyPilot ไม่รับชื่อขึ้นต้นด้วยตัวเลข
        ("music-lab", "music-lab-"),           # ไม่มี org
    ])
    def test_name_is_valid_for_skypilot(self, service, make_image, repository, prefix):
        name = service._cluster_name(make_image(repository=repository))

        assert name.startswith(prefix)
        common_utils.check_cluster_name_is_valid(name)
