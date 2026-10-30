#!/usr/bin/env python3
"""
vlab-scan-runner: ตรวจไฟล์ image.tar ที่อาจารย์อัปโหลด ก่อนเข้า camp registry

ใช้ภายใน K8s Job ของ scan reconciler (docs/LAB_IMAGE_SCAN_ARCHITECTURE.md ข้อ 4.4)
แต่ละ container ใน Pod เรียกคำสั่งย่อยเดียว ใช้ volume /work ร่วมกัน:

    fetch     (init)  โหลด tar จาก presigned GET  -> /work/image.tar     มี secret (URL) ตัวเดียว
    validate  (init)  ตรวจโครง tar + config ของ image ด้วย skopeo        ไม่มี secret
    scan      (init)  Trivy หาช่องโหว่ / secret แล้วตัดสินตาม policy       ไม่มี secret
    publish   (main)  PASS -> skopeo copy เข้า registry แล้วเขียนผลสรุป     มี secret (user/password ของ push port)
    version           พิมพ์เวอร์ชันของเครื่องมือ (ใช้ตรวจ image หลัง build)

สัญญา (contract):
- ผลระหว่างขั้นอยู่ใน /work/state.json (เขียนแบบ atomic) ขั้นถัดไปเห็น verdict แล้วข้ามตัวเอง
- เจอ image ไม่ผ่าน / โหลดไม่ได้ -> บันทึก verdict แล้ว exit 0 เพื่อให้ publish ได้เขียนผลเสมอ
- exit non-zero เฉพาะเมื่อ runner พังเอง -> Job เป็น Failed -> reconciler retry
- publish เขียน JSON (<= 4096 ไบต์) ลง /dev/termination-log ให้ backend อ่านผ่าน K8s API
  key: imageId, etag, verdict (PASS|FAIL|ERROR), retryable, digest, reasons, warnings, summary

ความปลอดภัย:
- Python stdlib อย่างเดียว ไม่มี dependency ภายนอก
- ไม่ log URL ที่เซ็นแล้ว ไม่ log environment ไม่ log credential ของ registry
- credential ของ registry อ่านจากไฟล์ เขียนเป็น authfile 0600 ชั่วคราว ไม่อยู่ใน env / argv
- เรียก tool ด้วย argv list เสมอ (ไม่ผ่าน shell) และตรวจรูปแบบ input ทุกตัวก่อนใช้
- ไม่แตก (extract) tar: อ่านแค่ header และให้ skopeo / Trivy อ่านไฟล์เอง
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Callable, NoReturn, Optional

RUNNER_VERSION = "1.1.0"

WORK_DIR = os.environ.get("WORK_DIR", "/work")
ARCHIVE_PATH = os.path.join(WORK_DIR, "image.tar")
STATE_PATH = os.path.join(WORK_DIR, "state.json")
TRIVY_REPORT_PATH = os.path.join(WORK_DIR, "trivy.json")
DIGEST_PATH = os.path.join(WORK_DIR, "digest")
DOWNLOAD_URL_FILE = os.environ.get("DOWNLOAD_URL_FILE", "/secrets/fetch/download_url")
# Secret แบบ kubernetes.io/basic-auth (key username / password) mount เข้า publish ตัวเดียว
PUSH_CREDENTIALS_DIR = os.environ.get("PUSH_CREDENTIALS_DIR", "/secrets/push")
TERMINATION_LOG = os.environ.get("TERMINATION_LOG", "/dev/termination-log")
SKOPEO_POLICY = os.environ.get("SKOPEO_POLICY", "/etc/vlab-scan/policy.json")

# K8s ตัด termination message ที่ 4096 ไบต์ เผื่อไว้
MAX_RESULT_BYTES = 3500
TOP_FINDINGS = 5
MAX_TEXT = 200
MAX_TAR_MEMBERS = 200_000
CHUNK = 1024 * 1024

SEVERITY_RANK = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# รูปแบบที่ยอมรับ (ตรวจก่อนส่งเข้า tool ทุกครั้ง)
RE_UUID = re.compile(r"^[0-9a-fA-F-]{36}$")
RE_ETAG = re.compile(r"^[0-9a-fA-F]{32}(-[0-9]{1,5})?$")
RE_REGISTRY = re.compile(r"^[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?$")
RE_REPOSITORY = re.compile(
    r"^[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*(?:/[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*)*$"
)
RE_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")
RE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
RE_ARCH = re.compile(r"^[a-z0-9]{1,16}$")
RE_USERNAME = re.compile(r"^[a-z0-9_-]{1,64}$")


class Verdict(Exception):
    """จบขั้นนี้ด้วยผลที่รายงานได้ (ไม่ใช่ runner พัง)"""

    def __init__(self, verdict: str, reason: str, retryable: bool = False):
        super().__init__(reason)
        self.verdict = verdict
        self.reason = reason
        self.retryable = retryable


def fail(reason: str) -> NoReturn:
    raise Verdict("FAIL", reason)


def error(reason: str, retryable: bool) -> NoReturn:
    raise Verdict("ERROR", reason, retryable)


def log(message: str) -> None:
    print(f"[vlab-scan] {message}", file=sys.stderr, flush=True)


def clip(value: Any, limit: int = MAX_TEXT) -> str:
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ------------------------------------------------------------ config (env)


def env(name: str, default: Optional[str] = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        error(f"missing required setting {name}", retryable=False)
    return value


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        error(f"{name} must be an integer", retryable=False)
    if value < minimum:
        error(f"{name} must be >= {minimum}", retryable=False)
    return value


def checked(name: str, pattern: re.Pattern, default: Optional[str] = None) -> str:
    value = env(name, default)
    if not pattern.match(value):
        error(f"{name} has an invalid format", retryable=False)
    return value


def image_id() -> str:
    value = os.environ.get("IMAGE_ID", "")
    return value if RE_UUID.match(value) else ""


def expected_etag() -> str:
    value = os.environ.get("ETAG", "").strip().strip('"')
    return value if RE_ETAG.match(value) else ""


# ------------------------------------------------------------ state


def load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        return {"steps": {}, "verdict": None, "reasons": [], "warnings": []}
    if not isinstance(state, dict):
        raise RuntimeError("state.json is corrupted")
    return state


def save_state(state: dict) -> None:
    """เขียนไฟล์ชั่วคราวแล้ว rename (atomic) container ถูกฆ่ากลางทางก็ไม่ได้ไฟล์ครึ่งๆ"""
    fd, tmp = tempfile.mkstemp(dir=WORK_DIR, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, STATE_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def run_step(name: str, body: Callable[[dict], Optional[dict]]) -> int:
    """รันขั้นหนึ่ง ข้ามถ้ามี verdict แล้ว บันทึกผลลง state"""
    state = load_state()
    if state.get("verdict"):
        log(f"{name}: skipped (verdict already {state['verdict']})")
        return 0
    try:
        detail = body(state) or {}
        state["steps"][name] = {"ok": True, **detail}
        log(f"{name}: ok")
    except Verdict as outcome:
        state["steps"][name] = {"ok": False}
        state["verdict"] = outcome.verdict
        state["retryable"] = outcome.retryable
        state["reasons"] = list(state.get("reasons") or []) + [clip(outcome.reason)]
        log(f"{name}: {outcome.verdict} - {clip(outcome.reason)}")
    save_state(state)
    return 0


def run_tool(argv: list[str], timeout: int, env_extra: Optional[dict] = None) -> subprocess.CompletedProcess:
    """เรียก tool แบบไม่ผ่าน shell, stdin ปิด, env น้อยที่สุด"""
    child_env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", WORK_DIR),
        "TMPDIR": os.environ.get("TMPDIR", os.path.join(WORK_DIR, "tmp")),
        "LANG": "C.UTF-8",
    }
    child_env.update(env_extra or {})
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=child_env,
        check=False,
    )


def tool_error(result: subprocess.CompletedProcess) -> str:
    lines = [line for line in (result.stderr or "").splitlines() if line.strip()]
    return clip(lines[-1] if lines else f"exit code {result.returncode}")


# ------------------------------------------------------------ fetch


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """ยอม redirect เฉพาะไป https กัน URL ถูกเบนไป http หรือ file://"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("refusing non-https redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_once(url: str, expected_size: int, timeout: int) -> tuple[int, str, str]:
    # ProxyHandler({}) ไม่ใช้ proxy จาก environment
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _HttpsOnlyRedirect())
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "vlab-scan-runner"})
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    written = 0
    fd = os.open(ARCHIVE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as out, opener.open(request, timeout=timeout) as response:
        declared = response.headers.get("Content-Length")
        if declared is not None and declared.isdigit() and int(declared) != expected_size:
            raise ValueError(f"size mismatch: server reports {declared}, expected {expected_size}")
        while True:
            chunk = response.read(CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > expected_size:
                # หยุดทันที กันไฟล์ใหญ่เกินที่แจ้งไว้เต็มดิสก์
                raise ValueError("archive is larger than expected")
            out.write(chunk)
            md5.update(chunk)
            sha256.update(chunk)
        out.flush()
        os.fsync(out.fileno())
    return written, md5.hexdigest(), sha256.hexdigest()


def step_fetch(state: dict) -> dict:
    etag = expected_etag()
    if not etag:
        error("ETAG is missing or invalid", retryable=False)
    expected_size = env_int("EXPECTED_SIZE", 0, minimum=1)
    max_bytes = env_int("MAX_ARCHIVE_BYTES", 20 * 1024**3, minimum=1)
    if expected_size > max_bytes:
        fail(f"archive is {expected_size} bytes, limit is {max_bytes}")
    timeout = env_int("FETCH_TIMEOUT_SECONDS", 60, minimum=5)

    try:
        with open(DOWNLOAD_URL_FILE, "r", encoding="utf-8") as handle:
            url = handle.read().strip()
    except OSError:
        error("download URL secret is not mounted", retryable=True)
    if not url.lower().startswith("https://"):
        error("download URL must be https", retryable=False)

    last_problem = "unknown"
    for attempt in range(1, 4):
        try:
            size, md5_hex, sha_hex = _download_once(url, expected_size, timeout)
        except urllib.error.HTTPError as http_error:
            # ไม่ใส่ URL ในข้อความ (มีลายเซ็น)
            last_problem = f"HTTP {http_error.code}"
            if http_error.code in (401, 403, 404):
                break  # URL หมดอายุ / ไฟล์ถูกลบ ลองใหม่ไปก็ไม่ได้ในรอบนี้
        except (urllib.error.URLError, OSError, ValueError) as problem:
            last_problem = clip(getattr(problem, "reason", problem))
        else:
            if size != expected_size:
                last_problem = f"size mismatch: got {size}, expected {expected_size}"
            elif "-" not in etag and md5_hex != etag.lower():
                # ETag ของ R2 (PUT ก้อนเดียว) = md5 ของไฟล์; multipart มี "-N" ตรวจได้แค่ size
                last_problem = "md5 does not match ETag (file changed or corrupted in transit)"
            else:
                return {"bytes": size, "sha256": sha_hex}
        log(f"fetch: attempt {attempt} failed: {last_problem}")
        time.sleep(2 * attempt)

    try:
        os.unlink(ARCHIVE_PATH)
    except FileNotFoundError:
        pass
    error(f"download failed: {last_problem}", retryable=True)


# ------------------------------------------------------------ validate


def detect_archive_format() -> str:
    """อ่านเฉพาะ header ใน tar (ไม่แตกไฟล์) คืน docker-archive หรือ oci-archive"""
    names: set[str] = set()
    try:
        with tarfile.open(ARCHIVE_PATH, mode="r:") as archive:
            for count, member in enumerate(archive, start=1):
                if count > MAX_TAR_MEMBERS:
                    fail("archive has too many entries")
                name = member.name
                if name.startswith("/") or ".." in name.split("/"):
                    fail("archive contains unsafe paths")
                if member.isdev():
                    fail("archive contains device files")
                names.add(name.lstrip("./"))
    except tarfile.ReadError:
        fail("file is not an uncompressed tar archive (use docker save)")
    except tarfile.TarError as problem:
        fail(f"broken tar archive: {clip(problem)}")

    if "manifest.json" in names:
        return "docker-archive"
    if "index.json" in names and "oci-layout" in names:
        return "oci-archive"
    fail("tar is not a docker save / OCI image archive")


def step_validate(state: dict) -> dict:
    allowed_arch = checked("ALLOWED_ARCH", RE_ARCH, "amd64")
    transport = detect_archive_format()
    result = run_tool(
        ["skopeo", "--policy", SKOPEO_POLICY, "inspect", "--config", f"{transport}:{ARCHIVE_PATH}"],
        timeout=600,
    )
    if result.returncode != 0:
        # tar เสีย / มีหลาย image ใน tar เดียว / manifest ผิด
        fail(f"cannot read image from archive: {tool_error(result)}")
    try:
        config = json.loads(result.stdout)
    except ValueError:
        fail("image config is not valid JSON")

    os_name = config.get("os")
    arch = config.get("architecture")
    if os_name != "linux" or arch != allowed_arch:
        fail(f"image platform is {os_name}/{arch}, expected linux/{allowed_arch}")

    runtime = config.get("config") or {}
    user = str(runtime.get("User") or "")
    exposed = sorted(
        int(port.split("/")[0])
        for port in (runtime.get("ExposedPorts") or {})
        if port.split("/")[0].isdigit()
    )

    warnings = list(state.get("warnings") or [])
    if user in ("", "0", "root") or user.startswith(("0:", "root:")):
        warnings.append("image runs as root")
    declared = {
        int(port) for port in os.environ.get("DECLARED_PORTS", "").split(",") if port.strip().isdigit()
    }
    if declared and exposed and not declared.issubset(exposed):
        warnings.append(f"declared ports {sorted(declared)} not all EXPOSEd (image exposes {exposed})")
    state["warnings"] = warnings
    state["transport"] = transport
    return {"image": {"os": os_name, "architecture": arch, "user": clip(user, 64), "exposedPorts": exposed[:20]}}


# ------------------------------------------------------------ scan


def evaluate_report(report: dict, fail_severity: str, ignore_unfixed: bool) -> dict:
    """ตัดสิน policy จาก report JSON ของ Trivy (แยกเป็นฟังก์ชันล้วน ทดสอบได้โดยไม่ต้องมี Trivy)"""
    threshold = SEVERITY_RANK[fail_severity]
    counts = {name: 0 for name in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")}
    blocking: list[dict] = []
    others: list[dict] = []
    secret_blocking: list[dict] = []
    secret_warning = 0
    seen: set[tuple] = set()

    for target in report.get("Results") or []:
        for vuln in target.get("Vulnerabilities") or []:
            key = (vuln.get("VulnerabilityID"), vuln.get("PkgName"), vuln.get("InstalledVersion"))
            if key in seen:
                continue
            seen.add(key)
            severity = str(vuln.get("Severity") or "UNKNOWN").upper()
            severity = severity if severity in SEVERITY_RANK else "UNKNOWN"
            counts[severity] += 1
            fixed = str(vuln.get("FixedVersion") or "")
            item = {
                "id": clip(vuln.get("VulnerabilityID"), 40),
                "pkg": clip(vuln.get("PkgName"), 60),
                "installed": clip(vuln.get("InstalledVersion"), 40),
                "fixed": clip(fixed, 40),
                "severity": severity,
            }
            if SEVERITY_RANK[severity] >= threshold and (fixed or not ignore_unfixed):
                blocking.append(item)
            elif SEVERITY_RANK[severity] >= SEVERITY_RANK["HIGH"]:
                others.append(item)
        for secret in target.get("Secrets") or []:
            severity = str(secret.get("Severity") or "UNKNOWN").upper()
            entry = {
                "rule": clip(secret.get("RuleID"), 60),
                "title": clip(secret.get("Title"), 80),
                "target": clip(target.get("Target"), 80),
                "severity": severity,
            }
            if SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK["HIGH"]:
                secret_blocking.append(entry)
            else:
                secret_warning += 1

    rank = lambda item: -SEVERITY_RANK[item["severity"]]  # noqa: E731
    blocking.sort(key=rank)
    others.sort(key=rank)
    reasons = []
    if blocking:
        reasons.append(f"{len(blocking)} fixable {fail_severity}+ vulnerabilities")
    if secret_blocking:
        reasons.append(f"{len(secret_blocking)} embedded secrets (e.g. {secret_blocking[0]['rule']})")
    warnings = []
    if others:
        warnings.append(f"{len(others)} HIGH vulnerabilities below the fail threshold")
    if secret_warning:
        warnings.append(f"{secret_warning} low-severity secret findings")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "counts": counts,
        "secrets": len(secret_blocking) + secret_warning,
        "top": (blocking + others)[:TOP_FINDINGS],
        "secretTop": secret_blocking[:2],
    }


def trivy_version() -> str:
    result = run_tool(["trivy", "--version", "--format", "json"], timeout=60)
    try:
        return clip(json.loads(result.stdout).get("Version"), 32)
    except ValueError:
        return "unknown"


def step_scan(state: dict) -> dict:
    fail_severity = env("POLICY_FAIL_SEVERITY", "CRITICAL").upper()
    if fail_severity not in SEVERITY_RANK or fail_severity == "UNKNOWN":
        error("POLICY_FAIL_SEVERITY must be LOW, MEDIUM, HIGH or CRITICAL", retryable=False)
    ignore_unfixed = env_bool("POLICY_IGNORE_UNFIXED", True)
    timeout_minutes = env_int("TRIVY_TIMEOUT_MINUTES", 20, minimum=1)

    # ขอ severity ตั้งแต่ HIGH (หรือต่ำกว่าถ้า threshold ต่ำกว่า) เพื่อนับ warning ได้
    floor = min(SEVERITY_RANK[fail_severity], SEVERITY_RANK["HIGH"])
    severities = ",".join(name for name, rank in SEVERITY_RANK.items() if rank >= floor and name != "UNKNOWN")
    cache_dir = os.environ.get("TRIVY_CACHE_DIR", os.path.join(WORK_DIR, "trivy-cache"))

    # ไม่ใช้ --ignore-unfixed ของ Trivy: กรองเองใน evaluate_report เพื่อให้ผลตรวจสอบได้และทดสอบได้
    result = run_tool(
        [
            "trivy", "image",
            "--input", ARCHIVE_PATH,
            "--scanners", "vuln,secret",
            "--image-config-scanners", "secret",
            "--severity", severities,
            "--format", "json",
            "--output", TRIVY_REPORT_PATH,
            "--exit-code", "0",
            "--timeout", f"{timeout_minutes}m",
            "--cache-dir", cache_dir,
            "--no-progress",
            "--skip-version-check",
            "--disable-telemetry",
            "--quiet",
        ],
        timeout=timeout_minutes * 60 + 60,
    )
    if result.returncode != 0:
        # ส่วนใหญ่คือโหลด vulnerability DB ไม่ได้ (เครือข่าย) ลองใหม่ได้
        error(f"trivy failed: {tool_error(result)}", retryable=True)
    try:
        with open(TRIVY_REPORT_PATH, "r", encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, ValueError):
        error("trivy report is missing or invalid", retryable=True)

    outcome = evaluate_report(report, fail_severity, ignore_unfixed)
    state["warnings"] = list(state.get("warnings") or []) + outcome["warnings"]
    detail = {
        "trivyVersion": trivy_version(),
        "failSeverity": fail_severity,
        "counts": outcome["counts"],
        "secrets": outcome["secrets"],
        "top": outcome["top"],
    }
    if not outcome["passed"]:
        # เก็บรายละเอียดไว้ก่อนโยน FAIL (run_step จะบันทึก ok=False ทับ)
        state["scanDetail"] = {**detail, "secretTop": outcome["secretTop"]}
        fail("; ".join(outcome["reasons"]))
    return detail


# ------------------------------------------------------------ publish


def read_push_credentials() -> tuple[str, str]:
    """user / password ของ push port จากไฟล์ใน PUSH_CREDENTIALS_DIR (ไม่มี = ตั้งค่าผิด ไม่ retry)"""
    values = []
    for key in ("username", "password"):
        try:
            with open(os.path.join(PUSH_CREDENTIALS_DIR, key), "r", encoding="utf-8") as handle:
                values.append(handle.read().rstrip("\r\n"))
        except OSError:
            error("registry push credentials are not mounted", retryable=False)
    username, password = values
    if not RE_USERNAME.match(username) or not password or "\n" in password:
        error("registry push credentials have an invalid format", retryable=False)
    return username, password


def write_authfile(registry: str, username: str, password: str) -> str:
    """authfile ของ skopeo (รูปแบบเดียวกับ ~/.docker/config.json) สิทธิ์ 0600 ผู้เรียกต้องลบเอง"""
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    tmp_dir = os.environ.get("TMPDIR", os.path.join(WORK_DIR, "tmp"))
    fd, path = tempfile.mkstemp(dir=tmp_dir, prefix=".auth-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"auths": {registry: {"auth": token}}}, handle)
    except BaseException:
        os.unlink(path)
        raise
    return path


def step_push(state: dict) -> dict:
    registry = checked("REGISTRY", RE_REGISTRY)
    repository = checked("REPOSITORY", RE_REPOSITORY)
    tag = checked("TAG", RE_TAG)
    transport = state.get("transport")
    if transport not in ("docker-archive", "oci-archive"):
        error("validate step did not record the archive format", retryable=True)
    tls_verify = "true" if env_bool("REGISTRY_TLS_VERIFY", False) else "false"
    username, password = read_push_credentials()

    try:
        os.unlink(DIGEST_PATH)
    except FileNotFoundError:
        pass
    # push ทับ tag เดิมได้: (repository, tag) unique ใน DB tag นี้จึงเป็นของแถวนี้แถวเดียว
    # credential ผ่าน authfile ไม่ใช่ --dest-creds (argv มองเห็นได้ใน /proc)
    authfile = write_authfile(registry, username, password)
    try:
        result = run_tool(
            [
                "skopeo", "--policy", SKOPEO_POLICY, "copy",
                "--retry-times", "3",
                f"--dest-tls-verify={tls_verify}",
                "--dest-authfile", authfile,
                "--digestfile", DIGEST_PATH,
                f"{transport}:{ARCHIVE_PATH}",
                f"docker://{registry}/{repository}:{tag}",
            ],
            timeout=1200,
        )
    finally:
        os.unlink(authfile)
    if result.returncode != 0:
        error(f"push to registry failed: {tool_error(result)}", retryable=True)
    try:
        with open(DIGEST_PATH, "r", encoding="utf-8") as handle:
            digest = handle.read().strip()
    except OSError:
        error("push succeeded but no digest was written", retryable=True)
    if not RE_DIGEST.match(digest):
        error("registry returned an invalid digest", retryable=True)
    state["digest"] = digest
    return {"digest": digest}


def build_result(state: dict) -> dict:
    steps = state.get("steps") or {}
    verdict = state.get("verdict") or ("PASS" if state.get("digest") else "ERROR")
    reasons = list(state.get("reasons") or [])
    if verdict == "ERROR" and not reasons:
        reasons = ["scan did not complete"]
    scan = steps.get("scan") or {}
    scan_detail = scan if scan.get("ok") else (state.get("scanDetail") or {})
    summary = {
        "runnerVersion": RUNNER_VERSION,
        "trivyVersion": scan_detail.get("trivyVersion"),
        "failSeverity": scan_detail.get("failSeverity"),
        "counts": scan_detail.get("counts"),
        "secrets": scan_detail.get("secrets"),
        "top": scan_detail.get("top") or [],
        "secretTop": scan_detail.get("secretTop") or [],
        "image": (steps.get("validate") or {}).get("image"),
        "archiveSha256": (steps.get("fetch") or {}).get("sha256"),
    }
    return {
        "imageId": image_id(),
        "etag": expected_etag(),
        "verdict": verdict,
        "retryable": bool(state.get("retryable")) if verdict == "ERROR" else False,
        "reasons": [clip(r) for r in reasons][:5],
        "warnings": [clip(w) for w in (state.get("warnings") or [])][:8],
        "digest": state.get("digest") if verdict == "PASS" else None,
        "summary": {k: v for k, v in summary.items() if v not in (None, [], {})},
    }


def encode_result(result: dict) -> bytes:
    """ตัดของที่ไม่จำเป็นจนพอดี termination message ส่วนที่ reconciler ต้องใช้ไม่ถูกตัด"""
    def dump() -> bytes:
        return json.dumps(result, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    data = dump()
    summary = result["summary"]
    trimmers = [
        lambda: summary.pop("secretTop", None),
        lambda: summary.__setitem__("top", summary.get("top", [])[:2]),
        lambda: summary.pop("top", None),
        lambda: result.__setitem__("warnings", [clip(w, 80) for w in result["warnings"][:3]]),
        lambda: result.__setitem__("reasons", [clip(r, 120) for r in result["reasons"][:2]]),
        lambda: summary.pop("image", None),
    ]
    for trim in trimmers:
        if len(data) <= MAX_RESULT_BYTES:
            break
        trim()
        data = dump()
    return data


def cmd_publish() -> int:
    state = load_state()
    if state.get("verdict") is None:
        try:
            state["steps"]["publish"] = {"ok": True, **step_push(state)}
            state["verdict"] = "PASS"
        except Verdict as outcome:
            state["verdict"] = outcome.verdict
            state["retryable"] = outcome.retryable
            state["reasons"] = list(state.get("reasons") or []) + [clip(outcome.reason)]
        save_state(state)

    data = encode_result(build_result(state))
    # เขียนผลไม่ได้ = backend ไม่มีทางรู้ผล ให้ Pod ล้มเพื่อให้ reconciler retry
    with open(TERMINATION_LOG, "wb") as handle:
        handle.write(data)
    log(f"publish: verdict {state['verdict']}")
    return 0


# ------------------------------------------------------------ entry


def cmd_version() -> int:
    skopeo = run_tool(["skopeo", "--version"], timeout=30)
    print(json.dumps({
        "runner": RUNNER_VERSION,
        "python": sys.version.split()[0],
        "trivy": trivy_version(),
        "skopeo": clip(skopeo.stdout.strip().split()[-1] if skopeo.stdout.strip() else "unknown", 32),
    }))
    return 0


COMMANDS: dict[str, Callable[[], int]] = {
    "fetch": lambda: run_step("fetch", step_fetch),
    "validate": lambda: run_step("validate", step_validate),
    "scan": lambda: run_step("scan", step_scan),
    "publish": cmd_publish,
    "version": cmd_version,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(f"usage: runner.py {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    os.umask(0o077)
    if argv[1] != "version":
        os.makedirs(os.environ.get("TMPDIR", os.path.join(WORK_DIR, "tmp")), mode=0o700, exist_ok=True)
    return COMMANDS[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
