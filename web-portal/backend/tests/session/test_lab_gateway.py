"""
กลุ่ม: lab gateway — ลิงก์ public ของ lab บน AWS (docs/AWS_LAB_GATEWAY.md ข้อ 4)

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
from app.models.lab import RunTarget
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
    # ตารางว่างเป็น {} (ไม่มี key "http")
    return set(table.get("http", {}).get("routers", {}))


class TestBuildRoutes:
    """lab gateway: route table"""

    def test_empty(self, db):
        """no sessions -> {} (Traefik 3.7 cannot decode empty routers / http maps)"""
        assert gw.build_routes(db) == {}

    def test_only_bad_upstreams_is_empty(self, db, add_gw_session):
        """every port skipped -> {} too, not {"http": {"routers": {}}}"""
        add_gw_session(upstreams={"22": "http://10.10.2.14:22"})
        assert gw.build_routes(db) == {}

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


# ---------------------------------------------------------------- A6: endpoint ที่ Traefik เรียก

GATEWAY_TOKEN = "t" * 40
ROUTES_PATH = "/api/internal/v1/gateway/routes"


@pytest.fixture
def client(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.configs.db import get_db
    from app.routes.lab_gateway_route import router as lab_gateway_router

    monkeypatch.setattr(settings, "LAB_GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "LAB_GATEWAY_TOKEN", GATEWAY_TOKEN)
    app = FastAPI()
    app.include_router(lab_gateway_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


class TestRoutesEndpoint:
    """lab gateway: /internal/v1/gateway/routes"""

    def test_registered_in_api_router(self):
        """route is registered in the main api_router (path /internal/v1/gateway/routes)"""
        from app.routes import api_router
        assert "/internal/v1/gateway/routes" in {r.path for r in api_router.routes}

    def test_not_in_openapi(self):
        """endpoint hidden from OpenAPI docs"""
        from app.routes.lab_gateway_route import router as r
        assert all(route.include_in_schema is False for route in r.routes)

    def test_correct_token_returns_table(self, client, add_gw_session):
        """correct X-Gateway-Token -> 200 + Traefik table (not wrapped in ApiResponse)"""
        s = add_gw_session(upstreams={"8443": "http://10.10.2.14:8443"})
        r = client.get(ROUTES_PATH, headers={"X-Gateway-Token": GATEWAY_TOKEN})
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"http"}
        assert set(body["http"]["routers"]) == {f"s-{s.gateway_token}-8443"}

    def test_empty_table(self, client):
        """no AWS lab running -> {} (empty Traefik config, every Host gets 404)"""
        r = client.get(ROUTES_PATH, headers={"X-Gateway-Token": GATEWAY_TOKEN})
        assert r.status_code == 200
        assert r.json() == {}

    @pytest.mark.parametrize("headers", [
        {},
        {"X-Gateway-Token": ""},
        {"X-Gateway-Token": "wrong"},
        {"X-Gateway-Token": GATEWAY_TOKEN[:-1]},
        {"X-Gateway-Token": GATEWAY_TOKEN + "x"},
    ], ids=["missing", "empty", "wrong", "prefix", "longer"])
    def test_bad_token_404(self, client, add_gw_session, headers):
        """missing / wrong token -> 404 and no table leaked"""
        add_gw_session()
        r = client.get(ROUTES_PATH, headers=headers)
        assert r.status_code == 404
        assert "routers" not in r.text

    def test_flag_off_404(self, client, monkeypatch):
        """LAB_GATEWAY_ENABLED=false -> 404 even with the right token"""
        monkeypatch.setattr(settings, "LAB_GATEWAY_ENABLED", False)
        r = client.get(ROUTES_PATH, headers={"X-Gateway-Token": GATEWAY_TOKEN})
        assert r.status_code == 404

    def test_server_token_empty_404(self, client, monkeypatch):
        """server token not set -> 404 (an empty header must never match)"""
        monkeypatch.setattr(settings, "LAB_GATEWAY_TOKEN", "")
        r = client.get(ROUTES_PATH, headers={"X-Gateway-Token": ""})
        assert r.status_code == 404


# ---------------------------------------------------------------- A7: token ไหลเข้า task ของ AWS

def docker_env(task: dict) -> dict[str, str]:
    """env ที่ส่งเข้า container (-e KEY=VALUE ใน docker run ของ AWS task)"""
    import shlex
    argv = shlex.split(task["run"])
    return dict(argv[i + 1].split("=", 1) for i, a in enumerate(argv) if a == "-e")


class TestTaskEnvs:
    """lab gateway: task envs"""

    def test_aws_with_token(self, service, make_image):
        """AWS task with token -> docker run gets Vite allowed hosts + VLAB_PUBLIC_URL_<port>"""
        task = service.create_fastapi_task(make_image(), "music-lab-1", env="staging",
                                           run_target=RunTarget.AWS, gateway_token=TOKEN)
        envs = docker_env(task)
        assert envs["__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS"] == ".bell-lab.space"
        assert envs["VLAB_PUBLIC_URL_8443"] == f"https://l-{TOKEN}-8443.bell-lab.space"
        assert envs["VLAB_PUBLIC_URL_5173"] == f"https://l-{TOKEN}-5173.bell-lab.space"
        assert envs["VLAB_PUBLIC_URL_8080"] == f"https://l-{TOKEN}-8080.bell-lab.space"
        # env เดิมของ lab ยังอยู่
        assert envs["IDE_PASSWORD"] == "musiclab"
        assert envs["APP_ENV"] == "staging"

    def test_aws_without_token(self, service, make_image):
        """AWS task without token -> no gateway envs (same as before)"""
        task = service.create_fastapi_task(make_image(), "music-lab-1", env="staging", run_target=RunTarget.AWS)
        envs = docker_env(task)
        assert not any(k.startswith(("VLAB_PUBLIC_URL_", "__VITE")) for k in envs)

    def test_k8s_ignores_token(self, service, make_image):
        """K3s task never gets gateway envs, even if a token is passed"""
        task = service.create_fastapi_task(make_image(), "music-lab-1", env="staging", gateway_token=TOKEN)
        assert task["envs"] == {"IDE_PASSWORD": "musiclab", "APP_ENV": "staging"}


# ---------------------------------------------------------------- A7–A8: กด Start ทั้งเส้น (sky ปลอม)

@pytest.fixture
def gateway_on(monkeypatch):
    monkeypatch.setattr(settings, "LAB_GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "LAB_GATEWAY_TOKEN", GATEWAY_TOKEN)


def only_session(db, world):
    [s] = db.query(SessionModel).filter(SessionModel.user_id == world.user.id).all()
    return s


class TestStartWithGateway:
    """lab gateway: Start"""

    def test_aws_gets_public_link(self, svc, db, world, fake_sky, gateway_on):
        """flag on + AWS -> endpoints = https://l-..., upstreams = private IP"""
        fake_sky.endpoints_map = {"8080": "10.10.2.14:8080"}
        result = svc.create_session(world.user.id, world.aws_lab.id)

        s = only_session(db, world)
        t = s.gateway_token
        assert re.fullmatch(r"[a-z2-7]{16}", t)
        assert s.upstreams == {"8080": "http://10.10.2.14:8080"}
        assert s.endpoints == {"8080": f"https://l-{t}-8080.bell-lab.space"}
        assert result["endpoints"] == s.endpoints

    def test_aws_task_has_envs(self, svc, db, world, fake_sky, gateway_on):
        """the launched task carries the same token as the record"""
        svc.create_session(world.user.id, world.aws_lab.id)
        s = only_session(db, world)
        [(_, task)] = fake_sky.launched
        assert f"VLAB_PUBLIC_URL_8080=https://l-{s.gateway_token}-8080.bell-lab.space" in task.run

    def test_running_session_in_route_table(self, svc, db, world, fake_sky, gateway_on):
        """after Start the session shows up in the Traefik table"""
        fake_sky.endpoints_map = {"8080": "10.10.2.14:8080"}
        svc.create_session(world.user.id, world.aws_lab.id)
        s = only_session(db, world)
        table = gw.build_routes(db)
        assert table["http"]["services"][f"s-{s.gateway_token}-8080"]["loadBalancer"]["servers"] == \
            [{"url": "http://10.10.2.14:8080"}]

    def test_flag_off_unchanged(self, svc, db, world, fake_sky):
        """flag off -> no token, endpoints are the private IP like before"""
        fake_sky.endpoints_map = {"8080": "10.10.2.14:8080"}
        svc.create_session(world.user.id, world.aws_lab.id)
        s = only_session(db, world)
        assert s.gateway_token is None
        assert s.upstreams is None
        assert s.endpoints == {"8080": "http://10.10.2.14:8080"}
        [(_, task)] = fake_sky.launched
        assert "VLAB_PUBLIC_URL_" not in task.run

    def test_k8s_no_token(self, svc, db, world, fake_sky, gateway_on):
        """flag on + SkyPilot on K3s (Start from a lab machine) -> no token, endpoints unchanged

        run target มาจากที่ที่กด Start (IP) ไม่ใช่ตัว lab — กดจากข้างนอกได้ AWS เสมอ
        จึงเรียก _new_sky_session ด้วย KUBERNETES ตรง ๆ (ทาง LAB_MACHINE_LAUNCH=skypilot)
        """
        s, task = svc._new_sky_session(world.user.id, world.k8s_lab, world.k8s_image, RunTarget.KUBERNETES,
                                       pin_node=None, class_slot_id=None)
        svc._run_sky_launch(s, task, world.k8s_image)
        assert s.gateway_token is None
        assert s.upstreams is None
        assert s.endpoints == {"8080": "http://10.0.0.5:8080"}

    def test_port_outside_range_dropped(self, svc, db, world, fake_sky, gateway_on, caplog):
        """port 80 in the image -> no public link + warning (docs/AWS_LAB_GATEWAY.md ข้อ 4.6)"""
        fake_sky.endpoints_map = {"8080": "10.10.2.14:8080", "80": "10.10.2.14:80"}
        with caplog.at_level(logging.WARNING, logger="server"):
            svc.create_session(world.user.id, world.aws_lab.id)
        s = only_session(db, world)
        assert set(s.endpoints) == {"8080"}
        assert "outside" in caplog.text and "'80'" in caplog.text
        assert router_names(gw.build_routes(db)) == {f"s-{s.gateway_token}-8080"}

    def test_tokens_unique_per_session(self, svc, db, world, fake_sky, gateway_on):
        """each Start gets a new token (stop, then start again)"""
        svc.create_session(world.user.id, world.aws_lab.id)
        first = only_session(db, world)
        first.status = SessionStatus.STOPPED
        db.commit()
        fake_sky.clusters = {}
        svc.create_session(world.user.id, world.aws_lab.id)
        tokens = {s.gateway_token for s in
                  db.query(SessionModel).filter(SessionModel.user_id == world.user.id).all()}
        assert len(tokens) == 2 and None not in tokens

    def test_prelaunch_token_hidden_until_claimed(self, svc, db, world, fake_sky, gateway_on):
        """prelaunch with flag on -> token from PENDING, not routed until claimed"""
        fake_sky.endpoints_map = {"8080": "10.10.2.14:8080"}
        s, task = svc._new_sky_session(world.user.id, world.aws_lab, world.aws_image, RunTarget.AWS,
                                       pin_node=None, class_slot_id=None, prelaunched_at=datetime.utcnow())
        assert s.status == SessionStatus.PENDING and s.gateway_token
        svc._run_sky_launch(s, task, world.aws_image)
        assert s.status == SessionStatus.RUNNING
        assert router_names(gw.build_routes(db)) == set()

        s.claimed_at = datetime.utcnow()
        db.commit()
        assert router_names(gw.build_routes(db)) == {f"s-{s.gateway_token}-8080"}


class TestNotExposed:
    """lab gateway: not exposed"""

    def test_session_response_has_no_internal_fields(self, svc, db, world, fake_sky, gateway_on):
        """SessionResponse (GET /sessions, /sessions/{id}) has no gateway_token / upstreams"""
        from app.schemas.session_schema import SessionDetailResponse, SessionResponse
        svc.create_session(world.user.id, world.aws_lab.id)
        s = only_session(db, world)
        for schema in (SessionResponse, SessionDetailResponse):
            dumped = schema.model_validate(s).model_dump()
            assert "gateway_token" not in dumped and "upstreams" not in dumped
            assert dumped["endpoints"] == s.endpoints

    def test_create_result_has_no_internal_fields(self, svc, db, world, fake_sky, gateway_on):
        """Start response has no token field / private IP"""
        fake_sky.endpoints_map = {"8080": "10.10.2.14:8080"}
        result = svc.create_session(world.user.id, world.aws_lab.id)
        assert "gateway_token" not in result and "upstreams" not in result
        assert "10.10.2.14" not in str(result)


# ---------------------------------------------------------------- A9: หน้า admin

class TestAdminHidden:
    """lab gateway: admin page"""

    def test_session_admin_hides_columns(self):
        """sqladmin SessionAdmin: list / details / form exclude gateway_token and upstreams"""
        from app.main import SessionAdmin
        listed = {c.key for c in SessionAdmin.column_list}
        assert not listed & {"gateway_token", "upstreams", "endpoints"}
        assert {"gateway_token", "upstreams"} <= set(SessionAdmin.column_details_exclude_list)
        assert {"gateway_token", "upstreams"} <= set(SessionAdmin.form_excluded_columns)
