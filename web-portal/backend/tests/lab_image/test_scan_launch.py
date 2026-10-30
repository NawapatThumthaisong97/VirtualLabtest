"""เปิด Job สแกนจาก scan_reconciler.launch_queued (FakeK8s / FakeR2 ไม่ต่อ cluster จริง)"""
import uuid
from datetime import datetime, timezone

import pytest

from app.configs.settings import settings
from app.models.lab_image import ImageStatus, LabImage, ScanStatus
from app.repositories.lab_image_repository import LabImageRepository
from app.services.lab_image_service import LabImageService
from app.services.scan_job_service import build_scan_job, scan_job_name
from app.services.scan_reconciler import ScanReconciler
from tests.fakes import FakeK8s

RUNNER = "100.64.0.3:5001/vlab/scan-runner@sha256:" + "a" * 64
ETAG = "0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def scan_settings(monkeypatch):
    monkeypatch.setattr(settings, "SCAN_RUNNER_IMAGE", RUNNER)
    monkeypatch.setattr(settings, "DOCKER_REGISTRY_HOST", "100.64.0.3:5001")
    # .env ของเครื่องที่รัน test อาจตั้งค่าพวกนี้ไว้ ให้ทุก test เริ่มจากค่าเริ่มต้น
    monkeypatch.setattr(settings, "REGISTRY_PUSH_HOST", None)
    monkeypatch.setattr(settings, "REGISTRY_PUSH_PORT", 5002)
    monkeypatch.setattr(settings, "SCAN_PUSH_SECRET", "registry-push")
    monkeypatch.setattr(settings, "SCAN_NODE_SELECTOR", {"node-role.kubernetes.io/control-plane": "true"})
    monkeypatch.setattr(settings, "SCAN_MAX_CONCURRENT", 2)
    monkeypatch.setattr(settings, "SCAN_MAX_ATTEMPTS", 2)


@pytest.fixture
def k8s():
    return FakeK8s()


@pytest.fixture
def queued(db, world):
    def _make(**overrides):
        fields = dict(
            id=uuid.uuid4(), uploaded_by=world.owner.id, course_id=world.course.id,
            repository="skypilot/scan-test", tag=f"lab-{uuid.uuid4().hex[:6]}", size_mb=10,
            status=ImageStatus.PENDING, scan_status=ScanStatus.QUEUED, exposed_ports=[8080, 5173],
            archive_key=f"lab-images/{uuid.uuid4().hex}_image.tar", archive_etag=ETAG,
            archive_size_bytes=10 * 1024 * 1024, archive_uploaded_at=datetime.now(timezone.utc),
        )
        fields.update(overrides)
        image = LabImage(**fields)
        db.add(image)
        db.commit()
        return image
    return _make


def reconcile(db, k8s, fake_r2):
    repo = LabImageRepository(db)
    return ScanReconciler(db, repo, LabImageService(db, repo, fake_r2), fake_r2, k8s).run()


def test_launch_creates_job_and_secret_and_marks_running(db, k8s, fake_r2, queued):
    image = queued()
    result = reconcile(db, k8s, fake_r2)

    db.refresh(image)
    name = scan_job_name(image, 1)
    assert result.launched == [str(image.id)]
    assert image.scan_status is ScanStatus.RUNNING
    assert image.scan_attempts == 1
    assert image.scan_job_name == name
    assert image.scan_started_at is not None

    job = k8s.created_jobs[name]
    assert job["metadata"]["labels"]["vlab/scan"] == "true"
    assert job["spec"]["template"]["metadata"]["labels"]["vlab/scan"] == "true"
    assert job["spec"]["backoffLimit"] == 0

    secret = k8s.secrets[name]
    assert secret["stringData"]["download_url"].startswith("https://fake-r2.test/" + image.archive_key)
    assert secret["metadata"]["ownerReferences"][0]["uid"] == f"uid-{name}"
    assert fake_r2.presigned[-1] == {
        "key": image.archive_key, "method": "GET", "expires_in": settings.SCAN_DOWNLOAD_URL_TTL_SECONDS,
    }


def test_job_manifest_is_hardened_and_scopes_secret_to_fetch(make_image):
    image = make_image(id=uuid.uuid4(), archive_etag=ETAG, archive_size_bytes=123, exposed_ports=[8080])
    job = build_scan_job(image, "scan-x")
    pod = job["spec"]["template"]["spec"]

    assert pod["automountServiceAccountToken"] is False
    assert pod["enableServiceLinks"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert [c["name"] for c in pod["initContainers"]] == ["fetch", "validate", "scan"]
    assert [c["name"] for c in pod["containers"]] == ["publish"]

    for container in pod["initContainers"] + pod["containers"]:
        ctx = container["securityContext"]
        assert ctx["readOnlyRootFilesystem"] is True
        assert ctx["allowPrivilegeEscalation"] is False
        assert ctx["capabilities"] == {"drop": ["ALL"]}
        assert container["image"] == RUNNER
        mounts = {m["mountPath"] for m in container["volumeMounts"]}
        # URL ที่เซ็นแล้วเห็นได้เฉพาะ fetch, credential ของ registry เห็นได้เฉพาะ publish
        assert ("/secrets/fetch" in mounts) == (container["name"] == "fetch")
        assert ("/secrets/push" in mounts) == (container["name"] == "publish")

    envs = {c["name"]: {e["name"]: e["value"] for e in c["env"]} for c in pod["initContainers"] + pod["containers"]}
    assert envs["fetch"]["EXPECTED_SIZE"] == "123"
    assert envs["validate"]["DECLARED_PORTS"] == "8080"
    assert envs["publish"]["REPOSITORY"] == image.repository
    # push ผ่าน push port ไม่ใช่ pull port ที่เป็น read-only
    assert envs["publish"]["REGISTRY"] == "100.64.0.3:5002"
    assert "REGISTRY" not in envs["scan"]
    # รหัสไม่อยู่ใน env ของ container ไหนเลย
    assert not any("PASSWORD" in name for env in envs.values() for name in env)

    push = next(v for v in pod["volumes"] if v["name"] == "push-credentials")
    assert push["secret"]["secretName"] == "registry-push"
    assert push["secret"]["defaultMode"] == 0o400
    assert pod["nodeSelector"] == {"node-role.kubernetes.io/control-plane": "true"}


def test_node_selector_can_be_disabled(make_image, monkeypatch):
    monkeypatch.setattr(settings, "SCAN_NODE_SELECTOR", {})
    image = make_image(id=uuid.uuid4(), archive_etag=ETAG, archive_size_bytes=123)
    assert "nodeSelector" not in build_scan_job(image, "scan-x")["spec"]["template"]["spec"]


def test_registry_push_host_defaults_from_pull_host(monkeypatch):
    assert settings.registry_push_host == "100.64.0.3:5002"
    monkeypatch.setattr(settings, "REGISTRY_PUSH_PORT", 6000)
    assert settings.registry_push_host == "100.64.0.3:6000"
    monkeypatch.setattr(settings, "REGISTRY_PUSH_HOST", "registry.lab:5002")
    assert settings.registry_push_host == "registry.lab:5002"
    monkeypatch.setattr(settings, "REGISTRY_PUSH_HOST", None)
    monkeypatch.setattr(settings, "DOCKER_REGISTRY_HOST", None)
    assert settings.registry_push_host is None


def test_respects_max_concurrent(db, k8s, fake_r2, queued):
    for _ in range(3):
        queued()
    assert len(reconcile(db, k8s, fake_r2).launched) == 2
    assert len(k8s.created_jobs) == 2


def test_retry_deletes_previous_job_and_uses_next_attempt_name(db, k8s, fake_r2, queued):
    image = queued(scan_attempts=1, scan_job_name="scan-old-a1")
    k8s.add_job("scan-old-a1", kind="FAILED", reason="DeadlineExceeded")

    reconcile(db, k8s, fake_r2)
    db.refresh(image)
    assert "scan-old-a1" in k8s.deleted_jobs
    assert image.scan_attempts == 2
    assert image.scan_job_name.endswith("-a2")


def test_runner_image_defaults_from_registry_host(monkeypatch):
    monkeypatch.setattr(settings, "SCAN_RUNNER_IMAGE", None)
    assert settings.scan_runner_image == "100.64.0.3:5001/vlab/scan-runner:1.1.0"
    monkeypatch.setattr(settings, "SCAN_RUNNER_IMAGE", RUNNER)
    assert settings.scan_runner_image == RUNNER


def test_missing_registry_leaves_rows_queued(db, k8s, fake_r2, queued, monkeypatch):
    monkeypatch.setattr(settings, "SCAN_RUNNER_IMAGE", None)
    monkeypatch.setattr(settings, "DOCKER_REGISTRY_HOST", None)
    image = queued()
    reconcile(db, k8s, fake_r2)
    db.refresh(image)
    assert image.scan_status is ScanStatus.QUEUED
    assert image.scan_attempts == 0
    assert k8s.created_jobs == {}


def test_missing_etag_is_an_error_not_a_scan(db, k8s, fake_r2, queued):
    image = queued(archive_etag=None)
    reconcile(db, k8s, fake_r2)
    db.refresh(image)
    assert image.scan_status is ScanStatus.ERROR
    assert k8s.created_jobs == {}


def test_secret_failure_removes_job_and_next_round_retries(db, k8s, fake_r2, queued):
    from kubernetes.client.rest import ApiException

    image = queued()
    k8s.secret_error = ApiException(status=500, reason="boom")
    result = reconcile(db, k8s, fake_r2)
    db.refresh(image)
    assert result.launched == []
    assert image.scan_status is ScanStatus.RUNNING   # commit ก่อนแตะ K8s
    assert image.scan_job_name not in k8s.jobs       # Job ที่สร้างแล้วถูกลบทิ้ง

    k8s.secret_error = None
    reconcile(db, k8s, fake_r2)   # รอบหน้า: Job หาย -> retry -> เปิดใหม่ attempt 2
    db.refresh(image)
    assert image.scan_status is ScanStatus.RUNNING
    assert image.scan_attempts == 2
    assert image.scan_job_name in k8s.secrets
