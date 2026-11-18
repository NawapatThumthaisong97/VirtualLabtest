"""เก็บผลสแกน (scan_reconciler._collect) แล้วเติม Exposed ports จาก EXPOSE ของ image
(docs/LAB_IMAGE_UPLOAD_PLAN.md ข้อ 4.2) — FakeK8s / FakeR2 ไม่ต่อ cluster จริง
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.lab_image import ImageStatus, LabImage, ScanStatus
from app.services.scan_reconciler import NO_COMMAND_WARNING, NO_PORTS_WARNING, ports_from_exposed
from tests.fakes import FakeK8s
from tests.lab_image.test_scan_launch import ETAG, reconcile, scan_settings  # noqa: F401 (autouse fixture)

DIGEST = "sha256:" + "b" * 64


@pytest.fixture
def k8s():
    return FakeK8s()


@pytest.fixture
def scanned(db, world, k8s):
    """แถว RUNNING ที่ Job สแกนจบแล้วด้วยผล verdict / exposedPorts ที่กำหนด

    command=None = ผลแบบ runner 1.1.0 (ไม่มี key entrypoint / cmd)
    command=(entrypoint, cmd) = ผลแบบ runner 1.2.0
    """

    def _make(verdict="PASS", exposed=(8080,), ports=(), image_info=True, command=None, entrypoint_script=None):
        job_name = f"scan-{uuid.uuid4().hex[:12]}"
        image = _image(db, world, job_name, list(ports), entrypoint_script)
        summary = {"runnerVersion": "1.1.0" if command is None else "1.2.0"}
        if image_info:
            summary["image"] = {"os": "linux", "architecture": "amd64", "user": "", "exposedPorts": list(exposed)}
            if command is not None:
                summary["image"].update(entrypoint=list(command[0]), cmd=list(command[1]), workingDir="")
        k8s.add_job(job_name, "SUCCEEDED", result={
            "imageId": str(image.id), "etag": ETAG, "verdict": verdict, "retryable": False,
            "reasons": [] if verdict == "PASS" else ["blocked"], "warnings": ["image runs as root"],
            "digest": DIGEST if verdict == "PASS" else None, "summary": summary,
        })
        return image

    return _make


def _image(db, world, job_name, ports, entrypoint_script=None):
    image = LabImage(
        id=uuid.uuid4(), uploaded_by=world.owner.id, course_id=world.course.id,
        repository="vlab/collect-test", tag=f"lab-{uuid.uuid4().hex[:6]}", size_mb=10,
        entrypoint_script=entrypoint_script,
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

    def test_runner_1_2_ports_skip_udp(self, db, k8s, fake_r2, scanned):
        """runner 1.2.0 keeps the protocol: EXPOSE 53/udp 8080 gives only 8080"""
        image = scanned(exposed=["53/udp", "8080/tcp"], command=([], ["httpd"]))
        reconcile(db, k8s, fake_r2)

        db.refresh(image)
        assert image.exposed_ports == [8080]


class TestNoCommandWarning:
    """Scan PASS warns when the container would have nothing to run"""

    def run(self, db, k8s, fake_r2, scanned, **kwargs):
        image = scanned(**kwargs)
        reconcile(db, k8s, fake_r2)
        db.refresh(image)
        return image

    def test_no_entrypoint_no_cmd_nothing_entered(self, db, k8s, fake_r2, scanned):
        """Image sets neither ENTRYPOINT nor CMD and no Entrypoint entered: approved, with a warning"""
        image = self.run(db, k8s, fake_r2, scanned, command=([], []))
        assert image.status is ImageStatus.APPROVED
        assert NO_COMMAND_WARNING in image.scan_summary["warnings"]

    def test_entered_entrypoint_is_enough(self, db, k8s, fake_r2, scanned):
        """The instructor's Entrypoint replaces the image's command, so nothing to warn about"""
        image = self.run(db, k8s, fake_r2, scanned, command=([], []), entrypoint_script="httpd -f -p 8080")
        assert NO_COMMAND_WARNING not in image.scan_summary["warnings"]

    @pytest.mark.parametrize("command", [(["/entrypoint.sh"], []), ([], ["httpd"])], ids=["entrypoint", "cmd"])
    def test_image_has_a_command(self, db, k8s, fake_r2, scanned, command):
        """ENTRYPOINT or CMD alone is enough"""
        image = self.run(db, k8s, fake_r2, scanned, command=command)
        assert NO_COMMAND_WARNING not in image.scan_summary["warnings"]

    def test_unknown_with_old_runner(self, db, k8s, fake_r2, scanned):
        """Runner 1.1.0 (no entrypoint / cmd keys): unknown, so no warning instead of a false alarm"""
        image = self.run(db, k8s, fake_r2, scanned)
        assert NO_COMMAND_WARNING not in image.scan_summary["warnings"]

    def test_unknown_when_image_info_trimmed(self, db, k8s, fake_r2, scanned):
        """summary.image dropped to fit 4 KB: unknown, no warning"""
        image = self.run(db, k8s, fake_r2, scanned, image_info=False)
        assert NO_COMMAND_WARNING not in image.scan_summary["warnings"]

    def test_failed_scan_is_not_warned(self, db, k8s, fake_r2, scanned):
        """FAIL: the image is not usable anyway"""
        image = self.run(db, k8s, fake_r2, scanned, verdict="FAIL", command=([], []))
        assert NO_COMMAND_WARNING not in image.scan_summary["warnings"]


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
