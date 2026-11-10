"""
กลุ่ม: lab gateway — ลิงก์ public ของ lab บน AWS (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md 1A)

A4: ฟังก์ชันล้วนใน app/services/lab_gateway_service.py ไม่ต่อ DB
A5: build_routes ใช้ DB ทดสอบ (fixture db / world)
endpoint / session_service เพิ่มใน A6–A8

บรรทัดแรกของ docstring ของ class / เทส = ชื่อ group / case ในตารางสรุป (conftest.py)
"""
import logging
import re
from datetime import datetime, timedelta

import pytest

from app.configs.settings import settings
from app.models.session import ServiceType, Session as SessionModel, SessionStatus
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


# ---------------------------------------------------------------- A5: build_routes (DB)

@pytest.fixture
def add_gw_session(db, world):
    """session lab AWS ที่ผ่าน gateway (ค่าเริ่ม = ควรอยู่ในตาราง) override ได้ทุก field"""
    def _add(**overrides):
        now = datetime.utcnow()
        fields = dict(
            user_id=world.user.id,
            lab_id=world.aws_lab.id,
            lab_image_id=world.aws_image.id,
            service_type=ServiceType.LAB,
            sky_cluster_name=f"aws-{gw.new_token()[:8]}",
            status=SessionStatus.RUNNING,
            started_at=now - timedelta(minutes=1),
            is_remote=True,
            is_cloud=True,
            gateway_token=gw.new_token(),
            upstreams={"8080": "http://10.10.2.14:8080", "8443": "http://10.10.2.14:8443"},
        )
        fields.update(overrides)
        s = SessionModel(**fields)
        db.add(s)
        db.commit()
        return s
    return _add


def router_names(table):
    return set(table["http"]["routers"])


class TestBuildRoutes:
    """lab gateway: route table"""

    def test_empty(self, db):
        """no sessions -> empty table in Traefik format"""
        assert gw.build_routes(db) == {"http": {"routers": {}, "services": {}}}

    def test_running_session_all_ports(self, db, add_gw_session):
        """RUNNING AWS session with token -> one router + service per port"""
        s = add_gw_session()
        t = s.gateway_token
        assert gw.build_routes(db) == {"http": {
            "routers": {
                f"s-{t}-8080": {"rule": f"Host(`l-{t}-8080.bell-lab.space`)",
                                "service": f"s-{t}-8080", "entryPoints": ["web"]},
                f"s-{t}-8443": {"rule": f"Host(`l-{t}-8443.bell-lab.space`)",
                                "service": f"s-{t}-8443", "entryPoints": ["web"]},
            },
            "services": {
                f"s-{t}-8080": {"loadBalancer": {"servers": [{"url": "http://10.10.2.14:8080"}]}},
                f"s-{t}-8443": {"loadBalancer": {"servers": [{"url": "http://10.10.2.14:8443"}]}},
            },
        }}

    def test_multiple_sessions(self, db, add_gw_session):
        """several sessions -> all in the table, no mixing"""
        a = add_gw_session(upstreams={"8080": "http://10.10.2.14:8080"})
        b = add_gw_session(upstreams={"8080": "http://10.10.3.20:8080"})
        table = gw.build_routes(db)
        assert router_names(table) == {f"s-{a.gateway_token}-8080", f"s-{b.gateway_token}-8080"}
        assert table["http"]["services"][f"s-{b.gateway_token}-8080"]["loadBalancer"]["servers"] == \
            [{"url": "http://10.10.3.20:8080"}]

    @pytest.mark.parametrize("overrides", [
        {"status": SessionStatus.PENDING},
        {"status": SessionStatus.STOPPED},
        {"status": SessionStatus.FAILED},
        {"deleted_at": datetime.utcnow()},
        {"is_cloud": False},
        {"gateway_token": None},
        {"upstreams": None},
    ], ids=["pending", "stopped", "failed", "deleted", "k8s", "no-token", "no-upstreams"])
    def test_not_routable(self, db, add_gw_session, overrides):
        """PENDING / STOPPED / FAILED / deleted / K8s / no token / no upstreams -> not in table"""
        add_gw_session(**overrides)
        assert router_names(gw.build_routes(db)) == set()

    def test_prelaunch_unclaimed_hidden(self, db, add_gw_session):
        """prelaunched but unclaimed -> not in table"""
        add_gw_session(prelaunched_at=datetime.utcnow())
        assert router_names(gw.build_routes(db)) == set()

    def test_prelaunch_claimed_visible(self, db, add_gw_session):
        """prelaunched and claimed -> in table"""
        now = datetime.utcnow()
        s = add_gw_session(prelaunched_at=now - timedelta(minutes=5), claimed_at=now)
        assert router_names(gw.build_routes(db)) == {f"s-{s.gateway_token}-8080", f"s-{s.gateway_token}-8443"}

    def test_session_stops_drops_out(self, db, add_gw_session):
        """session stops -> next poll it is gone (no separate delete step)"""
        s = add_gw_session()
        assert router_names(gw.build_routes(db))
        s.status = SessionStatus.STOPPED
        db.commit()
        assert router_names(gw.build_routes(db)) == set()

    @pytest.mark.parametrize("upstreams", [
        {"8080": "http://8.8.8.8:8080"},
        {"22": "http://10.10.2.14:22"},
        {"8080": "http://100.102.72.39:8000"},
        {"abc": "http://10.10.2.14:8080"},
        {"8080": None},
    ], ids=["outside-subnet", "port-22", "backend-ip", "non-numeric-key", "null-url"])
    def test_bad_upstream_skipped_with_warning(self, db, add_gw_session, caplog, upstreams):
        """bad upstream -> skipped + warning, good ports of the same session kept"""
        s = add_gw_session(upstreams={**upstreams, "8443": "http://10.10.2.14:8443"})
        with caplog.at_level(logging.WARNING, logger=gw.logger.name):
            table = gw.build_routes(db)
        assert router_names(table) == {f"s-{s.gateway_token}-8443"}
        assert "not allowed" in caplog.text

    def test_bad_session_does_not_break_others(self, db, add_gw_session):
        """one bad session does not break the table for everyone else"""
        add_gw_session(upstreams={"abc": "garbage"})
        good = add_gw_session()
        assert router_names(gw.build_routes(db)) == {f"s-{good.gateway_token}-8080", f"s-{good.gateway_token}-8443"}
