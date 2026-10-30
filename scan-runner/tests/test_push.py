"""step_push: credential ของ push port ไม่เรียก skopeo จริง

รัน: python3 -m pytest scan-runner/tests
"""
import base64
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import runner  # noqa: E402

DIGEST = "sha256:" + "b" * 64


@pytest.fixture
def work(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    creds = tmp_path / "push"
    creds.mkdir()
    (creds / "username").write_text("scanner")
    (creds / "password").write_text("Sup3r-Secret-Pass")
    monkeypatch.setattr(runner, "WORK_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "ARCHIVE_PATH", str(tmp_path / "image.tar"))
    monkeypatch.setattr(runner, "DIGEST_PATH", str(tmp_path / "digest"))
    monkeypatch.setattr(runner, "PUSH_CREDENTIALS_DIR", str(creds))
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setenv("REGISTRY", "100.64.0.3:5002")
    monkeypatch.setenv("REPOSITORY", "vlab/demo")
    monkeypatch.setenv("TAG", "v1")
    return tmp_path


@pytest.fixture
def skopeo(monkeypatch):
    """แทน run_tool: เก็บ argv และเนื้อหา authfile ตอนถูกเรียก แล้วเขียน digest แบบ skopeo"""
    calls = []

    def fake(argv, timeout, env_extra=None):
        authfile = argv[argv.index("--dest-authfile") + 1]
        with open(authfile, encoding="utf-8") as handle:
            calls.append({"argv": argv, "authfile": authfile, "auth": json.load(handle),
                          "mode": os.stat(authfile).st_mode & 0o777})
        with open(argv[argv.index("--digestfile") + 1], "w", encoding="utf-8") as handle:
            handle.write(DIGEST)
        return subprocess.CompletedProcess(argv, fake.returncode, "", fake.stderr)

    fake.returncode, fake.stderr = 0, ""
    fake.calls = calls
    monkeypatch.setattr(runner, "run_tool", fake)
    return fake


STATE = {"transport": "docker-archive"}


def test_push_uses_temporary_authfile(work, skopeo):
    assert runner.step_push(dict(STATE)) == {"digest": DIGEST}

    call = skopeo.calls[0]
    assert call["argv"][-1] == "docker://100.64.0.3:5002/vlab/demo:v1"
    token = call["auth"]["auths"]["100.64.0.3:5002"]["auth"]
    assert base64.b64decode(token).decode() == "scanner:Sup3r-Secret-Pass"
    assert call["mode"] == 0o600
    # รหัสไม่อยู่ใน argv และ authfile ถูกลบหลัง push
    assert not any("Sup3r-Secret-Pass" in arg for arg in call["argv"])
    assert not os.path.exists(call["authfile"])
    assert os.listdir(work / "tmp") == []


def test_push_failure_is_retryable_and_removes_authfile(work, skopeo):
    skopeo.returncode, skopeo.stderr = 1, "unauthorized: authentication required"
    with pytest.raises(runner.Verdict) as outcome:
        runner.step_push(dict(STATE))
    assert outcome.value.verdict == "ERROR"
    assert outcome.value.retryable is True
    assert "Sup3r-Secret-Pass" not in outcome.value.reason
    assert os.listdir(work / "tmp") == []


def test_authfile_removed_when_skopeo_crashes(work, monkeypatch):
    def boom(argv, timeout, env_extra=None):
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(runner, "run_tool", boom)
    with pytest.raises(subprocess.TimeoutExpired):
        runner.step_push(dict(STATE))
    assert os.listdir(work / "tmp") == []


@pytest.mark.parametrize("missing", ["username", "password"])
def test_missing_credentials_is_a_config_error(work, skopeo, missing):
    os.unlink(os.path.join(runner.PUSH_CREDENTIALS_DIR, missing))
    with pytest.raises(runner.Verdict) as outcome:
        runner.step_push(dict(STATE))
    assert outcome.value.verdict == "ERROR"
    assert outcome.value.retryable is False
    assert skopeo.calls == []


@pytest.mark.parametrize("username,password", [("Scanner!", "x" * 12), ("scanner", ""), ("scanner", "a\nb")])
def test_invalid_credentials_are_rejected(work, skopeo, username, password):
    creds = runner.PUSH_CREDENTIALS_DIR
    with open(os.path.join(creds, "username"), "w", encoding="utf-8") as handle:
        handle.write(username)
    with open(os.path.join(creds, "password"), "w", encoding="utf-8") as handle:
        handle.write(password)
    with pytest.raises(runner.Verdict) as outcome:
        runner.step_push(dict(STATE))
    assert outcome.value.retryable is False
    assert skopeo.calls == []


def test_trailing_newline_in_secret_file_is_ignored(work, skopeo):
    with open(os.path.join(runner.PUSH_CREDENTIALS_DIR, "password"), "w", encoding="utf-8") as handle:
        handle.write("Sup3r-Secret-Pass\n")
    runner.step_push(dict(STATE))
    token = skopeo.calls[0]["auth"]["auths"]["100.64.0.3:5002"]["auth"]
    assert base64.b64decode(token).decode() == "scanner:Sup3r-Secret-Pass"
