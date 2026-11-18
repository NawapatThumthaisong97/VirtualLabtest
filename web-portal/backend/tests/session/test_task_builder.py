"""
กลุ่ม 1: ตัวสร้าง SkyPilot task (create_fastapi_task) และชื่อ cluster

ไม่ต่อ DB ไม่เรียก cluster ใช้ sky.Task.from_yaml_config ตรวจว่า SkyPilot รับ config ได้จริง

บรรทัดแรกของ docstring ของ class / เทส = ชื่อ group / case ในตารางสรุป (conftest.py)
case ที่ขึ้นต้นด้วย "Regression:" คือบั๊กที่เคยเจอตอนเทสกับ cluster / AWS จริง
"""
import os
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import time

import pytest
import sky
from sky.utils import common_utils

from app.exceptions.domain import ClusterOperationError
from app.models.lab import RunTarget
from app.configs.settings import settings
from app.services.session_service import _aws_wait_ready_script
from tests.conftest import AMI, ECR_HOST, REGISTRY

IMAGE_REF = f"{ECR_HOST}/skypilot/music-lab:lab-01"
WAIT_MARKER = "# ---- wait for the lab to be ready"


def build(service, image, target=RunTarget.KUBERNETES):
    return service.create_fastapi_task(image, "music-lab-1", env="staging", run_target=target)


def docker_run_argv(task: dict) -> list[str]:
    """argument ของ `sudo docker run ...` ใน setup ของ AWS แบบที่ shell จะเห็น

    ตัดเอาช่วงระหว่าง "sudo docker run" ถึงสคริปต์รอ port (entrypoint หลายบรรทัดอยู่ในเครื่องหมายคำพูด
    จึงแยกตามบรรทัดตรง ๆ ไม่ได้) แล้วตัด "sudo docker run" กับ ">/dev/null" ออก
    """
    command = task["setup"].split("sudo docker run ", 1)[1].split(WAIT_MARKER, 1)[0]
    argv = shlex.split(command)
    assert argv[-1] == ">/dev/null"
    return argv[:-1]


# ---------------------------------------------------------------- K3s

class TestK8sTask:
    """K3s task"""

    def test_normal_lab(self, service, make_image):
        """Normal lab: registry image, resources, ports, envs, autostop"""
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
        """Lab without exposed ports has no ports key"""
        task = build(service, make_image(exposed_ports=[]))
        assert "ports" not in task["resources"]

    def test_lifespan_becomes_autostop(self, service, make_image):
        """lifespan_minutes becomes autostop idle_minutes"""
        task = build(service, make_image(lifespan_minutes=15))
        assert task["resources"]["autostop"]["idle_minutes"] == 15

    def test_workdir(self, service, make_image):
        """workdir is passed through"""
        assert build(service, make_image(workdir="/app"))["workdir"] == "/app"

    def test_regression_env_with_yaml_special_chars(self, service, make_image):
        """Regression: env value with ':' and '#' (e.g. 'a: b # c') stays a string

        เดิมต่อ YAML ด้วย f-string ค่าที่มี ':' หรือ '#' ทำให้ YAML พัง
        """
        task = build(service, make_image(env_vars={"A": "a: b # c", "N": 5}))

        assert task["envs"]["A"] == "a: b # c"
        assert task["envs"]["N"] == "5"
        assert sky.Task.from_yaml_config(task).envs["A"] == "a: b # c"

    def test_regression_multiline_entrypoint(self, service, make_image):
        """Regression: multi-line entrypoint keeps every line

        เดิม run: เยื้องแค่บรรทัดแรก บรรทัดที่ 2 หลุดออกจาก YAML
        """
        task = build(service, make_image(entrypoint_script="echo 1\necho 2"))
        assert sky.Task.from_yaml_config(task).run == "echo 1\necho 2"

    def test_regression_does_not_mutate_orm_env_vars(self, service, make_image):
        """Regression: building a task does not modify LabImage.env_vars

        เดิมใส่ APP_ENV ลง dict ของ ORM ตรง ๆ ถ้า commit จะติดไปใน DB
        """
        image = make_image()
        build(service, image)
        assert image.env_vars == {"IDE_PASSWORD": "musiclab"}


# ---------------------------------------------------------------- AWS

class TestAwsTask:
    """AWS task (VM mode)"""

    @pytest.mark.parametrize("missing", ["AWS_LAB_AMI", "ECR_REGISTRY_HOST"])
    def test_not_configured(self, service, make_image, monkeypatch, missing):
        """Missing AWS setting raises ClusterOperationError"""
        monkeypatch.setattr(settings, missing, None)
        with pytest.raises(ClusterOperationError):
            build(service, make_image(), RunTarget.AWS)

    def test_resources(self, service, make_image):
        """Resources: region, instance type, disk, AMI, ports, autostop"""
        task = build(service, make_image(), RunTarget.AWS)

        assert task["resources"] == {
            "infra": "aws/ap-southeast-1",
            "instance_type": "m7i-flex.large",
            "disk_size": 30,
            "image_id": AMI,
            "ports": [8080, 5173, 8443],
            "autostop": {"idle_minutes": 60, "down": True, "wait_for": "none"},
        }

    def test_autostop_override(self, service, make_image):
        """Pre-launched machine: autostop_minutes replaces lifespan (short safety net until claimed)"""
        task = service.create_fastapi_task(make_image(), "music-lab-1", run_target=RunTarget.AWS,
                                           autostop_minutes=30)
        assert task["resources"]["autostop"]["idle_minutes"] == 30

    def test_env_goes_to_container_not_vm(self, service, make_image):
        """Lab env goes to the container (docker run -e), not task envs

        envs: ของ task อยู่บน VM ไม่เข้า container
        """
        task = build(service, make_image(), RunTarget.AWS)
        argv = docker_run_argv(task)

        assert "envs" not in task
        assert argv[argv.index("IDE_PASSWORD=musiclab") - 1] == "-e"
        assert "APP_ENV=staging" in argv

    def test_setup_logs_in_and_pulls_from_ecr(self, service, make_image):
        """Setup logs in to ECR with the secret token and pulls the image"""
        setup = build(service, make_image(), RunTarget.AWS)["setup"]

        assert f'echo "$ECR_TOKEN" | sudo docker login -u AWS --password-stdin {ECR_HOST}' in setup
        assert f"sudo docker pull {ECR_HOST}/skypilot/music-lab:lab-01" in setup

    def test_ports_and_workdir(self, service, make_image):
        """Ports become -p and workdir becomes -w"""
        argv = docker_run_argv(build(service, make_image(workdir="/app"), RunTarget.AWS))

        for port in (8080, 5173, 8443):
            assert f"{port}:{port}" in argv
        assert argv[argv.index("-w") + 1] == "/app"

    def test_quotes_special_values(self, service, make_image):
        """Values with spaces or shell characters stay one argument"""
        image = make_image(env_vars={"A": "a: b # c; rm -rf /"})
        argv = docker_run_argv(build(service, image, RunTarget.AWS))
        assert "A=a: b # c; rm -rf /" in argv

    def test_regression_multiline_entrypoint_stays_in_container(self, service, make_image):
        """Regression: multi-line entrypoint runs in the container, not on the VM

        เดิมต่อ entrypoint ท้าย docker run ตรง ๆ บรรทัดที่ 2 ไปรันบน VM
        """
        task = build(service, make_image(entrypoint_script="echo 1\necho 2"), RunTarget.AWS)
        argv = docker_run_argv(task)

        assert argv[-3:] == [IMAGE_REF, "-c", "echo 1\necho 2"]

    def test_regression_entrypoint_overrides_image_entrypoint(self, service, make_image):
        """Regression: an entered entrypoint replaces the image ENTRYPOINT, like command: in the lab pod

        เดิมต่อ "/bin/bash -c ..." ท้าย image ถ้า image ตั้ง ENTRYPOINT ไว้ (code-server) คำสั่งนี้กลายเป็น
        argument ของ ENTRYPOINT เดิม เปิดในห้องแลปได้แต่บน AWS พัง
        """
        argv = docker_run_argv(build(service, make_image(entrypoint_script="/bin/bash /run.sh"), RunTarget.AWS))

        assert argv[argv.index("--entrypoint") + 1] == "/bin/sh"
        assert argv.index("--entrypoint") < argv.index(IMAGE_REF)  # option ต้องอยู่ก่อนชื่อ image
        assert argv[-3:] == [IMAGE_REF, "-c", "/bin/bash /run.sh"]

    def test_regression_empty_entrypoint_uses_image_entrypoint(self, service, make_image):
        """Regression: empty entrypoint uses the image's own ENTRYPOINT (code-server)

        ถ้าต่อคำสั่งท้าย docker run จะกลายเป็น argument ของ ENTRYPOINT แล้วพัง
        """
        argv = docker_run_argv(build(service, make_image(entrypoint_script=""), RunTarget.AWS))
        assert argv[-1] == IMAGE_REF
        assert "--entrypoint" not in argv

    def test_null_entrypoint_uses_image_entrypoint(self, service, make_image):
        """entrypoint_script NULL (column is nullable since 20261118_01) behaves like an empty one"""
        argv = docker_run_argv(build(service, make_image(entrypoint_script=None), RunTarget.AWS))
        assert argv[-1] == IMAGE_REF
        assert "--entrypoint" not in argv

    def test_container_starts_in_setup_and_run_waits_for_it(self, service, make_image):
        """Setup starts the container detached and waits for its ports; run only follows it

        _wait_job_running ถือว่าเปิดสำเร็จเมื่อ job เป็น RUNNING ซึ่งเกิดหลัง setup จบ
        การรอ port ใน setup จึงทำให้ "RUNNING" แปลว่า app พร้อมแล้ว
        """
        task = build(service, make_image(), RunTarget.AWS)
        setup, run = task["setup"], task["run"]

        argv = docker_run_argv(task)
        assert argv[:3] == ["-d", "--name", "lab"]
        assert "--rm" not in argv  # เก็บ container ที่ตายไว้ให้อ่าน log ได้
        order = [setup.index(s) for s in ("docker login", "docker pull", "docker rm -f lab", "sudo docker run", WAIT_MARKER)]
        assert order == sorted(order)
        assert "for vlab_port in 8080 5173 8443; do" in setup
        assert f"vlab_deadline=$((SECONDS + {settings.AWS_LAB_READY_TIMEOUT}))" in setup
        assert "docker run" not in run
        assert "sudo docker logs -f lab &" in run
        assert 'exit "$(sudo docker wait lab)"' in run

    @pytest.mark.skipif(shutil.which("bash") is None or sys.platform == "win32", reason="needs bash")
    @pytest.mark.parametrize("entrypoint", [None, "echo 'a b' \"$HOME\"\nexec sleep 1"])
    def test_setup_and_run_are_valid_bash(self, service, make_image, entrypoint):
        """setup / run parse as bash (bash -n), including quotes and a multi-line entrypoint"""
        task = build(service, make_image(entrypoint_script=entrypoint), RunTarget.AWS)
        for script in (task["setup"], task["run"]):
            subprocess.run(["bash", "-n"], input=script, text=True, check=True)

    def test_secret_is_accepted_and_not_in_envs(self, service, make_image):
        """ECR token is a hidden secret, not a plain env"""
        task = build(service, make_image(), RunTarget.AWS)
        sky_task = sky.Task.from_yaml_config(task, secrets_overrides=[("ECR_TOKEN", "dummy")])

        secret = sky_task.secrets["ECR_TOKEN"]
        assert secret.get_secret_value() == "dummy"
        assert "dummy" not in str(secret)  # SkyPilot เก็บเป็น SecretStr แสดงผลเป็น ***
        assert "ECR_TOKEN" not in (sky_task.envs or {})

    def test_task_is_accepted_by_skypilot(self, service, make_image):
        """The new setup / run (multi-line, quotes, $(...)) still load as a SkyPilot task"""
        task = build(service, make_image(entrypoint_script="echo 1\necho 2"), RunTarget.AWS)
        setup, run = task["setup"], task["run"]  # from_yaml_config ดึง key ออกจาก dict ที่ส่งเข้าไป
        sky_task = sky.Task.from_yaml_config(task, secrets_overrides=[("ECR_TOKEN", "dummy")])
        assert sky_task.setup == setup
        assert sky_task.run == run


# ------------------------------------------------- สคริปต์รอ port ของ AWS (รันจริงด้วย docker ปลอม)

@pytest.mark.skipif(shutil.which("bash") is None or sys.platform == "win32", reason="needs bash + /dev/tcp")
class TestAwsWaitReadyScript:
    """AWS wait-for-ports script

    รันสคริปต์จริงด้วย bash โดยแทน sudo / docker ด้วยของปลอม: docker inspect บอก IP = 127.0.0.1
    และบอกว่า container ยังรันอยู่ไหมตามไฟล์ state ส่วน port ใช้ socket ที่เทสเปิดเอง
    """

    @pytest.fixture
    def fake_bin(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        state = tmp_path / "running"
        state.write_text("true")
        scripts = {
            "sudo": '#!/bin/bash\nexec "$@"\n',
            "docker": (
                "#!/bin/bash\n"
                'case "$1 $3" in\n'
                f'  "inspect {{{{.State.Running}}}}") cat {state} ;;\n'
                '  "inspect "*) echo 127.0.0.1 ;;\n'
                '  "logs "*) echo "app log line" ;;\n'
                "esac\n"
            ),
        }
        for name, body in scripts.items():
            path = bin_dir / name
            path.write_text(body)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return bin_dir, state

    @staticmethod
    def run_script(fake_bin, ports, timeout_seconds=4):
        bin_dir, _ = fake_bin
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
        started = time.monotonic()
        result = subprocess.run(["bash", "-c", _aws_wait_ready_script(ports, timeout_seconds)],
                                env=env, capture_output=True, text=True, timeout=30)
        return result, time.monotonic() - started

    @staticmethod
    def listening_port():
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        return sock

    def test_all_ports_open_succeeds(self, fake_bin):
        """Every port accepts TCP -> exit 0"""
        a, b = self.listening_port(), self.listening_port()
        try:
            result, _ = self.run_script(fake_bin, [a.getsockname()[1], b.getsockname()[1]])
        finally:
            a.close()
            b.close()
        assert result.returncode == 0, result.stderr
        assert result.stdout.count("ready") == 2

    def test_port_never_opens_fails_after_timeout(self, fake_bin):
        """A port that never opens -> exit 1 after the timeout, with the container log"""
        closed = self.listening_port()
        port = closed.getsockname()[1]
        closed.close()  # ไม่มีใครฟังแล้ว
        result, elapsed = self.run_script(fake_bin, [port], timeout_seconds=3)
        assert result.returncode == 1
        assert f"port {port} not ready after 3s" in result.stderr
        assert "app log line" in result.stderr
        assert elapsed < 15

    def test_container_exit_fails_fast(self, fake_bin):
        """Container already exited -> exit 1 right away, without waiting for the timeout"""
        _, state = fake_bin
        state.write_text("false")
        closed = self.listening_port()
        port = closed.getsockname()[1]
        closed.close()
        result, elapsed = self.run_script(fake_bin, [port], timeout_seconds=60)
        assert result.returncode == 1
        assert "exited before port" in result.stderr
        assert elapsed < 10

    def test_no_ports_still_catches_a_command_that_exits(self, fake_bin):
        """No ports: a container that stops right after start still fails setup"""
        _, state = fake_bin
        state.write_text("false")
        result, _ = self.run_script(fake_bin, [])
        assert result.returncode == 1
        assert "exited right after start" in result.stderr


# ---------------------------------------------------------------- ชื่อ cluster

class TestClusterName:
    """Cluster name"""

    @pytest.mark.parametrize("repository, prefix", [
        ("skypilot/music-lab", "music-lab-"),
        ("org/My_Lab.v2", "my-lab-v2-"),
        ("x/___", "lab-"),
        ("org/2048-game", "lab-2048-game-"),   # regression: SkyPilot ไม่รับชื่อขึ้นต้นด้วยตัวเลข
        ("music-lab", "music-lab-"),           # ไม่มี org
    ], ids=["normal", "mixed case and symbols", "symbols only", "starts with a digit", "no org"])
    def test_name_is_valid_for_skypilot(self, service, make_image, repository, prefix):
        """Name from repository is valid for SkyPilot"""
        name = service._cluster_name(make_image(repository=repository))

        assert name.startswith(prefix)
        common_utils.check_cluster_name_is_valid(name)

    def test_unique_names_same_second(self, service, make_image):
        """unique=True (prelaunch): many machines in the same second get different, valid names"""
        image = make_image()
        names = {service._cluster_name(image, unique=True) for _ in range(20)}

        assert len(names) == 20
        for name in names:
            common_utils.check_cluster_name_is_valid(name)
