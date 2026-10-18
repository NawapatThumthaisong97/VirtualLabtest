"""
Tests for Issue #73:
[Sub-Issue 2] : Billing Aggregation & Anonymized Export API (Backend)

Tests cover:
1. RBAC authorization tests (Admin only, 403 Forbidden for Student/Instructor, 401 Unauthorized for unauthenticated)
2. Billing Aggregation calculations (GROUP BY course, cluster, anon_id)
3. Strict Anonymity verification (Zero PII, deterministic HMAC-SHA256 anon_id)
4. Dedicated Executive Export (CSV with UTF-8 BOM, PDF 1.4 binary stream)
5. Soft-Delete report history (deleted_at recorded, excluded from list, row remains in DB, 404 for missing)
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import io
import uuid

from fastapi import FastAPI, status as http_status
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jose import jwt
import pytest

from app.configs.db import get_db
from app.configs.settings import settings
from app.exceptions.domain import DomainError
from app.main import STATUS_MAP
from app.models.billing_report import BillingReport
from app.models.courses import Course
from app.models.lab import Lab, RunTarget
from app.models.rbac import Role, UserRoleAssignment
from app.models.session import Session as SessionModel, SessionStatus, ServiceType
from app.models.usage_record import UsageRecord
from app.models.user import User, UserRole
from app.routes import api_router
from app.seeds.rbac_seed import RBACSeeder


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

    role_name = role.value.capitalize()
    role_row = db.query(Role).filter(Role.role_name == role_name).first()
    if role_row:
        assignment = UserRoleAssignment(user_id=user.id, role_id=role_row.id)
        db.add(assignment)
    db.commit()
    return user, make_user_token(user)


@pytest.fixture
def populated_billing_data(db, seed_rbac):
    """
    Populate a rich set of courses, labs, sessions, and usage records
    to test aggregations by course, cluster, and anon_id.
    """
    admin_user, admin_token = create_role_user(db, "admin@tu.ac.th", UserRole.ADMIN)
    student1, student1_token = create_role_user(db, "student1_6709616001@dome.tu.ac.th", UserRole.STUDENT)
    student2, student2_token = create_role_user(db, "student2_6709616002@dome.tu.ac.th", UserRole.STUDENT)
    instructor, instructor_token = create_role_user(db, "ajarn.somchai@tu.ac.th", UserRole.INSTRUCTOR)

    # 1. Course CS101 and CS202
    course1 = Course(
        id=uuid.uuid4(),
        code="CS101",
        name="Intro to Computer Science",
        lecturer_name="Ajarn Somchai",
        created_by=instructor.id,
    )
    course2 = Course(
        id=uuid.uuid4(),
        code="CS202",
        name="Data Structures & Algorithms",
        lecturer_name="Ajarn Somchai",
        created_by=instructor.id,
    )
    db.add_all([course1, course2])
    db.flush()

    # 2. Labs
    lab1 = Lab(
        id=uuid.uuid4(),
        course_id=course1.id,
        title="Lab 1: Python Basics",
        order_no=1,
        run_target=RunTarget.KUBERNETES,
    )
    lab2 = Lab(
        id=uuid.uuid4(),
        course_id=course2.id,
        title="Lab 2: Trees & Graphs",
        order_no=1,
        run_target=RunTarget.AWS,
    )
    db.add_all([lab1, lab2])
    db.flush()

    # 3. Sessions
    now = datetime.now(timezone.utc)
    # Session 1: Student 1, Lab 1 (CS101), Local K3s, LAB service
    sess1 = SessionModel(
        id=uuid.uuid4(),
        user_id=student1.id,
        lab_id=lab1.id,
        service_type=ServiceType.LAB,
        status=SessionStatus.STOPPED,
        is_cloud=False,
    )
    # Session 2: Student 2, Lab 2 (CS202), Cloud AWS, COMPUTE_SERVICE
    sess2 = SessionModel(
        id=uuid.uuid4(),
        user_id=student2.id,
        lab_id=lab2.id,
        service_type=ServiceType.COMPUTE_SERVICE,
        status=SessionStatus.STOPPED,
        is_cloud=True,
    )
    # Session 3: Student 1, Lab 2 (CS202), Cloud AWS, AI_TRAINING
    sess3 = SessionModel(
        id=uuid.uuid4(),
        user_id=student1.id,
        lab_id=lab2.id,
        service_type=ServiceType.AI_TRAINING,
        status=SessionStatus.STOPPED,
        is_cloud=True,
    )
    db.add_all([sess1, sess2, sess3])
    db.flush()

    # 4. Usage Records
    rec1 = UsageRecord(
        session_id=sess1.id,
        cpu_seconds=7200,      # 2.0 hours
        gpu_seconds=0,         # 0 hours
        ram_mb_hours=Decimal("4096.00"),
        is_cloud_burst=False,
        est_cost_thb=Decimal("30.50"),
        recorded_at=now - timedelta(days=2),
    )
    rec2 = UsageRecord(
        session_id=sess2.id,
        cpu_seconds=14400,     # 4.0 hours
        gpu_seconds=3600,      # 1.0 hour
        ram_mb_hours=Decimal("8192.00"),
        is_cloud_burst=True,
        est_cost_thb=Decimal("150.00"),
        recorded_at=now - timedelta(days=1),
    )
    rec3 = UsageRecord(
        session_id=sess3.id,
        cpu_seconds=3600,      # 1.0 hour
        gpu_seconds=7200,      # 2.0 hours
        ram_mb_hours=Decimal("16384.00"),
        is_cloud_burst=True,
        est_cost_thb=Decimal("250.75"),
        recorded_at=now,
    )
    db.add_all([rec1, rec2, rec3])
    db.commit()

    return {
        "admin_user": admin_user,
        "admin_token": admin_token,
        "student1": student1,
        "student1_token": student1_token,
        "student2": student2,
        "student2_token": student2_token,
        "instructor": instructor,
        "instructor_token": instructor_token,
        "course1": course1,
        "course2": course2,
        "total_cost": 30.50 + 150.00 + 250.75,  # 431.25 THB
    }


# =====================================================================
# Group 1: RBAC Access Control Tests
# =====================================================================

class TestRBACBilling:
    """Verify Admin-only access and proper 401/403 rejections"""

    def test_unauthenticated_request_fails_with_401(self, client):
        """Unauthenticated requests are rejected with 401"""
        resp = client.get("/api/v1/billing/summary")
        assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED

        resp_export = client.get("/api/v1/billing/export")
        assert resp_export.status_code == http_status.HTTP_401_UNAUTHORIZED

        resp_reports = client.get("/api/v1/billing/reports")
        assert resp_reports.status_code == http_status.HTTP_401_UNAUTHORIZED

    def test_student_gets_403_forbidden(self, client, populated_billing_data):
        """Students cannot access any billing endpoints"""
        headers = {"Authorization": f"Bearer {populated_billing_data['student1_token']}"}

        resp = client.get("/api/v1/billing/summary", headers=headers)
        assert resp.status_code == http_status.HTTP_403_FORBIDDEN

        resp = client.get("/api/v1/billing/export?format=csv", headers=headers)
        assert resp.status_code == http_status.HTTP_403_FORBIDDEN

        resp = client.get("/api/v1/billing/reports", headers=headers)
        assert resp.status_code == http_status.HTTP_403_FORBIDDEN

        resp = client.delete(f"/api/v1/billing/reports/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == http_status.HTTP_403_FORBIDDEN

    def test_instructor_gets_403_forbidden(self, client, populated_billing_data):
        """Instructors cannot access global billing aggregation endpoints"""
        headers = {"Authorization": f"Bearer {populated_billing_data['instructor_token']}"}

        resp = client.get("/api/v1/billing/summary", headers=headers)
        assert resp.status_code == http_status.HTTP_403_FORBIDDEN

        resp = client.get("/api/v1/billing/export?format=csv", headers=headers)
        assert resp.status_code == http_status.HTTP_403_FORBIDDEN

    def test_admin_can_access_billing_summary(self, client, populated_billing_data):
        """Admin can access summary endpoints successfully"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}

        resp_v1 = client.get("/api/v1/billing/summary", headers=headers)
        assert resp_v1.status_code == http_status.HTTP_200_OK
        data = resp_v1.json()
        assert data["success"] is True

        resp_legacy = client.get("/api/billing/summary", headers=headers)
        assert resp_legacy.status_code == http_status.HTTP_200_OK

    def test_admin_can_access_plural_endpoints(self, client, populated_billing_data):
        """Admin can access plural endpoints (/api/v1/billings and /api/v1/billings/exports)"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}

        resp_plural = client.get("/api/v1/billings", headers=headers)
        assert resp_plural.status_code == http_status.HTTP_200_OK
        assert resp_plural.json()["success"] is True

        resp_plural_reports = client.get("/api/v1/billings/reports", headers=headers)
        assert resp_plural_reports.status_code == http_status.HTTP_200_OK


# =====================================================================
# Group 2: Billing Aggregation & Calculations Tests
# =====================================================================

class TestBillingAggregation:
    """Verify accurate aggregation by course, cluster, and anon_id"""

    def test_aggregate_by_course(self, client, populated_billing_data):
        """Aggregate total costs, sessions, and resource hours by course"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billing/summary?group_by=course", headers=headers)
        assert resp.status_code == http_status.HTTP_200_OK

        payload = resp.json()["data"]
        assert payload["groupBy"] == "course"
        assert payload["totalSessions"] == 3
        assert payload["totalCostThb"] == pytest.approx(431.25, 0.01)
        assert payload["totalCpuHours"] == pytest.approx(7.0, 0.1)  # (7200 + 14400 + 3600) / 3600 = 7.0
        assert payload["totalGpuHours"] == pytest.approx(3.0, 0.1)  # (0 + 3600 + 7200) / 3600 = 3.0

        items = payload["items"]
        assert len(items) == 2

        # CS202 has rec2 (150.00) + rec3 (250.75) = 400.75 THB
        cs202_item = next(it for it in items if it["groupKey"] == "CS202")
        assert cs202_item["totalSessions"] == 2
        assert cs202_item["totalCostThb"] == pytest.approx(400.75, 0.01)
        assert cs202_item["totalGpuHours"] == pytest.approx(3.0, 0.1)

        # CS101 has rec1 (30.50 THB)
        cs101_item = next(it for it in items if it["groupKey"] == "CS101")
        assert cs101_item["totalSessions"] == 1
        assert cs101_item["totalCostThb"] == pytest.approx(30.50, 0.01)
        assert cs101_item["totalCpuHours"] == pytest.approx(2.0, 0.1)

    def test_aggregate_by_cluster(self, client, populated_billing_data):
        """Aggregate by cloud (AWS SkyPilot) vs local (K3s) and service type"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billing/summary?group_by=cluster", headers=headers)
        assert resp.status_code == http_status.HTTP_200_OK

        payload = resp.json()["data"]
        assert payload["groupBy"] == "cluster"
        assert payload["totalCostThb"] == pytest.approx(431.25, 0.01)

        items = payload["items"]
        assert len(items) >= 2

        # Check local K3s entry
        local_item = next(it for it in items if it["isCloud"] is False)
        assert "Local K3s" in local_item["groupName"]
        assert local_item["totalCostThb"] == pytest.approx(30.50, 0.01)

        # Check AWS entries (COMPUTE_SERVICE and AI_TRAINING)
        aws_items = [it for it in items if it["isCloud"] is True]
        assert len(aws_items) == 2
        aws_total_cost = sum(it["totalCostThb"] for it in aws_items)
        assert aws_total_cost == pytest.approx(400.75, 0.01)

    def test_aggregate_by_anon_id_enforces_strict_anonymity(self, client, populated_billing_data):
        """
        Aggregation by anon_id pseudonymizes users with HMAC-SHA256
        and guarantees no real names, emails, or student IDs leak into the payload.
        """
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billing/summary?group_by=anon_id", headers=headers)
        assert resp.status_code == http_status.HTTP_200_OK

        payload = resp.json()["data"]
        assert payload["groupBy"] == "anon_id"
        assert payload["totalSessions"] == 3
        assert payload["totalCostThb"] == pytest.approx(431.25, 0.01)

        items = payload["items"]
        assert len(items) == 2  # student1 and student2

        # Check pseudonymization format
        for item in items:
            assert item["anonId"] is not None
            assert item["anonId"].startswith("anon_")
            assert len(item["anonId"]) == 13
            assert item["groupKey"] == item["anonId"]

        # STRICT ANONYMITY ASSERTIONS:
        raw_json_str = resp.text
        assert "student1_6709616001@dome.tu.ac.th" not in raw_json_str
        assert "student2_6709616002@dome.tu.ac.th" not in raw_json_str
        assert "6709616001" not in raw_json_str
        assert "6709616002" not in raw_json_str
        assert str(populated_billing_data["student1"].id) not in raw_json_str
        assert str(populated_billing_data["student2"].id) not in raw_json_str

    def test_aggregate_by_nat_subnet(self, client, populated_billing_data):
        """Aggregate total costs, sessions, and resource hours by NAT subnet"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billings?group_by=nat_subnet", headers=headers)
        assert resp.status_code == http_status.HTTP_200_OK

        payload = resp.json()["data"]
        assert payload["groupBy"] == "nat_subnet"
        assert payload["totalSessions"] == 3
        assert payload["totalCostThb"] == pytest.approx(431.25, 0.01)

        items = payload["items"]
        assert len(items) >= 2

        # Check AWS cloud subnet (10.0.0.0/16)
        cloud_item = next(it for it in items if it["natSubnet"] == "10.0.0.0/16")
        assert cloud_item["isCloud"] is True
        assert cloud_item["totalSessions"] == 2
        assert cloud_item["totalCostThb"] == pytest.approx(400.75, 0.01)

        # Check local K3s subnet (192.168.1.0/24)
        local_item = next(it for it in items if it["natSubnet"] == "192.168.1.0/24")
        assert local_item["isCloud"] is False
        assert local_item["totalSessions"] == 1
        assert local_item["totalCostThb"] == pytest.approx(30.50, 0.01)

    def test_invalid_group_by_returns_400(self, client, populated_billing_data):
        """Unsupported group_by parameter returns 400 Bad Request"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billing/summary?group_by=invalid_group", headers=headers)
        assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


# =====================================================================
# Group 3: Executive Export Endpoints (CSV & PDF)
# =====================================================================

class TestBillingExport:
    """Verify CSV (with BOM) and PDF exports for executive consumption"""

    def test_export_csv_has_bom_and_strict_anonymity(self, client, populated_billing_data):
        """Export CSV returns UTF-8 with BOM, proper headers, and zero PII"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billing/export?format=csv&group_by=course", headers=headers)
        assert resp.status_code == http_status.HTTP_200_OK

        # Check headers
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert "billing_report_course_" in resp.headers["content-disposition"]

        content = resp.content
        # Verify UTF-8 BOM
        assert content.startswith(b"\xef\xbb\xbf")

        decoded_text = content.decode("utf-8-sig")
        assert "# REPORT TITLE" in decoded_text
        assert "STRICT ANONYMIZED REPORT" in decoded_text
        assert "CS101" in decoded_text
        assert "CS202" in decoded_text
        assert "431.25" in decoded_text

        # Strict anonymity in CSV export
        assert "student1_6709616001" not in decoded_text
        assert "6709616001" not in decoded_text
        assert str(populated_billing_data["student1"].id) not in decoded_text

    def test_export_pdf_returns_valid_pdf_stream(self, client, populated_billing_data):
        """Export PDF returns valid PDF 1.4 binary stream with strict anonymity"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billing/export?format=pdf&group_by=anon_id", headers=headers)
        assert resp.status_code == http_status.HTTP_200_OK

        assert resp.headers["content-type"] == "application/pdf"
        assert "attachment" in resp.headers["content-disposition"]
        assert "billing_report_anon_id_" in resp.headers["content-disposition"]

        content = resp.content
        assert content.startswith(b"%PDF-1.4")
        assert b"%%EOF" in content
        assert b"anon_" in content

        # Strict anonymity in PDF export
        content_latin1 = content.decode("latin-1", errors="replace")
        assert "student1_6709616001" not in content_latin1
        assert "6709616001" not in content_latin1
        assert str(populated_billing_data["student1"].id) not in content_latin1

    def test_export_invalid_format_returns_400(self, client, populated_billing_data):
        """Invalid format like 'docx' returns 400 Bad Request"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billing/export?format=docx", headers=headers)
        assert resp.status_code == http_status.HTTP_400_BAD_REQUEST

    def test_export_plural_endpoint_and_nat_subnet(self, client, populated_billing_data):
        """Plural export endpoint /api/v1/billings/exports with nat_subnet grouping"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        resp = client.get("/api/v1/billings/exports?format=csv&group_by=nat_subnet", headers=headers)
        assert resp.status_code == http_status.HTTP_200_OK

        assert "text/csv" in resp.headers["content-type"]
        assert resp.content.startswith(b"\xef\xbb\xbf")

        decoded_text = resp.content.decode("utf-8-sig")
        assert "NAT_SUBNET" in decoded_text
        assert "10.0.0.0/16" in decoded_text
        assert "192.168.1.0/24" in decoded_text


# =====================================================================
# Group 4: Report History & Soft-Delete Operations
# =====================================================================

class TestBillingReportHistoryAndSoftDelete:
    """Verify creation, listing, and soft-delete mechanics for billing reports"""

    def test_export_records_report_history_and_soft_delete_works(self, client, db, populated_billing_data):
        """
        1. Calling export creates a BillingReport audit record.
        2. Listing reports displays the record.
        3. DELETE soft-deletes the report (sets deleted_at, does not delete row).
        4. Subsequent list omits the soft-deleted report.
        """
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}

        # 1. Trigger export to create report record
        export_resp = client.get("/api/v1/billing/export?format=csv&group_by=course", headers=headers)
        assert export_resp.status_code == http_status.HTTP_200_OK

        # 2. List reports
        list_resp = client.get("/api/v1/billing/reports", headers=headers)
        assert list_resp.status_code == http_status.HTTP_200_OK
        data = list_resp.json()["data"]
        assert data["total"] >= 1
        created_report = data["reports"][0]
        report_id = created_report["id"]
        assert created_report["isDeleted"] is False

        # 3. Perform Soft-Delete
        del_resp = client.delete(f"/api/v1/billing/reports/{report_id}", headers=headers)
        assert del_resp.status_code == http_status.HTTP_200_OK
        del_data = del_resp.json()["data"]
        assert del_data["isDeleted"] is True

        # 4. Verify in DB directly: row still exists, deleted_at is set!
        db_report = db.query(BillingReport).filter(BillingReport.id == uuid.UUID(report_id)).first()
        assert db_report is not None, "Report must NOT be physically deleted from database"
        assert db_report.deleted_at is not None, "Report must have deleted_at timestamp set"
        assert db_report.is_deleted is True

        # 5. Verify list endpoint excludes soft-deleted reports
        list_resp_after = client.get("/api/v1/billing/reports", headers=headers)
        assert list_resp_after.status_code == http_status.HTTP_200_OK
        reports_after = list_resp_after.json()["data"]["reports"]
        assert all(r["id"] != report_id for r in reports_after)

    def test_soft_delete_non_existent_report_returns_404(self, client, populated_billing_data):
        """Attempting to soft-delete a non-existent or already deleted report returns 404"""
        headers = {"Authorization": f"Bearer {populated_billing_data['admin_token']}"}
        random_id = uuid.uuid4()
        del_resp = client.delete(f"/api/v1/billing/reports/{random_id}", headers=headers)
        assert del_resp.status_code == http_status.HTTP_404_NOT_FOUND
