"""
กลุ่ม: lab gateway — ลิงก์ public ของ lab บน AWS (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md 1A)

ส่วนนี้ (A4) เทสฟังก์ชันล้วนใน app/services/lab_gateway_service.py ไม่ต่อ DB
ตาราง route / endpoint / session_service เพิ่มใน A5–A8

บรรทัดแรกของ docstring ของ class / เทส = ชื่อ group / case ในตารางสรุป (conftest.py)
"""
import re

import pytest

from app.configs.settings import settings
from app.services import lab_gateway_service as gw

TOKEN = "k7m2q9xw4bz3ha6c"


@pytest.fixture(autouse=True)
def gateway_settings(monkeypatch):
    monkeypatch.setattr(settings, "LAB_GATEWAY_DOMAIN", "bell-lab.space")
    monkeypatch.setattr(settings, "LAB_GATEWAY_PORT_MIN", 3000)
    monkeypatch.setattr(settings, "LAB_GATEWAY_PORT_MAX", 9999)
    monkeypatch.setattr(settings, "LAB_GATEWAY_UPSTREAM_CIDRS_STR", "10.10.2.0/24,10.10.3.0/24")


class TestToken:
    """lab gateway: token"""

    def test_format(self):
        """token = base32 lowercase 16 chars, valid in a DNS label"""
        token = gw.new_token()
        assert len(token) == gw.TOKEN_LENGTH == 16
        assert re.fullmatch(r"[a-z2-7]{16}", token)

    def test_unique(self):
        """tokens are random (1000 tokens, no duplicates)"""
        assert len({gw.new_token() for _ in range(1000)}) == 1000

    def test_hostname_fits_dns_label(self):
        """l-<token>-<port> fits a DNS label (<= 63 chars)"""
        label = gw.public_host(gw.new_token(), 9999).split(".")[0]
        assert len(label) <= 63
        assert re.fullmatch(r"[a-z0-9-]+", label)


class TestPortAllowed:
    """lab gateway: allowed ports"""

    @pytest.mark.parametrize("port,expected", [
        (2999, False), (3000, True), (8443, True), (9999, True), (10000, False),
        (22, False), (80, False),
        ("8443", True), (" 8443 ", True), ("22", False),
        ("abc", False), ("-1", False), ("", False), (None, False), (True, False),
    ])
    def test_range(self, port, expected):
        """only ports in LAB_GATEWAY_PORT_MIN..MAX"""
        assert gw.port_allowed(port) is expected

    def test_follows_settings(self, monkeypatch):
        """range follows settings"""
        monkeypatch.setattr(settings, "LAB_GATEWAY_PORT_MAX", 8000)
        assert gw.port_allowed(8000) is True
        assert gw.port_allowed(8443) is False


class TestPublicLinks:
    """lab gateway: public links"""

    def test_public_host(self):
        """public_host = l-<token>-<port>.<domain>"""
        assert gw.public_host(TOKEN, 8443) == f"l-{TOKEN}-8443.bell-lab.space"
        assert gw.public_host(TOKEN, "5173") == f"l-{TOKEN}-5173.bell-lab.space"

    def test_public_endpoints_drop_disallowed_ports(self):
        """public_endpoints: https links, ports outside range (22, 80) dropped"""
        assert gw.public_endpoints(TOKEN, [8080, 5173, 8443, 22, 80]) == {
            "8080": f"https://l-{TOKEN}-8080.bell-lab.space",
            "5173": f"https://l-{TOKEN}-5173.bell-lab.space",
            "8443": f"https://l-{TOKEN}-8443.bell-lab.space",
        }

    def test_public_endpoints_str_keys(self):
        """public_endpoints accepts str keys (from JSONB) and returns str keys"""
        assert gw.public_endpoints(TOKEN, ["8443"]) == {"8443": f"https://l-{TOKEN}-8443.bell-lab.space"}

    def test_public_endpoints_empty(self):
        """no allowed ports -> empty dict"""
        assert gw.public_endpoints(TOKEN, [22]) == {}
        assert gw.public_endpoints(TOKEN, []) == {}

    def test_gateway_envs(self):
        """gateway_envs: Vite allowed hosts + VLAB_PUBLIC_URL_<port> per allowed port"""
        assert gw.gateway_envs(TOKEN, [8443, 5173, 22]) == {
            "__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS": ".bell-lab.space",
            "VLAB_PUBLIC_URL_8443": f"https://l-{TOKEN}-8443.bell-lab.space",
            "VLAB_PUBLIC_URL_5173": f"https://l-{TOKEN}-5173.bell-lab.space",
        }


class TestUpstreamOk:
    """lab gateway: upstream check"""

    @pytest.mark.parametrize("url", [
        "http://10.10.2.14:8443",
        "http://10.10.3.200:5173",
    ])
    def test_allowed(self, url):
        """lab subnet + allowed port -> ok"""
        assert gw.upstream_ok(url) is True

    @pytest.mark.parametrize("url", [
        "http://8.8.8.8:8080",            # นอก subnet
        "http://10.10.1.5:8080",          # subnet อื่นใน VPC
        "http://100.102.72.39:8000",      # Tailscale IP (backend)
        "http://127.0.0.1:8080",          # router เอง
        "http://10.10.2.14:22",           # พอร์ตนอกช่วง
        "http://10.10.2.14",              # ไม่มีพอร์ต
        "https://10.10.2.14:8443",        # ไม่ใช่ http
        "http://lab.internal:8443",       # ชื่อ host ไม่ใช่ IP
        "http://10.10.2.14:99999",        # พอร์ตเกิน
        "not-a-url",
        "",
        None,
    ])
    def test_rejected(self, url):
        """outside subnet / bad port / not http / hostname / malformed -> rejected"""
        assert gw.upstream_ok(url) is False

    def test_follows_settings(self, monkeypatch):
        """allowed subnets follow LAB_GATEWAY_UPSTREAM_CIDRS_STR"""
        monkeypatch.setattr(settings, "LAB_GATEWAY_UPSTREAM_CIDRS_STR", "10.10.9.0/24")
        assert gw.upstream_ok("http://10.10.9.1:8080") is True
        assert gw.upstream_ok("http://10.10.2.14:8080") is False
