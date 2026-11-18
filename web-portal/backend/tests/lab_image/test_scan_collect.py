"""เก็บผลสแกน (scan_reconciler._collect) แล้วเติม Exposed ports จาก EXPOSE ของ image
(docs/LAB_IMAGE_UPLOAD_PLAN.md ข้อ 4.2) — FakeK8s / FakeR2 ไม่ต่อ cluster จริง
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.lab_image import ImageStatus, LabImage, ScanStatus
from app.services.scan_reconciler import NO_PORTS_WARNING, ports_from_exposed
from tests.fakes import FakeK8s
from tests.lab_image.test_scan_launch import ETAG, reconcile, scan_settings  # noqa: F401 (autouse fixture)

DIGEST = "sha256:" + "b" * 64


@pytest.fixture
def k8s():
    return FakeK8s()


@pytest.fixture
def scanned(db, world, k8s):
    """แถว RUNNING ที่ Job สแกนจบแล้วด้วยผล verdict / exposedPorts ที่กำหนด"""

    def _make(verdict="PASS", exposed=(8080,), ports=(), image_info=True):
        job_name = f"scan-{uuid.uuid4().hex[:12]}"
        image = _image(db, world, job_name, list(ports))
        summary = {"runnerVersion": "1.1.0"}
        if image_info:
            summary["image"] = {"os": "linux", "architecture": "amd64", "user": "", "exposedPorts": list(exposed)}
        k8s.add_job(job_name, "SUCCEEDED", result={
            "imageId": str(image.id), "etag": ETAG, "verdict": verdict, "retryable": False,
            "reasons": [] if verdict == "PASS" else ["blocked"], "warnings": ["image runs as root"],
            "digest": DIGEST if verdict == "PASS" else None, "summary": summary,
        })
        return image

    return _make


def _image(db, world, job_name, ports):
    image = LabImage(
        id=uuid.uuid4(), uploaded_by=world.owner.id, course_id=world.course.id,
        repository="vlab/collect-test", tag=f"lab-{uuid.uuid4().hex[:6]}", size_mb=10,
        status=ImageStatus.PENDING, scan_status=ScanStatus.RUNNING, scan_attempts=1,
        scan_job_name=job_name, scan_started_at=datetime.now(timezone.utc), exposed_ports=ports,
        archive_key=f"lab-images/{uuid.uuid4().hex}_image.tar", archive_etag=ETAG,
        archive_size_bytes=10 * 1024 * 1024, archive_uploaded_at=datetime.now(timezone.utc),
    )
    db.add(image)
    db.commit()
    return image


class TestFillPortsFromImage:
    """Scan PASS fills empty Exposed ports from the image's EXPOSE"""

    def test_empty_ports_take_image_expose(self, db, k8s, fake_r2, scanned):
        """Instructor left ports empty: EXPOSE 5173 8080 becomes [5173, 8080] and the image is approved"""
        image = scanned(exposed=[5173, 8080])
        result = reconcile(db, k8s, fake_r2)

        db.refresh(image)
        assert result.passed == [str(image.id)]
        assert image.status is ImageStatus.APPROVED
        assert image.exposed_ports == [5173, 8080]
        assert image.scan_summary["portsFromImage"] is True
        assert NO_PORTS_WARNING not in image.scan_summary["warnings"]

    def test_entered_ports_win(self, db, k8s, fake_r2, scanned):
        """Ports the instructor typed are never replaced by EXPOSE"""
        image = scanned(exposed=[8080], ports=[3000])
        reconcile(db, k8s, fake_r2)

        db.refresh(image)
        assert image.exposed_ports == [3000]
        assert "portsFromImage" not in image.scan_summary

    def test_no_ports_anywhere_is_approved_with_warning(self, db, k8s, fake_r2, scanned):
        """No EXPOSE and nothing entered: still approved, but warned that students get no link"""
        image = scanned(exposed=[])
        reconcile(db, k8s, fake_r2)

        db.refresh(image)
        assert image.status is ImageStatus.APPROVED
        assert image.exposed_ports == []
        assert image.scan_summary["warnings"] == ["image runs as root", NO_PORTS_WARNING]

    def test_summary_without_image_info(self, db, k8s, fake_r2, scanned):
        """Result trimmed to fit 4 KB (no summary.image): treated as no EXPOSE, not a crash"""
        image = scanned(image_info=False)
        reconcile(db, k8s, fake_r2)

        db.refresh(image)
        assert image.status is ImageStatus.APPROVED
        assert NO_PORTS_WARNING in image.scan_summary["warnings"]

    def test_failed_scan_does_not_touch_ports(self, db, k8s, fake_r2, scanned):
        """FAIL: ports stay empty and no port warning is added (the image is not usable anyway)"""
        image = scanned(verdict="FAIL", exposed=[8080])
        reconcile(db, k8s, fake_r2)

        db.refresh(image)
        assert image.scan_status is ScanStatus.FAILED
        assert image.exposed_ports == []
        assert NO_PORTS_WARNING not in image.scan_summary["warnings"]


class TestPortsFromExposed:
    """ExposedPorts from the runner -> tcp port list"""

    @pytest.mark.parametrize("exposed, expected", [
        ([8080, 5173], [8080, 5173]),                  # runner 1.1.0: int ตัด proto แล้ว
        (["8080/tcp", "53/udp", "3000"], [8080, 3000]),  # มี proto: ข้าม udp, ไม่มี proto = tcp
        (["8080/TCP"], [8080]),
        ([8080, 8080, "8080/tcp"], [8080]),            # ซ้ำ
        ([0, 70000, "abc", None, "-1"], []),           # นอกช่วง / ไม่ใช่ตัวเลข
        (None, []),
        ("8080", []),                                  # ไม่ใช่ list
    ])
    def test_parse(self, exposed, expected):
        """Only valid, unique tcp ports, in the given order"""
        assert ports_from_exposed(exposed) == expected
