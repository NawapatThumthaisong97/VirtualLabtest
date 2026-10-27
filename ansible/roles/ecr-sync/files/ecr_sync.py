#!/usr/bin/env python3
"""
vlab-ecr-sync: คัดลอก image จาก camp registry ขึ้น ECR (รันจาก systemd timer บนเครื่อง registry)

ทุกรอบ:
  1. อ่าน repository / tag ทั้งหมดจาก camp registry (HTTP API v2)
  2. เทียบ digest กับ ECR (describe_images) ต่อ repository
  3. tag ที่ไม่มีบน ECR -> สร้าง repository (IMMUTABLE, scan on push) ถ้ายังไม่มี แล้ว skopeo copy
  4. ตรวจว่า digest บน ECR ตรงกับต้นทางหลัง copy

tag ที่มีบน ECR แล้วแต่ digest ต่างกัน: ไม่เขียนทับ (lab ที่รันอยู่อาจใช้ตัวเดิม) log เป็น error
ไม่ลบอะไรบน ECR: image ที่ถูกลบจาก camp registry ยังอยู่บน ECR ให้ lifecycle policy ของ ECR จัดการ

ความปลอดภัย:
- key AWS มาจาก $CREDENTIALS_DIRECTORY (systemd LoadCredential) ไม่ผ่าน environment / argv
- token ECR เขียนเป็น authfile 0600 ใน $RUNTIME_DIRECTORY แล้วลบทิ้งทุกรอบ ไม่ log
- ตรวจชื่อ repository / tag ก่อนใช้ เรียก skopeo ด้วย argv list (ไม่ผ่าน shell)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

RE_ECR_HOST = re.compile(r"^(\d{12})\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com$")
RE_SOURCE = re.compile(r"^[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?$")
# กติกาชื่อ repository ของ ECR (เข้มกว่าของ registry:2)
RE_REPOSITORY = re.compile(r"^(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)*[a-z0-9]+(?:[._-][a-z0-9]+)*$")
RE_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
RE_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')

MANIFEST_ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])
HTTP_TIMEOUT = 30
CREDENTIAL_KEYS = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}

log = logging.getLogger("vlab-ecr-sync")


class SyncError(Exception):
    pass


# ---------- config ----------

def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def compile_optional(name: str) -> re.Pattern | None:
    value = env(name)
    try:
        return re.compile(value) if value else None
    except re.error as error:
        raise SyncError(f"{name} is not a valid regex: {error}") from error


def load_aws_credentials() -> dict[str, str]:
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise SyncError("CREDENTIALS_DIRECTORY not set (run via systemd LoadCredential)")
    values: dict[str, str] = {}
    with open(os.path.join(directory, "aws.env"), encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in CREDENTIAL_KEYS:
                values[key] = value.strip()
    if set(values) != CREDENTIAL_KEYS or not all(values.values()):
        raise SyncError("aws.env must contain AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    return values


# ---------- camp registry (ต้นทาง) ----------

class SourceRegistry:
    def __init__(self, host: str):
        self.base = f"http://{host}"

    def _request(self, path: str, method: str = "GET", accept: str | None = None):
        request = urllib.request.Request(self.base + path, method=method)
        if accept:
            request.add_header("Accept", accept)
        return urllib.request.urlopen(request, timeout=HTTP_TIMEOUT)  # noqa: S310 (host ตรวจแล้ว)

    def repositories(self) -> list[str]:
        repos: list[str] = []
        path: str | None = "/v2/_catalog?n=1000"
        while path:
            with self._request(path) as response:
                repos.extend(json.load(response).get("repositories") or [])
                match = RE_NEXT_LINK.search(response.headers.get("Link", ""))
            path = None
            if match:
                parsed = urllib.parse.urlsplit(match.group(1))
                path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        return repos

    def tags(self, repo: str) -> list[str]:
        try:
            with self._request(f"/v2/{repo}/tags/list") as response:
                return json.load(response).get("tags") or []
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return []
            raise

    def digest(self, repo: str, tag: str) -> str | None:
        try:
            with self._request(f"/v2/{repo}/manifests/{tag}", "HEAD", MANIFEST_ACCEPT) as response:
                return response.headers.get("Docker-Content-Digest")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise


# ---------- ECR (ปลายทาง) ----------

class Ecr:
    def __init__(self, host: str, region: str, credentials: dict[str, str]):
        self.host = host
        session = boto3.session.Session(
            aws_access_key_id=credentials["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=credentials["AWS_SECRET_ACCESS_KEY"],
            region_name=region,
        )
        self.client = session.client(
            "ecr", config=Config(retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=10, read_timeout=60)
        )
        self.registry_id = RE_ECR_HOST.match(host).group(1)

    def write_authfile(self, directory: str) -> str:
        data = self.client.get_authorization_token(registryIds=[self.registry_id])["authorizationData"][0]
        fd, path = tempfile.mkstemp(prefix="auth-", suffix=".json", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            # authorizationToken เป็น base64("AWS:<password>") อยู่แล้ว ตรงกับรูปแบบ auth.json
            json.dump({"auths": {self.host: {"auth": data["authorizationToken"]}}}, handle)
        os.chmod(path, 0o600)
        return path

    def tag_digests(self, repo: str) -> dict[str, str] | None:
        """tag -> digest ของ repo นี้, None = ยังไม่มี repository"""
        result: dict[str, str] = {}
        paginator = self.client.get_paginator("describe_images")
        try:
            for page in paginator.paginate(
                registryId=self.registry_id, repositoryName=repo, filter={"tagStatus": "TAGGED"}
            ):
                for detail in page.get("imageDetails", []):
                    for tag in detail.get("imageTags") or []:
                        result[tag] = detail["imageDigest"]
        except self.client.exceptions.RepositoryNotFoundException:
            return None
        return result

    def ensure_repository(self, repo: str) -> None:
        try:
            self.client.create_repository(
                registryId=self.registry_id,
                repositoryName=repo,
                imageTagMutability="IMMUTABLE",
                imageScanningConfiguration={"scanOnPush": True},
                encryptionConfiguration={"encryptionType": "AES256"},
                tags=[{"Key": "managed-by", "Value": "vlab-ecr-sync"}],
            )
            log.info("created ECR repository %s", repo)
        except self.client.exceptions.RepositoryAlreadyExistsException:
            pass

    def digest(self, repo: str, tag: str) -> str | None:
        try:
            response = self.client.describe_images(
                registryId=self.registry_id, repositoryName=repo, imageIds=[{"imageTag": tag}]
            )
        except self.client.exceptions.ImageNotFoundException:
            return None
        details = response.get("imageDetails") or []
        return details[0]["imageDigest"] if details else None


# ---------- copy ----------

def skopeo_copy(source: str, ecr_host: str, repo: str, tag: str, authfile: str, policy: str, timeout: int) -> None:
    argv = [
        "skopeo", "--policy", policy, "copy", "--all",
        "--src-tls-verify=false",  # camp registry เป็น HTTP บน localhost
        "--dest-authfile", authfile,
        f"docker://{source}/{repo}:{tag}",
        f"docker://{ecr_host}/{repo}:{tag}",
    ]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise SyncError(f"skopeo copy timed out after {timeout}s") from error
    if result.returncode != 0:
        raise SyncError(f"skopeo copy failed: {result.stderr.strip()[-500:]}")


def wanted(repo: str, include: re.Pattern | None, exclude: re.Pattern | None) -> bool:
    if include and not include.search(repo):
        return False
    return not (exclude and exclude.search(repo))


def run() -> int:
    ecr_host = env("ECR_REGISTRY")
    match = RE_ECR_HOST.match(ecr_host)
    if not match:
        raise SyncError("ECR_REGISTRY must look like <account>.dkr.ecr.<region>.amazonaws.com")
    source_host = env("SOURCE_REGISTRY", "localhost:5001")
    if not RE_SOURCE.match(source_host):
        raise SyncError("SOURCE_REGISTRY is invalid")
    include, exclude = compile_optional("INCLUDE_REGEX"), compile_optional("EXCLUDE_REGEX")
    max_copies = int(env("MAX_COPIES", "20"))
    timeout = int(env("COPY_TIMEOUT", "3600"))
    policy = env("SKOPEO_POLICY", "/opt/vlab-ecr-sync/policy.json")
    runtime_dir = os.environ.get("RUNTIME_DIRECTORY") or tempfile.gettempdir()

    source = SourceRegistry(source_host)
    ecr = Ecr(ecr_host, match.group(2), load_aws_credentials())

    # หา tag ที่ต้อง copy ก่อน ขอ token เฉพาะรอบที่มีงานจริง
    pending: list[tuple[str, str, str]] = []
    failures = 0
    for repo in sorted(source.repositories()):
        if not wanted(repo, include, exclude):
            continue
        if not RE_REPOSITORY.match(repo) or len(repo) > 256:
            log.warning("skip %s: name not allowed by ECR", repo)
            continue
        remote = ecr.tag_digests(repo)
        for tag in sorted(source.tags(repo)):
            if not RE_TAG.match(tag):
                log.warning("skip %s:%s: invalid tag", repo, tag)
                continue
            local_digest = source.digest(repo, tag)
            if not local_digest:
                continue
            remote_digest = (remote or {}).get(tag)
            if remote_digest == local_digest:
                continue
            if remote_digest:
                # IMMUTABLE: ห้ามทับ ต้องใช้ tag ใหม่
                log.error("conflict %s:%s: ECR has %s, camp registry has %s", repo, tag, remote_digest, local_digest)
                failures += 1
                continue
            pending.append((repo, tag, local_digest))

    if not pending:
        log.info("up to date")
        return 1 if failures else 0

    authfile = ecr.write_authfile(runtime_dir)
    copied = 0
    try:
        for repo, tag, local_digest in pending[:max_copies]:
            try:
                ecr.ensure_repository(repo)
                log.info("copy %s:%s (%s)", repo, tag, local_digest)
                skopeo_copy(source_host, ecr_host, repo, tag, authfile, policy, timeout)
                pushed = ecr.digest(repo, tag)
                if pushed != local_digest:
                    raise SyncError(f"digest mismatch after copy: ECR {pushed}, source {local_digest}")
                copied += 1
            except (SyncError, ClientError, BotoCoreError) as error:
                log.error("failed %s:%s: %s", repo, tag, error)
                failures += 1
    finally:
        os.remove(authfile)

    left = max(0, len(pending) - max_copies)
    log.info("copied %d, failed %d, deferred %d", copied, failures, left)
    return 1 if failures else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    try:
        return run()
    except (SyncError, ClientError, BotoCoreError, urllib.error.URLError, OSError, ValueError) as error:
        log.error("%s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
