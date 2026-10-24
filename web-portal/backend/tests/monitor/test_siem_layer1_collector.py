"""
Tests for 5-Layer SIEM Architecture — Layer 1: Collector (Vector Agent + Falco eBPF)

Verifies:
1. K8s DaemonSet & ConfigMap manifests in k8s/siem/layer1-collector/ are valid YAML
2. Falco Collector uses modern_ebpf engine (CO-RE), least-privilege Linux capabilities,
   and detects container shell spawns, sensitive file reads, and escape syscalls
3. Vector Agent Collector sweeps system logs, application logs, boundary logs, and Falco eBPF alerts
   while strictly enforcing Zero-Trust Plane Separation (no student /var/log/pods harvesting)
4. All outbound telemetry is routed over the Tailscale mesh (100.64.0.0/10) with zero public ports exposed
5. AWS EC2/SkyPilot AMI baking script & Ansible role (siem-layer1-collector) are valid and complete
6. Backend Ingestion API (/api/v1/logs) accepts Vector + Falco eBPF alerts, masks PII, and increments falcoEbpfAlerts
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jose import jwt
import pytest
import yaml

from app.configs.db import get_db
from app.configs.settings import settings
from app.exceptions.domain import DomainError
from app.main import STATUS_MAP
from app.models.rbac import Role, UserRoleAssignment
from app.models.user import User, UserRole
from app.routes import api_router
from app.seeds.rbac_seed import RBACSeeder


REPO_ROOT = Path(__file__).resolve().parents[4]
K8S_LAYER1_DIR = REPO_ROOT / "k8s" / "siem" / "layer1-collector"
ANSIBLE_LAYER1_DIR = REPO_ROOT / "ansible" / "roles" / "siem-layer1-collector"


@pytest.fixture(autouse=True)
def fixed_auth_settings(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-salt-for-hmac-sha256-layer1")
    monkeypatch.setattr(settings, "ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)


@pytest.fixture
def test_app(db):
    app = FastAPI()

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request, exc: DomainError):
        status_code = 500
        for error_type, code in STATUS_MAP.items():
            if isinstance(exc, error_type):
                status_code = code
                break
        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "message": exc.message,
                "data": None,
                "error": {"code": exc.code, "message": exc.message},
            },
        )

    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


@pytest.fixture
def admin_token(db):
    RBACSeeder(db).seed()
    db.commit()

    admin = User(
        id=uuid.uuid4(),
        email="admin.layer1@dome.tu.ac.th",
        name="SIEM Admin",
        role=UserRole.ADMIN,
    )
    db.add(admin)
    db.flush()

    role_row = db.query(Role).filter(Role.role_name == "Admin").first()
    if role_row:
        db.add(UserRoleAssignment(user_id=admin.id, role_id=role_row.id))
    db.commit()

    payload = {
        "sub": str(admin.id),
        "email": admin.email,
        "name": admin.name,
        "role": UserRole.ADMIN.value,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


class TestLayer1KubernetesManifests:
    """Verify K3s DaemonSet & ConfigMap manifests for Vector Agent + Falco eBPF"""

    def test_all_layer1_k8s_manifests_are_valid_yaml(self):
        yaml_files = sorted(K8S_LAYER1_DIR.glob("*.yaml"))
        assert len(yaml_files) >= 5, "Expected at least 5 Layer 1 K8s manifests"

        for path in yaml_files:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            assert len(docs) >= 1, f"{path.name} is empty"
            for doc in docs:
                assert isinstance(doc, dict)
                assert "apiVersion" in doc
                assert "kind" in doc
                assert doc["metadata"]["labels"]["vlab.siem/layer"] == "1-collector"

    def test_falco_daemonset_uses_modern_ebpf_and_container_kernel_rules(self):
        cm_doc = yaml.safe_load(
            (K8S_LAYER1_DIR / "01-falco-rules-configmap.yaml").read_text(encoding="utf-8")
        )
        falco_cfg = yaml.safe_load(cm_doc["data"]["falco.yaml"])
        assert falco_cfg["engine"]["kind"] == "modern_ebpf"
        assert falco_cfg["json_output"] is True
        assert falco_cfg["http_output"]["url"] == "http://127.0.0.1:8687/falco"

        custom_rules = yaml.safe_load(cm_doc["data"]["vlab_custom_rules.yaml"])
        rule_names = {item.get("rule") for item in custom_rules if isinstance(item, dict) and "rule" in item}
        assert "VLab Unauthorized Interactive Shell in Container" in rule_names
        assert "VLab Sensitive System File Read in Container" in rule_names
        assert "VLab Container Escape Privileged Syscall Attempt" in rule_names
        assert "VLab Cryptomining or Recon Tool Execution in Container" in rule_names

        ds_doc = yaml.safe_load(
            (K8S_LAYER1_DIR / "02-falco-daemonset.yaml").read_text(encoding="utf-8")
        )
        assert ds_doc["kind"] == "DaemonSet"
        container = ds_doc["spec"]["template"]["spec"]["containers"][0]
        caps_add = set(container["securityContext"]["capabilities"]["add"])
        assert {"BPF", "PERFMON", "SYS_RESOURCE", "SYS_PTRACE"}.issubset(caps_add)
        assert container["securityContext"]["privileged"] is False

    def test_vector_agent_collects_logs_enforces_plane_separation_and_uses_tailscale(self):
        cm_Text = (K8S_LAYER1_DIR / "03-vector-agent-configmap.yaml").read_text(encoding="utf-8")
        assert "/var/log/pods" not in cm_Text, "Plane separation violated: student pod logs must never be collected"

        cm_doc = yaml.safe_load(cm_Text)
        vector_cfg = yaml.safe_load(cm_doc["data"]["vector.yaml"])

        sources = vector_cfg["sources"]
        assert "host_system_journal" in sources
        assert "host_application_logs" in sources
        assert "boundary_squid_logs" in sources
        assert "boundary_kyverno_logs" in sources
        assert "boundary_tailscale_logs" in sources
        assert "falco_ebpf_http" in sources
        assert "falco_ebpf_file" in sources

        # Local Falco receiver binds strictly to loopback (127.0.0.1), never 0.0.0.0
        assert sources["falco_ebpf_http"]["address"].startswith("127.0.0.1:")

        # Sink uses Tailscale internal network with disk buffering
        hub_sink = vector_cfg["sinks"]["tailscale_central_hub"]
        assert hub_sink["buffer"]["type"] == "disk"
        assert hub_sink["request"]["headers"]["X-Transport-Network"] == "tailscale0"

        # DaemonSet must not expose any public hostPort
        ds_doc = yaml.safe_load(
            (K8S_LAYER1_DIR / "04-vector-agent-daemonset.yaml").read_text(encoding="utf-8")
        )
        assert ds_doc["kind"] == "DaemonSet"
        for c in ds_doc["spec"]["template"]["spec"]["containers"]:
            assert "ports" not in c, "Vector Agent DaemonSet must not expose public hostPorts"


class TestLayer1AnsibleAndAwsAmiBaking:
    """Verify Ansible Role and AWS EC2/SkyPilot AMI baking script for Layer 1"""

    def test_ansible_role_and_aws_ami_script_exist_and_preserve_plane_separation(self):
        defaults_file = ANSIBLE_LAYER1_DIR / "defaults" / "main.yml"
        tasks_file = ANSIBLE_LAYER1_DIR / "tasks" / "main.yml"
        vector_tpl = ANSIBLE_LAYER1_DIR / "templates" / "vector-agent.yaml.j2"
        bake_script = ANSIBLE_LAYER1_DIR / "files" / "bake-aws-ami-collector.sh"

        assert defaults_file.exists()
        assert tasks_file.exists()
        assert vector_tpl.exists()
        assert bake_script.exists()

        defaults_data = yaml.safe_load(defaults_file.read_text(encoding="utf-8"))
        assert defaults_data["falco_engine_kind"] == "modern_ebpf"
        assert defaults_data["tailscale_interface"] == "tailscale0"
        assert defaults_data["forbidden_pod_logs_path"] == "/var/log/pods/*/*/*.log"

        vector_tpl_text = vector_tpl.read_text(encoding="utf-8")
        assert "/var/log/pods" not in vector_tpl_text

        bake_text = bake_script.read_text(encoding="utf-8")
        assert "FALCO_DRIVER_CHOICE=modern_ebpf" in bake_text
        assert "tailscaled" in bake_text
        assert "vector.service" in bake_text


class TestLayer1BackendTelemetryIngestion:
    """Verify Backend API ingests Falco eBPF & Vector Agent telemetry over Tailscale"""

    def test_ingest_falco_ebpf_kernel_alert_increments_counter_and_masks_pii(self, client, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}

        before_resp = client.get("/api/v1/metrics/security-counters", headers=headers)
        assert before_resp.status_code == 200
        initial_falco = before_resp.json()["data"]["falcoEbpfAlerts"]

        payload = {
            "severity": "CRITICAL",
            "category": "SECURITY_VIOLATION",
            "eventType": "FALCO_SENSITIVE_FILE_READ",
            "source": "k3s-worker-lab1-01",
            "message": (
                "Sensitive system file read detected in container "
                "(user=6709616099 email=sophia.dav@dome.tu.ac.th file=/etc/shadow "
                "container_name=lab-pod-114bb79a cmdline=cat /etc/shadow)"
            ),
            "userId": str(uuid.uuid4()),
            "clusterOrSubnet": "192.168.1.0/24",
            "metadata": {
                "siem_layer": "layer1-collector",
                "collector": "falco-ebpf",
                "engine": "modern_ebpf",
                "rule": "VLab Sensitive System File Read in Container",
                "fast_track": True,
                "transport": "tailscale0",
            },
        }

        post_resp = client.post("/api/v1/logs", json=payload, headers=headers)
        assert post_resp.status_code == 201
        item = post_resp.json()["data"]

        assert item["eventType"] == "FALCO_SENSITIVE_FILE_READ"
        assert "sophia.dav@dome.tu.ac.th" not in item["message"]
        assert "6709616099" not in item["message"]
        assert "[REDACTED_EMAIL]" in item["message"]
        assert "[REDACTED_STUDENT_ID]" in item["message"]
        assert item["metadata"]["collector"] == "falco-ebpf"
        assert item["metadata"]["fast_track"] is True

        after_resp = client.get("/api/v1/metrics/security-counters", headers=headers)
        assert after_resp.status_code == 200
        assert after_resp.json()["data"]["falcoEbpfAlerts"] == initial_falco + 1
