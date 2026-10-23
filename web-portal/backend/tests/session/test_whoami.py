"""
กลุ่ม 9: GET /v1/whoami — backend เห็น IP ของเครื่องที่ถามเป็นอะไร (ansible ใช้ตรวจหลัง deploy ว่าไม่มี NAT คั่น)
"""
from types import SimpleNamespace

from app.routes.session_route import whoami
from tests.session.test_warm_pod import OUTSIDE_IP, PETE_IP, k8s  # noqa: F401 (fixture)


def _req(ip):
    return SimpleNamespace(client=SimpleNamespace(host=ip) if ip else None)


class TestWhoami:
    """whoami: client IP + matching lab machine"""

    def test_lab_machine(self, k8s):
        """IP of a Ready worker -> labMachine = that node"""
        assert whoami(_req(PETE_IP))["data"] == {"clientIp": PETE_IP, "labMachine": "worker-pete", "error": None}

    def test_outside(self, k8s):
        """IP not a worker (e.g. docker gateway after NAT) -> labMachine null"""
        assert whoami(_req("172.18.0.1"))["data"]["labMachine"] is None
        assert whoami(_req(OUTSIDE_IP))["data"]["labMachine"] is None

    def test_k8s_down(self, k8s):
        """K3s unreachable -> still 200, error says why"""
        k8s.error = RuntimeError("connection refused")
        data = whoami(_req(PETE_IP))["data"]
        assert data["labMachine"] is None and "connection refused" in data["error"]
