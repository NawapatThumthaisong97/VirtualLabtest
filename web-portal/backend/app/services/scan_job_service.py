"""
Scan Job: สร้าง K8s Job ที่รัน vlab-scan-runner กับ tar ของ lab image หนึ่งแถว

สัญญาของ Pod (env, secret, securityContext) ตาม docs/SCAN_RUNNER_IMAGE.md ข้อ 4
เรียกจาก scan_reconciler.launch_queued เท่านั้น (reconciler เป็นเจ้าของ K8s คนเดียว)

ลำดับ: สร้าง Job ก่อน แล้วสร้าง Secret ที่มี ownerReference ชี้ Job
- Pod จะรอที่ ContainerCreating จนกว่า Secret มี (kubelet retry mount เอง) ไม่ต้องเรียงจังหวะ
- ลบ Job แล้ว Secret ถูกลบตามโดย garbage collector ไม่มี URL ค้างใน cluster
- สร้าง Secret ไม่ได้ -> ลบ Job ที่เพิ่งสร้างทิ้งแล้วโยน error ให้ reconciler retry
"""
import re
from typing import Any

from kubernetes.client.rest import ApiException

from app.configs.settings import settings
from app.models.lab_image import LabImage

SCAN_LABEL = "vlab/scan"
RUNNER_UID = 10001
SECRET_KEY = "download_url"
SECRET_MOUNT = "/secrets/fetch"
PUSH_SECRET_MOUNT = "/secrets/push"   # ต้องตรงกับ PUSH_CREDENTIALS_DIR ใน scan-runner/runner.py
WORK_MOUNT = "/work"

_NON_HEX = re.compile(r"[^0-9a-f]")


class ScanJobConfigError(RuntimeError):
    """ตั้งค่าไม่ครบ (เช่นไม่มี SCAN_RUNNER_IMAGE) — ไม่ใช่ความผิดของแถวนี้"""


def scan_job_name(image: LabImage, attempt: int) -> str:
    """scan-{id 12 ตัว}-{etag 8 ตัว}-a{ครั้งที่} (<= 63 ตัว a-z0-9-) ชื่อเปลี่ยนเมื่อไฟล์หรือรอบเปลี่ยน"""
    etag8 = _NON_HEX.sub("", (image.archive_etag or "").lower())[:8] or "noetag"
    return f"scan-{image.id.hex[:12]}-{etag8}-a{attempt}"


def _labels(image: LabImage, job_name: str) -> dict[str, str]:
    return {SCAN_LABEL: "true", "vlab/scan-image-id": str(image.id), "vlab/scan-job": job_name}


def _env(values: dict[str, Any]) -> list[dict]:
    return [{"name": k, "value": str(v)} for k, v in values.items() if v not in (None, "")]


def _container(name: str, args: str, env: dict[str, Any], requests: dict, limits: dict,
               extra_mounts: list[dict] | None = None) -> dict:
    return {
        "name": name,
        "image": settings.scan_runner_image,
        "imagePullPolicy": "IfNotPresent",
        "args": [args],
        "env": _env(env),
        "resources": {"requests": requests, "limits": limits},
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": RUNNER_UID,
            "runAsGroup": RUNNER_UID,
            "capabilities": {"drop": ["ALL"]},
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "volumeMounts": [{"name": "work", "mountPath": WORK_MOUNT}, *(extra_mounts or [])],
        "terminationMessagePolicy": "File",
    }


def build_scan_job(image: LabImage, job_name: str) -> dict:
    """manifest ของ Job (dict) — แยกเป็นฟังก์ชันล้วนให้ทดสอบได้โดยไม่ต้องมี cluster"""
    if not settings.scan_runner_image:
        raise ScanJobConfigError("DOCKER_REGISTRY_HOST is not set (needed to locate the scan runner image)")
    if not settings.registry_push_host:
        raise ScanJobConfigError("DOCKER_REGISTRY_HOST is not set")

    labels = _labels(image, job_name)
    common = {"IMAGE_ID": image.id, "ETAG": image.archive_etag}
    ports = ",".join(str(p) for p in (image.exposed_ports or []) if str(p).isdigit())

    # env เฉพาะที่แต่ละขั้นใช้ (container ที่ไม่ต้องรู้ registry ก็ไม่ได้รับ)
    fetch = _container(
        "fetch", "fetch",
        {**common, "EXPECTED_SIZE": image.archive_size_bytes},
        requests={"cpu": "100m", "memory": "128Mi"}, limits={"cpu": "1", "memory": "256Mi"},
        extra_mounts=[{"name": "download-url", "mountPath": SECRET_MOUNT, "readOnly": True}],
    )
    validate = _container(
        "validate", "validate",
        {**common, "ALLOWED_ARCH": "amd64", "DECLARED_PORTS": ports},
        requests={"cpu": "100m", "memory": "256Mi"}, limits={"cpu": "1", "memory": "1Gi"},
    )
    scan = _container(
        "scan", "scan",
        {**common, "POLICY_FAIL_SEVERITY": settings.SCAN_FAIL_SEVERITY, "POLICY_IGNORE_UNFIXED": "true"},
        requests={"cpu": "500m", "memory": "1Gi"}, limits={"cpu": "2", "memory": "4Gi"},
    )
    # push ผ่าน push port ที่ต้อง login (credential mount เข้า publish ตัวเดียว)
    publish = _container(
        "publish", "publish",
        {**common, "REGISTRY": settings.registry_push_host,
         "REPOSITORY": image.repository, "TAG": image.tag},
        requests={"cpu": "100m", "memory": "256Mi"}, limits={"cpu": "1", "memory": "1Gi"},
        extra_mounts=[{"name": "push-credentials", "mountPath": PUSH_SECRET_MOUNT, "readOnly": True}],
    )

    pod_spec: dict[str, Any] = {
        "restartPolicy": "Never",
        "automountServiceAccountToken": False,
        "enableServiceLinks": False,
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": RUNNER_UID,
            "runAsGroup": RUNNER_UID,
            "fsGroup": RUNNER_UID,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "initContainers": [fetch, validate, scan],
        "containers": [publish],
        "volumes": [
            {"name": "work", "emptyDir": {"sizeLimit": settings.SCAN_WORK_SIZE_LIMIT}},
            # Secret ชื่อเดียวกับ Job มีแค่ URL ของไฟล์นี้ไฟล์เดียว mount เข้าเฉพาะ fetch
            {"name": "download-url", "secret": {
                "secretName": job_name, "defaultMode": 0o400,
                "items": [{"key": SECRET_KEY, "path": SECRET_KEY}],
            }},
            # Secret ถาวรที่ Ansible สร้าง (ไม่ผูกกับ Job) mount เข้าเฉพาะ publish
            {"name": "push-credentials", "secret": {
                "secretName": settings.SCAN_PUSH_SECRET, "defaultMode": 0o400,
                "items": [{"key": "username", "path": "username"}, {"key": "password", "path": "password"}],
            }},
        ],
    }
    if settings.SCAN_PRIORITY_CLASS:
        pod_spec["priorityClassName"] = settings.SCAN_PRIORITY_CLASS
    if settings.SCAN_NODE_SELECTOR:
        pod_spec["nodeSelector"] = dict(settings.SCAN_NODE_SELECTOR)

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name, "namespace": settings.SCAN_NAMESPACE, "labels": labels},
        "spec": {
            "backoffLimit": 0,                                   # retry เป็นงานของ reconciler (นับ scan_attempts)
            "activeDeadlineSeconds": settings.SCAN_JOB_DEADLINE_SECONDS,
            "ttlSecondsAfterFinished": 3600,                     # กันค้าง ปกติ reconciler ลบเองทันทีที่ได้ผล
            "template": {"metadata": {"labels": labels}, "spec": pod_spec},
        },
    }


def build_download_secret(image: LabImage, job_name: str, download_url: str, job_uid: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {
            "name": job_name,
            "namespace": settings.SCAN_NAMESPACE,
            "labels": _labels(image, job_name),
            "ownerReferences": [{
                "apiVersion": "batch/v1", "kind": "Job", "name": job_name, "uid": job_uid,
                "controller": False, "blockOwnerDeletion": False,
            }],
        },
        "stringData": {SECRET_KEY: download_url},
    }


def _uid_of(obj: Any) -> str:
    metadata = obj.get("metadata") if isinstance(obj, dict) else getattr(obj, "metadata", None)
    uid = metadata.get("uid") if isinstance(metadata, dict) else getattr(metadata, "uid", None)
    if not uid:
        raise RuntimeError("Job has no uid")
    return uid


def launch_scan_job(k8s, r2, image: LabImage, job_name: str) -> None:
    """สร้าง Job + Secret ของแถวนี้ (ทำซ้ำได้: Job ชื่อนี้มีอยู่แล้ว = ถือว่าสำเร็จ)"""
    namespace, timeout = settings.SCAN_NAMESPACE, settings.K8S_TIMEOUT
    job_manifest = build_scan_job(image, job_name)
    try:
        job = k8s.batch_v1.create_namespaced_job(namespace, job_manifest, _request_timeout=timeout)
    except ApiException as error:
        if error.status != 409:
            raise
        # รอบก่อนสร้างไปแล้ว (เช่น commit DB ไม่ทัน) ใช้ Job เดิม
        job = k8s.batch_v1.read_namespaced_job(job_name, namespace, _request_timeout=timeout)

    # ออก URL ตอนสร้าง Job (สด) ไม่ใช่ตอนเข้าคิว
    download_url = r2.generate_presigned_get_url(image.archive_key, settings.SCAN_DOWNLOAD_URL_TTL_SECONDS)
    secret = build_download_secret(image, job_name, download_url, _uid_of(job))
    try:
        k8s.v1.create_namespaced_secret(namespace, secret, _request_timeout=timeout)
    except ApiException as error:
        if error.status == 409:
            # มีอยู่แล้ว (สร้างซ้ำ) แทนด้วย URL ใหม่
            k8s.v1.replace_namespaced_secret(job_name, namespace, secret, _request_timeout=timeout)
            return
        _delete_job_quietly(k8s, job_name)
        raise
    except Exception:
        _delete_job_quietly(k8s, job_name)
        raise


def _delete_job_quietly(k8s, job_name: str) -> None:
    try:
        k8s.batch_v1.delete_namespaced_job(
            job_name, settings.SCAN_NAMESPACE, propagation_policy="Background",
            _request_timeout=settings.K8S_TIMEOUT,
        )
    except ApiException:
        pass  # ลบไม่ได้: reconciler รอบหน้าเห็นเป็น orphan / RUNNING ค้าง แล้วจัดการเอง
