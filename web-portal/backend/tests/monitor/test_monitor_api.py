"""
Tests for Issue #72:
[Sub-Issue 1] : API for Cluster Metrics, Critical Logs & Security Counters (Backend)

Tests include:
1. LogMaskerService unit tests (HMAC-SHA256 pseudonymization, PII masking, Source Code stripping)
2. MonitorService & Repository calculation, grouping by AWS/K3s NAT subnets
3. RBAC authorization tests (Admin only, 403 for Student/Instructor, 401 for unauthenticated)
4. RESTful endpoints (/api/v1/metrics, /api/metrics, /api/v1/logs, /api/logs, /api/v1/metrics/security-counters)
5. Read-only verification (No mutating endpoints exist)
"""

from datetime import datetime, timezone, timedelta
import uuid
from typing import Optional

from fastapi import FastAPI, status as http_status
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jose import jwt
import pytest

from app.configs.db import get_db
from app.configs.settings import settings
from app.exceptions.domain import DomainError
from app.main import STATUS_MAP
from app.models.courses import Course
from app.models.lab import Lab, RunTarget
from app.models.lab_image import LabImage
from app.models.rbac import Permission, Role, RolePermission, UserRoleAssignment
from app.models.session import Session as SessionModel, SessionStatus, ServiceType
from app.models.user import User, UserRole
from app.routes import api_router
from app.seeds.rbac_seed import RBACSeeder
from app.services.log_masker_service import LogMaskerService
from app.services.monitor_service import MonitorService


@pytest.fixture(autouse=True)
def fixed_auth_settings(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-salt-for-hmac-sha256")
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
def seed_rbac(db):
    """Seed RBAC permissions and roles into test database"""
    seeder = RBACSeeder(db)
    seeder.seed()
    db.commit()


def make_user_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_role_user(db, email: str, role: UserRole) -> tuple[User, str]:
    user = User(
        id=uuid.uuid4(),
        email=email,
        name=f"User {role.value}",
        role=role,
    )
    db.add(user)
    db.flush()

    # Assign RBAC role
    role_name = role.value.capitalize()
    role_row = db.query(Role).filter(Role.role_name == role_name).first()
    if role_row:
        assignment = UserRoleAssignment(user_id=user.id, role_id=role_row.id)
        db.add(assignment)
    db.commit()
    return user, make_user_token(user)


# =====================================================================
# Group 1: LogMaskerService Data Masking & Pseudonymization
# =====================================================================

class TestLogMaskerService:
    """LogMaskerService Data Masking, PII Redaction, and HMAC-SHA256 Pseudonymization"""

    def test_pseudonymize_user_id_is_deterministic_and_one_way(self):
        """HMAC-SHA256 pseudonymization produces anon_<8-char> and is deterministic"""
        masker = LogMaskerService(secret_key="secret-key-salt-with-at-least-32-chars-long")
        uid = uuid.uuid4()

        anon_1 = masker.pseudonymize_user_id(uid)
        anon_2 = masker.pseudonymize_user_id(uid)

        assert anon_1 is not None
        assert anon_1.startswith("anon_")
        assert len(anon_1) == 13  # "anon_" (5) + 8 hex chars = 13
        assert anon_1 == anon_2

        # Different user yields different anon_id
        uid_different = uuid.uuid4()
        assert masker.pseudonymize_user_id(uid_different) != anon_1

        # None or empty returns None
        assert masker.pseudonymize_user_id(None) is None
        assert masker.pseudonymize_user_id("") is None

    def test_secret_key_length_validation_rejects_weak_keys(self):
        """Secret key < 32 chars or empty raises ValueError"""
        with pytest.raises(ValueError, match="SECRET_KEY must be configured"):
            LogMaskerService(secret_key="too-short")

        with pytest.raises(ValueError, match="SECRET_KEY must be configured"):
            LogMaskerService(secret_key="")

    def test_mask_pii_redacts_emails_and_student_ids(self):
        """PII such as student emails and 10-digit student IDs are redacted"""
        masker = LogMaskerService()
        raw_msg = "Student 6709616099 (sophia.dav@dome.tu.ac.th) triggered boundary policy"
        masked = masker.mask_text(raw_msg)

        assert "sophia.dav@dome.tu.ac.th" not in masked
        assert "6709616099" not in masked
        assert "[REDACTED_EMAIL]" in masked
        assert "[REDACTED_STUDENT_ID]" in masked

    def test_mask_source_code_strips_code_blocks_and_pod_traces(self):
        """Source code inside pods, markdown blocks, and python traces are stripped"""
        masker = LogMaskerService()
        raw_trace = (
            "Error inside user pod:\n"
            "```python\n"
            "import os\n"
            "print(os.environ['SECRET_KEY'])\n"
            "```\n"
            'File "/home/student/lab.py", line 42, in <module>\n'
            "    raise RuntimeError('Crash')\n"
        )
        masked = masker.mask_text(raw_trace)

        assert "import os" not in masked
        assert "print(os.environ" not in masked
        assert "[REDACTED_SOURCE_CODE]" in masked

    def test_mask_log_record_removes_pii_fields_and_adds_anon_id(self):
        """Record dict removes PII fields (name, email) and replaces user_id with anon_id"""
        masker = LogMaskerService()
        raw_record = {
            "id": "event-1",
            "user_id": str(uuid.uuid4()),
            "email": "student@dome.tu.ac.th",
            "name": "Jane Doe",
            "student_id": "6709616001",
            "message": "User Jane Doe from student@dome.tu.ac.th started interactive session",
            "source": "worker-01",
        }

        masked = masker.mask_log_record(raw_record)

        assert "email" not in masked
        assert "name" not in masked
        assert "student_id" not in masked
        assert "user_id" not in masked
        assert "anon_id" in masked
        assert masked["anon_id"].startswith("anon_")
        assert "student@dome.tu.ac.th" not in masked["message"]


# =====================================================================
# Group 2: RBAC Protection & Read-Only Constraint
# =====================================================================

class TestMonitorRBAC:
    """RBAC Middleware authorization and Read-Only verification for monitoring endpoints"""

    def test_unauthenticated_request_rejected(self, client):
        """Unauthenticated request to /api/v1/metrics returns 401 Unauthorized"""
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED

    def test_student_and_instructor_rejected_with_403(self, db, client, seed_rbac):
        """Student and Instructor roles receive 403 Forbidden on metrics and logs"""
        _, student_token = create_role_user(db, "student@dome.tu.ac.th", UserRole.STUDENT)
        _, instructor_token = create_role_user(db, "prof@tu.ac.th", UserRole.INSTRUCTOR)

        # Student
        resp_s_metrics = client.get(
            "/api/v1/metrics",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp_s_metrics.status_code == http_status.HTTP_403_FORBIDDEN

        resp_s_logs = client.get(
            "/api/v1/logs",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp_s_logs.status_code == http_status.HTTP_403_FORBIDDEN

        # Instructor
        resp_i = client.get(
            "/api/v1/metrics",
            headers={"Authorization": f"Bearer {instructor_token}"},
        )
        assert resp_i.status_code == http_status.HTTP_403_FORBIDDEN

    def test_admin_authorized_for_metrics_and_logs(self, db, client, seed_rbac):
        """Admin role succeeds with 200 OK on both metrics and logs endpoints"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)

        resp_metrics = client.get(
            "/api/v1/metrics",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp_metrics.status_code == http_status.HTTP_200_OK
        assert resp_metrics.json()["success"] is True

        resp_logs = client.get(
            "/api/v1/logs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp_logs.status_code == http_status.HTTP_200_OK
        assert resp_logs.json()["success"] is True

    def test_read_only_constraint_rejects_mutations(self, db, client, seed_rbac):
        """Constraint: Read-only nature for UI rejects PUT, DELETE, PATCH with 405 Method Not Allowed"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)
        headers = {"Authorization": f"Bearer {admin_token}"}

        assert client.post("/api/v1/metrics", headers=headers).status_code == 405
        assert client.delete("/api/v1/metrics", headers=headers).status_code == 405
        assert client.put("/api/v1/logs", headers=headers).status_code == 405
        assert client.delete("/api/v1/logs", headers=headers).status_code == 405
        assert client.delete("/api/v1/metrics/security-counters", headers=headers).status_code == 405


# =====================================================================
# Group 3: Cluster Resource Allocation Metrics & NAT Subnets
# =====================================================================

class TestClusterMetrics:
    """Cluster Resource Metrics API for CPU, RAM, Active Sessions, and NAT Subnet filtering"""

    def test_metrics_summary_and_provider_structure(self, db, client, seed_rbac):
        """GET /api/v1/metrics returns summary, byProvider (AWS + Local K3s), and CamelCase payload"""
        admin, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)

        # Seed sample active sessions
        course = Course(
            code="CS101",
            name="Intro to Computer Science",
            lecturer_name="Dr. Smith",
            created_by=admin.id,
        )
        db.add(course)
        db.flush()

        img_k3s = LabImage(
            uploaded_by=admin.id,
            course_id=course.id,
            repository="skypilot/k3s-lab",
            tag="v1",
            image_digest=f"sha256:{uuid.uuid4().hex}",
            size_mb=4096,
            cpu_requirement="2",
        )
        img_aws = LabImage(
            uploaded_by=admin.id,
            course_id=course.id,
            repository="vlab/aws-lab",
            tag="v1",
            image_digest=f"sha256:{uuid.uuid4().hex}",
            size_mb=8192,
            cpu_requirement="4",
        )
        db.add_all([img_k3s, img_aws])
        db.flush()

        lab_k3s = Lab(
            course_id=course.id,
            title="K3s Lab",
            order_no=1,
            image_id=img_k3s.id,
            run_target=RunTarget.KUBERNETES,
        )
        lab_aws = Lab(
            course_id=course.id,
            title="AWS Lab",
            order_no=2,
            image_id=img_aws.id,
            run_target=RunTarget.AWS,
        )
        db.add_all([lab_k3s, lab_aws])
        db.flush()

        # Session on Local K3s in Lab Room 1
        s1 = SessionModel(
            user_id=admin.id,
            lab_id=lab_k3s.id,
            lab_image_id=img_k3s.id,
            service_type=ServiceType.LAB,
            status=SessionStatus.RUNNING,
            node_name="k3s-worker-lab1-01",
            is_cloud=False,
        )
        # Session on AWS
        s2 = SessionModel(
            user_id=admin.id,
            lab_id=lab_aws.id,
            lab_image_id=img_aws.id,
            service_type=ServiceType.LAB,
            status=SessionStatus.RUNNING,
            node_name="skypilot-aws-node-01",
            is_cloud=True,
        )
        db.add_all([s1, s2])
        db.commit()

        resp = client.get(
            "/api/v1/metrics",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        data = body["data"]
        assert "summary" in data
        assert "byProvider" in data
        assert "securityViolationCounters" in data

        # Check CamelCase serialization
        summary = data["summary"]
        assert summary["totalActiveSessions"] >= 2
        assert "cpu" in summary
        assert "ram" in summary
        assert "utilizationPercent" in summary["cpu"]
        assert "utilizationPercent" in summary["ram"]

        # Check byProvider
        providers = {p["provider"]: p for p in data["byProvider"]}
        assert "local_k3s" in providers
        assert "aws" in providers

        k3s_prov = providers["local_k3s"]
        assert k3s_prov["subnets"] is not None
        # Check subnets contain natSubnet and roomName
        subnets_map = {s["natSubnet"]: s for s in k3s_prov["subnets"]}
        assert "192.168.1.0/24" in subnets_map
        assert "roomName" in subnets_map["192.168.1.0/24"]

    def test_metrics_filter_by_provider_and_subnet(self, db, client, seed_rbac):
        """GET /api/v1/metrics supports filtering by provider=aws and nat_subnet"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Filter AWS only
        resp_aws = client.get("/api/v1/metrics?provider=aws", headers=headers)
        assert resp_aws.status_code == 200
        providers_aws = resp_aws.json()["data"]["byProvider"]
        assert len(providers_aws) == 1
        assert providers_aws[0]["provider"] == "aws"

        # Filter Local K3s only
        resp_k3s = client.get("/api/v1/metrics?provider=local_k3s", headers=headers)
        assert resp_k3s.status_code == 200
        providers_k3s = resp_k3s.json()["data"]["byProvider"]
        assert len(providers_k3s) == 1
        assert providers_k3s[0]["provider"] == "local_k3s"

        # Filter specific nat_subnet
        resp_sub = client.get(
            "/api/v1/metrics?provider=local_k3s&nat_subnet=192.168.1.0/24",
            headers=headers,
        )
        assert resp_sub.status_code == 200
        subnets = resp_sub.json()["data"]["byProvider"][0]["subnets"]
        assert len(subnets) == 1
        assert subnets[0]["natSubnet"] == "192.168.1.0/24"


# =====================================================================
# Group 4: Security Violation Counters
# =====================================================================

class TestSecurityCounters:
    """Security Violation Counters API for Squid Egress Drops, Kyverno Blocks, and Tailscale Attempts"""

    def test_security_counters_endpoint(self, db, client, seed_rbac):
        """GET /api/v1/metrics/security-counters returns Squid, Kyverno, and Tailscale counters"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)
        headers = {"Authorization": f"Bearer {admin_token}"}

        resp = client.get("/api/v1/metrics/security-counters", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        data = body["data"]
        assert "squidEgressDrops" in data
        assert "kyvernoPolicyBlocks" in data
        assert "tailscaleCrossClusterAttempts" in data
        assert "totalViolations" in data

        assert data["squidEgressDrops"] >= 0
        assert data["kyvernoPolicyBlocks"] >= 0
        assert data["tailscaleCrossClusterAttempts"] >= 0
        assert data["totalViolations"] == (
            data["squidEgressDrops"]
            + data["kyvernoPolicyBlocks"]
            + data["tailscaleCrossClusterAttempts"]
        )

        # Alternative plural route compatibility check
        resp_alt = client.get("/api/security/counters", headers=headers)
        assert resp_alt.status_code == 200
        assert resp_alt.json()["success"] is True


# =====================================================================
# Group 5: Critical Infrastructure & Security Boundary Logs
# =====================================================================

class TestCriticalLogs:
    """Critical Infrastructure & Boundary Logs API with Data Masking and Pseudonymization"""

    def test_logs_retrieval_and_pseudonymization(self, db, client, seed_rbac):
        """GET /api/v1/logs returns logs without PII and with deterministic anonId"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)
        headers = {"Authorization": f"Bearer {admin_token}"}

        resp = client.get("/api/v1/logs?limit=20", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        data = body["data"]
        assert "logs" in data
        assert "total" in data
        assert len(data["logs"]) > 0

        # Verify every log entry is clean of PII and conforms to CamelCase
        event_types = set()
        for log in data["logs"]:
            assert "id" in log
            assert "timestamp" in log
            assert "severity" in log
            assert "category" in log
            assert "eventType" in log
            assert "source" in log
            assert "message" in log

            # Check that PII is never exposed
            assert "user_id" not in log
            assert "userId" not in log
            assert "email" not in log
            assert "studentId" not in log

            # If anonId is present, verify format
            if log.get("anonId"):
                assert log["anonId"].startswith("anon_")

            # Check message does not leak raw emails or code blocks
            msg = log["message"]
            assert "@dome.tu.ac.th" not in msg
            assert "```" not in msg

            event_types.add(log["eventType"])

        # Must include critical events and security violations
        assert "NODE_DOWN" in event_types
        assert "SQUID_EGRESS_DROP" in event_types
        assert "OPA_KYVERNO_BLOCK" in event_types

    def test_logs_filter_by_severity_and_category(self, db, client, seed_rbac):
        """GET /api/v1/logs supports filtering by severity and category"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Filter CRITICAL only
        resp_crit = client.get("/api/v1/logs?severity=CRITICAL", headers=headers)
        assert resp_crit.status_code == 200
        logs_crit = resp_crit.json()["data"]["logs"]
        for item in logs_crit:
            assert item["severity"] == "CRITICAL"

        # Filter SECURITY_VIOLATION only
        resp_sec = client.get("/api/v1/logs?category=SECURITY_VIOLATION", headers=headers)
        assert resp_sec.status_code == 200
        logs_sec = resp_sec.json()["data"]["logs"]
        for item in logs_sec:
            assert item["category"] == "SECURITY_VIOLATION"

        # Filter by event_type
        resp_node = client.get("/api/v1/logs?event_type=NODE_DOWN", headers=headers)
        assert resp_node.status_code == 200
        logs_node = resp_node.json()["data"]["logs"]
        for item in logs_node:
            assert item["eventType"] == "NODE_DOWN"


# =====================================================================
# Group 6: Log Ingestion from Collector (POST /api/v1/logs)
# =====================================================================

class TestLogIngestion:
    """Collector Log Ingestion with Data Masking, Pseudonymization, and Storage"""

    def test_ingest_log_masks_pii_and_pseudonymizes_user_id(self, db, client, seed_rbac):
        """Collector posts raw log with PII & code, backend sanitizes and persists it"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)
        headers = {"Authorization": f"Bearer {admin_token}"}
        user_uuid = str(uuid.uuid4())

        payload = {
            "severity": "CRITICAL",
            "category": "SECURITY_VIOLATION",
            "eventType": "SQUID_EGRESS_DROP",
            "source": "squid-proxy-edge",
            "message": "Student 6709616099 (sophia.dav@dome.tu.ac.th) tried illegal egress with script:\n```python\nimport socket\ns=socket.socket()\n```",
            "userId": user_uuid,
            "clusterOrSubnet": "192.168.1.0/24",
            "metadata": {"destination": "malicious.example.com", "port": 443},
        }

        resp = client.post("/api/v1/logs", json=payload, headers=headers)
        assert resp.status_code == http_status.HTTP_201_CREATED
        data = resp.json()["data"]

        # 1. PII and Source Code are masked
        assert "sophia.dav@dome.tu.ac.th" not in data["message"]
        assert "6709616099" not in data["message"]
        assert "import socket" not in data["message"]
        assert "[REDACTED_EMAIL]" in data["message"]
        assert "[REDACTED_STUDENT_ID]" in data["message"]
        assert "[REDACTED_SOURCE_CODE]" in data["message"]

        # 2. anon_id is generated and raw user_id is NOT returned
        assert data["anonId"] is not None
        assert data["anonId"].startswith("anon_")
        assert len(data["anonId"]) == 13
        assert "userId" not in data

    def test_ingest_log_increments_security_counters(self, db, client, seed_rbac):
        """Ingesting security violation log increments security violation counter"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Check initial counter
        resp_before = client.get("/api/v1/metrics/security-counters", headers=headers)
        initial_squid = resp_before.json()["data"]["squidEgressDrops"]

        # Ingest Squid drop log
        payload = {
            "severity": "WARNING",
            "category": "SECURITY_VIOLATION",
            "eventType": "SQUID_EGRESS_DROP",
            "source": "squid-proxy",
            "message": "Dropped external connection",
            "clusterOrSubnet": "192.168.1.0/24",
        }
        resp = client.post("/api/v1/logs", json=payload, headers=headers)
        assert resp.status_code == http_status.HTTP_201_CREATED

        # Verify counter incremented
        resp_after = client.get("/api/v1/metrics/security-counters", headers=headers)
        after_squid = resp_after.json()["data"]["squidEgressDrops"]
        assert after_squid == initial_squid + 1

    def test_ingest_log_persists_in_db_and_shows_in_get_logs(self, db, client, seed_rbac):
        """Ingested log is persisted in database and queryable via GET /api/v1/logs"""
        _, admin_token = create_role_user(db, "admin@dome.tu.ac.th", UserRole.ADMIN)
        headers = {"Authorization": f"Bearer {admin_token}"}

        unique_source = f"k3s-worker-test-{uuid.uuid4().hex[:6]}"
        payload = {
            "severity": "CRITICAL",
            "category": "INFRASTRUCTURE",
            "eventType": "NODE_DOWN",
            "source": unique_source,
            "message": "Node heartbeat timeout detected",
            "clusterOrSubnet": "192.168.1.0/24",
        }
        post_resp = client.post("/api/v1/logs", json=payload, headers=headers)
        assert post_resp.status_code == http_status.HTTP_201_CREATED
        created_id = post_resp.json()["data"]["id"]

        # Verify queryable in GET /api/v1/logs
        get_resp = client.get("/api/v1/logs?event_type=NODE_DOWN", headers=headers)
        assert get_resp.status_code == http_status.HTTP_200_OK
        logs = get_resp.json()["data"]["logs"]
        matching = [l for l in logs if l["id"] == created_id]
        assert len(matching) == 1
        assert matching[0]["source"] == unique_source

    def test_ingest_log_forbidden_for_student_and_instructor(self, db, client, seed_rbac):
        """Students and Instructors cannot push logs to /api/v1/logs"""
        _, student_token = create_role_user(db, "student@dome.tu.ac.th", UserRole.STUDENT)
        _, instructor_token = create_role_user(db, "prof@tu.ac.th", UserRole.INSTRUCTOR)

        payload = {
            "severity": "INFO",
            "category": "INFRASTRUCTURE",
            "eventType": "TEST_EVENT",
            "source": "fake-source",
            "message": "test",
        }

        resp_s = client.post(
            "/api/v1/logs",
            json=payload,
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp_s.status_code == http_status.HTTP_403_FORBIDDEN

        resp_i = client.post(
            "/api/v1/logs",
            json=payload,
            headers={"Authorization": f"Bearer {instructor_token}"},
        )
        assert resp_i.status_code == http_status.HTTP_403_FORBIDDEN

