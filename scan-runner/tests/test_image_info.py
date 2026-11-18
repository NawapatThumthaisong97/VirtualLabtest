"""image_info / encode_result: ข้อมูลจาก config ของ image ที่ส่งให้ backend (runner 1.2.0)

ฟังก์ชันล้วน ไม่เรียก skopeo จริง รัน: python3 -m pytest scan-runner/tests
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import runner  # noqa: E402


def config(**runtime):
    """ผลของ skopeo inspect --config แบบย่อ"""
    return {"os": "linux", "architecture": "amd64", "config": runtime}


class TestImageInfo:
    def test_code_server_like_image(self):
        """ENTRYPOINT + CMD + WORKDIR + EXPOSE ถูกอ่านครบ"""
        info = runner.image_info(config(
            User="coder",
            ExposedPorts={"8080/tcp": {}},
            Entrypoint=["/usr/bin/entrypoint.sh", "--bind-addr", "0.0.0.0:8080"],
            Cmd=["."],
            WorkingDir="/home/coder",
        ))
        assert info == {
            "os": "linux",
            "architecture": "amd64",
            "user": "coder",
            "exposedPorts": ["8080/tcp"],
            "entrypoint": ["/usr/bin/entrypoint.sh", "--bind-addr", "0.0.0.0:8080"],
            "cmd": ["."],
            "workingDir": "/home/coder",
        }

    def test_nothing_set_gives_empty_values_not_missing_keys(self):
        """ไม่ได้ตั้งอะไรเลย: key ยังอยู่ครบ (backend แยก "image ไม่มีคำสั่ง" ออกจาก "runner รุ่นเก่า" ได้)"""
        info = runner.image_info(config())
        assert info["entrypoint"] == []
        assert info["cmd"] == []
        assert info["workingDir"] == ""
        assert info["exposedPorts"] == []
        assert info["user"] == ""

    def test_null_config_section(self):
        """config เป็น null (image บางตัวจาก tool อื่น) ไม่พัง"""
        info = runner.image_info({"os": "linux", "architecture": "amd64", "config": None})
        assert info["cmd"] == [] and info["exposedPorts"] == []

    def test_ports_keep_protocol_and_are_sorted(self):
        """เก็บ /proto ไว้ (1.1.0 ตัดทิ้งจน udp ปนกับ tcp) เรียงตามเลข ไม่มี /proto = tcp"""
        info = runner.image_info(config(ExposedPorts={"8443/tcp": {}, "53/udp": {}, "3000": {}, "8080/TCP": {}}))
        assert info["exposedPorts"] == ["53/udp", "3000/tcp", "8080/tcp", "8443/tcp"]
        assert runner.tcp_ports(info["exposedPorts"]) == [3000, 8080, 8443]

    def test_bad_ports_are_dropped(self):
        """เลขนอกช่วงหรือไม่ใช่ตัวเลขไม่ถูกส่งต่อ"""
        info = runner.image_info(config(ExposedPorts={"0/tcp": {}, "70000/tcp": {}, "abc/tcp": {}, "22/tcp": {}}))
        assert info["exposedPorts"] == ["22/tcp"]

    def test_ports_are_capped(self):
        """port เยอะเกิน (EXPOSE 1000-2000) ถูกตัดที่ MAX_EXPOSED_PORTS"""
        info = runner.image_info(config(ExposedPorts={f"{p}/tcp": {} for p in range(1000, 1100)}))
        assert len(info["exposedPorts"]) == runner.MAX_EXPOSED_PORTS
        assert info["exposedPorts"][0] == "1000/tcp"

    def test_command_is_clipped(self):
        """คำสั่งยาว / argument เยอะถูกตัด และขึ้นบรรทัดใหม่ถูกลบ (ผลต้องไม่เกิน termination message)"""
        info = runner.image_info(config(Cmd=["sh", "-c", "echo a\n" + "x" * 500] + [str(i) for i in range(30)]))
        assert len(info["cmd"]) == runner.MAX_COMMAND_ARGS
        assert len(info["cmd"][2]) <= runner.MAX_COMMAND_ARG_TEXT
        assert "\n" not in info["cmd"][2]

    @pytest.mark.parametrize("value", ["npm start", None, 5, {"a": 1}])
    def test_command_that_is_not_a_list(self, value):
        """Entrypoint / Cmd ที่ไม่ใช่ list (config แปลก) ถือว่าไม่ได้ตั้ง"""
        assert runner.image_info(config(Entrypoint=value, Cmd=value))["cmd"] == []


class TestEncodeResult:
    @staticmethod
    def result(image):
        return {
            "imageId": "x", "etag": "e", "verdict": "PASS", "retryable": False,
            "reasons": [], "warnings": ["image runs as root"], "digest": "sha256:" + "a" * 64,
            "summary": {"runnerVersion": "1.2.0", "image": image},
        }

    def test_small_result_is_untouched(self):
        image = runner.image_info(config(ExposedPorts={"8080/tcp": {}}, Cmd=["httpd"]))
        decoded = json.loads(runner.encode_result(self.result(image)))
        assert decoded["summary"]["image"] == image

    def test_huge_commands_are_trimmed_before_ports(self):
        """ผลใหญ่เกิน: ตัดคำสั่งก่อน exposedPorts ยังอยู่ (backend ใช้เติม port ให้ lab)"""
        long_args = ["y" * runner.MAX_COMMAND_ARG_TEXT] * runner.MAX_COMMAND_ARGS
        image = runner.image_info(config(
            ExposedPorts={f"{p}/tcp": {} for p in range(8000, 8020)},
            Entrypoint=long_args, Cmd=long_args, WorkingDir="/w" * 100,
        ))
        result = self.result(image)
        result["summary"]["top"] = [{"id": "CVE-" + "z" * 150}] * 5
        data = runner.encode_result(result)

        assert len(data) <= runner.MAX_RESULT_BYTES
        decoded = json.loads(data)
        assert len(decoded["summary"]["image"]["exposedPorts"]) == 20
        assert decoded["digest"] and decoded["verdict"] == "PASS"
