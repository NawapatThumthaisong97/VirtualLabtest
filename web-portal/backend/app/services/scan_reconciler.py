"""
Scan Reconciler
งานพื้นหลังที่เป็นเจ้าของการสแกน lab image กับ K8s คนเดียว (docs/LAB_IMAGE_SCAN_ARCHITECTURE.md ข้อ 4.3)

webhook upload-trigger แค่ตั้งแถวเป็น QUEUED แล้วตอบทันที ส่วนตัวนี้วนทุก
SCAN_RECONCILE_INTERVAL_SECONDS แล้วทำ 4 ขั้นต่อรอบ:
  1. list Job + Pod ของ scan ทั้งหมดครั้งเดียว (label vlab/scan=true)
  2. เก็บผลของแถว RUNNING -> PASSED (approve) / FAILED / ERROR / กลับไป QUEUED (retry)
  3. เปิด Job ให้แถว QUEUED จนเต็ม SCAN_MAX_CONCURRENT (scan_job_service.launch_scan_job)
  4. เก็บกวาด: reject แถว FAILED / ERROR ที่ครบ retention, ลบ Job ที่ไม่มีแถวคู่

สถานะทั้งหมดอยู่ใน DB backend restart แล้วรอบถัดไปทำต่อได้เอง
"""
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from kubernetes.client.rest import ApiException
from sqlalchemy import text

from app.adapters.r2_adapter import r2_adapter
from app.configs.db import SessionLocal, engine
from app.configs.settings import settings
from app.exceptions.domain import DomainError
from app.models.lab_image import ImageStatus, LabImage, ScanStatus
from app.repositories.lab_image_repository import LabImageRepository
from app.services.kubernetes_service import get_kubernetes_service
from app.services.lab_image_service import LabImageService
from app.services.scan_job_service import launch_scan_job, scan_job_name
from app.utils.logger import logger

# Postgres advisory lock กัน backend หลายตัวทำรอบเดียวกันซ้อน (ต่อจาก 880_001 / 880_002)
ADVISORY_LOCK_KEY = 880_003

# label ที่ Job / Pod ของ scan ต้องมี (ScanJobService ต้องใส่ให้ตรง)
SCAN_LABEL = "vlab/scan"
SCAN_SELECTOR = f"{SCAN_LABEL}=true"
# container ที่เขียนผลสรุป JSON ลง /dev/termination-log
RESULT_CONTAINER = "publish"


# ------------------------------------------------------------ อ่านสถานะจาก K8s


@dataclass
class JobState:
    """สถานะของ Job หนึ่งตัวที่อ่านได้จาก K8s

    kind: ACTIVE | SUCCEEDED | FAILED  (Job ที่ไม่อยู่ใน dict ถือว่า MISSING)
    result: JSON ผลสรุปจาก container publish (เฉพาะ SUCCEEDED และอ่านได้)
    """

    kind: str
    reason: Optional[str] = None
    result: Optional[dict] = None


def _job_kind(job) -> tuple[str, Optional[str]]:
    for condition in (job.status.conditions or []) if job.status else []:
        if condition.status != "True":
            continue
        if condition.type == "Failed":
            # DeadlineExceeded / BackoffLimitExceeded / PodFailurePolicy
            return "FAILED", condition.reason
        if condition.type == "Complete":
            return "SUCCEEDED", None
    return "ACTIVE", None


def _pod_result(pod) -> Optional[dict]:
    """JSON จาก termination message ของ container publish (None = ไม่มี / อ่านไม่ได้)"""
    for status in (pod.status.container_statuses or []) if pod.status else []:
        terminated = status.state.terminated if status.state else None
        if status.name != RESULT_CONTAINER or terminated is None or not terminated.message:
            continue
        try:
            result = json.loads(terminated.message)
        except ValueError:
            return None
        return result if isinstance(result, dict) else None
    return None


def read_scan_jobs(k8s) -> dict[str, JobState]:
    """อ่าน Job + Pod ของ scan ทั้งหมดใน namespace ด้วย 2 API call แล้วจับคู่ด้วยชื่อ Job

    Pod ของ Job มี label job-name=<ชื่อ Job> (K8s ใส่ให้เอง)
    """
    namespace, timeout = settings.SCAN_NAMESPACE, settings.K8S_TIMEOUT
    jobs = k8s.batch_v1.list_namespaced_job(
        namespace, label_selector=SCAN_SELECTOR, _request_timeout=timeout
    ).items
    pods = k8s.v1.list_namespaced_pod(
        namespace, label_selector=SCAN_SELECTOR, _request_timeout=timeout
    ).items

    results: dict[str, dict] = {}
    for pod in pods:
        job_name = (pod.metadata.labels or {}).get("job-name")
        result = _pod_result(pod)
        if job_name and result is not None:
            results[job_name] = result

    states: dict[str, JobState] = {}
    for job in jobs:
        name = job.metadata.name
        kind, reason = _job_kind(job)
        states[name] = JobState(
            kind=kind, reason=reason, result=results.get(name) if kind == "SUCCEEDED" else None
        )
    return states


def delete_scan_job(k8s, name: str) -> None:
    """ลบ Job พร้อม Pod (Secret ผูก ownerReference กับ Job ไว้ จึงถูกลบตาม) ไม่มีอยู่แล้วถือว่าสำเร็จ"""
    try:
        k8s.batch_v1.delete_namespaced_job(
            name,
            settings.SCAN_NAMESPACE,
            propagation_policy="Background",
            _request_timeout=settings.K8S_TIMEOUT,
        )
    except ApiException as error:
        if error.status != 404:
            raise


# ------------------------------------------------------------ ตัดสินผลของแต่ละแถว


@dataclass
class ReconcileResult:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    errored: list[str] = field(default_factory=list)
    retried: list[str] = field(default_factory=list)
    launched: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    orphans_deleted: list[str] = field(default_factory=list)

    def changed(self) -> bool:
        return any(getattr(self, name) for name in self.__dataclass_fields__)

    def as_dict(self) -> dict[str, Any]:
        return {name: value for name, value in self.__dict__.items() if value}


class ScanReconciler:
    def __init__(self, db, repo: LabImageRepository, service: LabImageService, r2, k8s):
        self.db = db
        self.repo = repo
        self.service = service
        self.r2 = r2
        self.k8s = k8s
        self._deleted: set[str] = set()  # Job ที่ลบไปแล้วในรอบนี้ (ไม่นับเป็น orphan ซ้ำ)

    def _delete_job(self, name: Optional[str]) -> None:
        if name and name not in self._deleted:
            delete_scan_job(self.k8s, name)
            self._deleted.add(name)

    def run(self, now: Optional[datetime] = None) -> ReconcileResult:
        now = now or datetime.now(timezone.utc)
        result = ReconcileResult()

        running = self.repo.find_by_scan_status(ScanStatus.RUNNING)
        queued = self.repo.find_by_scan_status(ScanStatus.QUEUED)
        # ไม่มีงาน = ไม่แตะ K8s เลย (รอบส่วนใหญ่จบที่ query นี้)
        jobs = read_scan_jobs(self.k8s) if (running or queued) else None

        if jobs is not None:
            for image in running:
                self._collect(image, jobs.get(image.scan_job_name or ""), now, result)
            self.launch_queued(result)
            self._delete_orphan_jobs(jobs, result)
        self._reject_expired(now, result)
        return result

    # ---- ขั้น 2: เก็บผลของแถว RUNNING

    def _collect(self, image: LabImage, state: Optional[JobState], now: datetime, result: ReconcileResult) -> None:
        image_id = str(image.id)
        if state is not None and state.kind == "ACTIVE":
            if image.scan_started_at and now - image.scan_started_at > timedelta(
                seconds=settings.SCAN_JOB_DEADLINE_SECONDS + 300
            ):
                # K8s ควรตัดด้วย activeDeadlineSeconds ไปแล้ว ถ้ายังค้างอยู่ ตัดเอง
                self._retry_or_error(image, "job did not finish in time", result)
            return

        if state is None:
            # Job หาย: ถูกลบ / หมด TTL / สร้างไม่สำเร็จหลังตั้ง RUNNING
            self._retry_or_error(image, "scan job not found", result)
            return
        if state.kind == "FAILED":
            self._retry_or_error(image, f"scan job failed: {state.reason or 'unknown'}", result)
            return

        outcome = state.result
        if outcome is None:
            self._retry_or_error(image, "scan result missing or unreadable", result)
            return
        if outcome.get("etag") != image.archive_etag:
            # ผลของไฟล์เก่า (ปกติ webhook จะตั้งแถวเป็น QUEUED ไปแล้ว ไม่น่าเข้ามาถึงตรงนี้)
            image.scan_status = ScanStatus.QUEUED
            image.scan_attempts = 0
            self.db.commit()
            self._delete_job(image.scan_job_name)
            result.retried.append(image_id)
            return

        verdict = outcome.get("verdict")
        summary = _summary_from(outcome)
        if verdict == "PASS" and outcome.get("digest"):
            self._finish(image, ScanStatus.PASSED, summary, now, digest=outcome["digest"])
            self._approve_and_drop_archive(image)
            result.passed.append(image_id)
        elif verdict == "FAIL":
            self._finish(image, ScanStatus.FAILED, summary, now)
            result.failed.append(image_id)
        elif verdict == "ERROR" and outcome.get("retryable"):
            self._retry_or_error(image, "; ".join(outcome.get("reasons") or ["retryable error"]), result, summary)
            return
        else:
            # ERROR ถาวร หรือ PASS ที่ไม่มี digest (push ไม่ครบ) / verdict แปลก
            self._finish(image, ScanStatus.ERROR, summary, now)
            result.errored.append(image_id)
        self._delete_job(image.scan_job_name)

    def _finish(self, image: LabImage, status: ScanStatus, summary: dict, now: datetime, digest: Optional[str] = None) -> None:
        image.scan_status = status
        image.scan_summary = summary
        image.scan_finished_at = now
        if digest is not None:
            image.image_digest = digest
        self.db.commit()

    def _retry_or_error(self, image: LabImage, reason: str, result: ReconcileResult, summary: Optional[dict] = None) -> None:
        """กลับไป QUEUED ถ้ายังเหลือโควตา ไม่งั้นเป็น ERROR (ลบ Job ของรอบนี้ทิ้งทั้งสองกรณี)"""
        job_name = image.scan_job_name
        if image.scan_attempts < settings.SCAN_MAX_ATTEMPTS:
            image.scan_status = ScanStatus.QUEUED
            image.scan_summary = {**(summary or {}), "lastError": reason}
            result.retried.append(str(image.id))
            self.db.commit()
        else:
            self._finish(image, ScanStatus.ERROR, {**(summary or {}), "reasons": [reason]}, datetime.now(timezone.utc))
            result.errored.append(str(image.id))
        self._delete_job(job_name)

    def _approve_and_drop_archive(self, image: LabImage) -> None:
        """PASS -> approve แล้วลบ tar จาก R2 (registry เป็นที่เก็บจริงแล้ว)

        approve ไม่ผ่าน (เช่น ถูกเปลี่ยนสถานะไประหว่างนั้น) ไม่ลบไฟล์ ให้คนดูต่อ
        ลบ R2 ไม่ได้แค่ log ไฟล์ค้างใน bucket ไม่กระทบระบบ (image อยู่ใน registry แล้ว)
        """
        try:
            self.service.approve_image(image.id)
        except DomainError as error:
            logger.warning(f"Scan passed but approve failed for {image.id}: {error}")
            return
        try:
            if image.archive_key:
                self.r2.delete_object(image.archive_key)
        except Exception as error:  # noqa: BLE001 — ลบไม่ได้ไม่ใช่เหตุให้ทั้งรอบล้ม
            logger.warning(f"Could not delete archive {image.archive_key} from R2: {error}")

    # ---- ขั้น 3: เปิด Job ให้แถว QUEUED

    def launch_queued(self, result: ReconcileResult) -> None:
        """เปิด Job ให้แถว QUEUED เรียงตามเวลาอัปโหลด จนเต็ม SCAN_MAX_CONCURRENT"""
        running = len(self.repo.find_by_scan_status(ScanStatus.RUNNING))
        free_slots = settings.SCAN_MAX_CONCURRENT - running
        if free_slots <= 0:
            return

        if not settings.scan_runner_image or not settings.DOCKER_REGISTRY_HOST:
            # ตั้งค่าไม่ครบไม่ใช่ความผิดของแถว: ปล่อยค้าง QUEUED ไม่เผา scan_attempts
            logger.warning("Scan reconciler: DOCKER_REGISTRY_HOST not set, not launching jobs")
            return

        for image in self.repo.find_by_scan_status(ScanStatus.QUEUED)[:free_slots]:
            if image.status is not ImageStatus.PENDING:
                continue
            if not (image.archive_key and image.archive_etag and image.archive_size_bytes):
                # webhook ไม่ได้ส่ง etag / size มา ตรวจไฟล์ให้ตรงกับที่บันทึกไม่ได้ จึงไม่สแกน
                self._finish(image, ScanStatus.ERROR,
                             {"verdict": "ERROR", "reasons": ["archive metadata (etag / size) missing"]},
                             datetime.now(timezone.utc))
                result.errored.append(str(image.id))
                continue

            # 1. Job ของรอบก่อน (retry / อัปไฟล์ทับระหว่างสแกน) ต้องหายก่อน ไม่งั้นผลเก่าอาจถูกอ่าน
            self._delete_job(image.scan_job_name)

            # 2. commit RUNNING ก่อนแตะ K8s: สร้าง Job ไม่สำเร็จ -> รอบหน้าเห็น Job หาย แล้ว _collect retry เอง
            image.scan_attempts += 1
            image.scan_job_name = scan_job_name(image, image.scan_attempts)
            image.scan_status = ScanStatus.RUNNING
            image.scan_started_at = datetime.now(timezone.utc)
            image.scan_finished_at = None
            self.db.commit()

            # 3. Job + Secret (presigned GET สด) ล้มแถวเดียวไม่หยุดแถวอื่น
            try:
                launch_scan_job(self.k8s, self.r2, image, image.scan_job_name)
            except Exception as error:  # noqa: BLE001
                logger.warning(f"Scan reconciler could not launch job for {image.id}: {error}")
                continue
            result.launched.append(str(image.id))

    # ---- ขั้น 4: เก็บกวาด

    def _delete_orphan_jobs(self, jobs: dict[str, JobState], result: ReconcileResult) -> None:
        """Job ที่มี label scan แต่ไม่ใช่ Job ปัจจุบันของแถว RUNNING ไหนเลย (แถวถูกลบ / ถูกแทนด้วยรอบใหม่)"""
        self.db.expire_all()
        current = {image.scan_job_name for image in self.repo.find_by_scan_status(ScanStatus.RUNNING)}
        for name in jobs:
            if name not in current and name not in self._deleted:
                self._delete_job(name)
                result.orphans_deleted.append(name)

    def _reject_expired(self, now: datetime, result: ReconcileResult) -> None:
        """FAILED / ERROR ที่ครบ retention -> reject_image (ลบ tar จาก R2 แล้วลบแถว คืนชื่อ repository:tag)"""
        cutoff = now - timedelta(days=settings.SCAN_FAILED_RETENTION_DAYS)
        for image in self.repo.find_scans_finished_before(cutoff, ScanStatus.FAILED, ScanStatus.ERROR):
            image_id = image.id
            try:
                self.service.reject_image(image_id)
                result.rejected.append(str(image_id))
            except DomainError as error:
                # ถูกอ้างอิงอยู่ / ไม่ใช่ PENDING / R2 ลบไม่ได้ -> ข้ามแถวนี้ รอบหน้าลองใหม่
                logger.warning(f"Scan reconciler could not reject {image_id}: {error}")


def _summary_from(outcome: dict) -> dict:
    """ส่วนของผลที่เก็บใน scan_summary (ตัด etag / digest ที่มีคอลัมน์ของตัวเองแล้ว)"""
    summary = dict(outcome.get("summary") or {})
    summary["verdict"] = outcome.get("verdict")
    summary["reasons"] = outcome.get("reasons") or []
    summary["warnings"] = outcome.get("warnings") or []
    return summary


# ------------------------------------------------------------ loop


def reconcile_once() -> Optional[dict]:
    """1 รอบ คืน None ถ้า backend ตัวอื่นกำลังทำอยู่ (lock ถือบน connection แยกแบบ session_reconciler)"""
    with engine.connect() as lock_conn:
        if not lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}
        ).scalar():
            return None
        try:
            db = SessionLocal()
            try:
                repo = LabImageRepository(db)
                reconciler = ScanReconciler(
                    db, repo, LabImageService(db, repo, r2_adapter), r2_adapter, get_kubernetes_service()
                )
                return reconciler.run().as_dict()
            finally:
                db.close()
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})


async def run_scan_reconciler(interval_seconds: int, stop: asyncio.Event) -> None:
    """เรียก reconcile_once ทุก interval_seconds จนกว่า stop จะถูก set

    K8s SDK เป็น blocking จึงรันใน thread ไม่ให้ event loop ของ FastAPI ค้าง
    """
    logger.info(f"Scan reconciler started (every {interval_seconds}s)")
    while not stop.is_set():
        try:
            result = await asyncio.to_thread(reconcile_once)
            if result:
                logger.info(f"Scan reconciler: {result}")
        except Exception as e:
            # รอบนี้พัง (เช่น K3s ล่ม) แถวที่แก้ไปแล้วถูก commit ทีละแถว ที่เหลือลองใหม่รอบหน้า
            logger.warning(f"Scan reconciler failed: {e}")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
    logger.info("Scan reconciler stopped")
