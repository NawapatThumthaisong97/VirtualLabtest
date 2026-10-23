#!/usr/bin/env python3
"""vlab-tui.py - หน้าจอ monitor + เทส Ansible / launch แบบ btop (ดู docs/archive/TEST_ALL.md)

กล่องบนจอ: cluster (node / นาฬิกา / ทาง backend→master), skypilot server (health / memory / auth),
tests (รายการเทส ✅ ❌), ของที่เปิดอยู่ (lab pod / session / EC2) และ log สำคัญของ backend
เปิดทิ้งไว้เฉย ๆ = monitor สด กดปุ่มเพื่อรันเทส:
    a ansible   i infra   l launch   t ทั้งหมด   d ลบของค้าง   q ออก

ข้อมูลทั้งหมดดึงด้วยคำสั่งเดิม (kubectl / curl / ssh / aws / ansible) ไม่ import โค้ด backend
ใช้ python3 ของเครื่องที่มี rich (ThinkPad มีอยู่แล้ว)

ใช้ (รันจาก root ของ repo):
    ./script/vlab-tui.py                     # TUI
    ./script/vlab-tui.py --plain infra       # ไม่มีจอ: พิมพ์ทีละบรรทัด แล้วจบด้วยตารางสรุป (ansible|infra|launch|all)

ค่าตั้งต้นแก้ด้วย env: BACKEND_URL USER_ID LAB_K8S LAB_AWS LAB_AUTO MASTER WORKER WEB SKY_URL SKIP_AWS=1 YES=1
"""

import argparse
import base64
import collections
import datetime as dt
import json
import os
import re
import select
import subprocess
import sys
import termios
import threading
import time
import tty
import urllib.error
import urllib.request
from pathlib import Path

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

ROOT = Path(__file__).resolve().parent.parent
ANSIBLE_DIR = ROOT / "ansible"
INVENTORY = "inventory.home.yml"

BACKEND_URL = os.environ.get("BACKEND_URL", "http://100.102.72.39:8000")
API = BACKEND_URL + "/api"
SKY_URL = os.environ.get("SKY_URL", "http://100.125.244.48:30880")   # NodePort ผ่าน Tailscale
MASTER = os.environ.get("MASTER", "vboxuser@100.125.244.48")
WORKER = os.environ.get("WORKER", "vboxuser@100.83.96.97")           # เครื่องแลปที่ใช้เทส
WEB = os.environ.get("WEB", "web@100.102.72.39")                     # เครื่อง web-service
WEB_DIR = "/opt/web-service"
LAB_K8S = os.environ.get("LAB_K8S", "03a18386-1558-4bcf-9399-4b79cc1ae22b")
LAB_AWS = os.environ.get("LAB_AWS", "536989c2-52d1-4169-b23a-ed06247cdb57")
LAB_AUTO = os.environ.get("LAB_AUTO", "035a1861-3b1b-4309-8600-22cab0d06439")
USER_EMAIL = "sophia.dav@dome.tu.ac.th"
SKIP_AWS = os.environ.get("SKIP_AWS") == "1"
YES = os.environ.get("YES") == "1"
AWS = ["aws", "--profile", "skypilot", "--region", "ap-southeast-1"]   # ห้ามใช้ profile default (root)
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6"]
BACKEND_EXEC = f"docker exec virtual_lab_backend"

LOG_DIR = Path(f"/tmp/vlab-test-{dt.datetime.now():%Y%m%d-%H%M%S}")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
BACKEND_LOG_PATTERN = re.compile(
    r"\[auto\]|\[warm pod\]|launch failed|cluster_operation_error|Prewarm scheduler:|Traceback|ERROR")


# ---------- helpers

def run(cmd, timeout=30, cwd=None, stdin=None):
    """รันคำสั่ง คืน (rc, stdout+stderr) — timeout = rc 124"""
    try:
        # ไม่ส่ง stdin = DEVNULL — ไม่งั้น ssh / ansible แย่งอ่านปุ่มที่กดใน TUI / คำตอบ y/n
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, input=stdin,
                           stdin=None if stdin is not None else subprocess.DEVNULL)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError as e:
        return 127, str(e)


def ssh(host, command, timeout=30, stdin=None):
    return run(SSH + [host, command], timeout=timeout, stdin=stdin)


def http(url, method="GET", data=None, auth=None, timeout=10):
    """คืน (status, body, วินาที) — ต่อไม่ติด = status 0"""
    req = urllib.request.Request(url, method=method, data=json.dumps(data).encode() if data else None)
    # Cloudflare ตอบ 403 กับ user-agent ของ Python (Python-urllib) ก่อนถึง tunnel เลยใช้ชื่อแบบ curl
    req.add_header("User-Agent", "curl/8 vlab-tui")
    if data:
        req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace"), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), time.monotonic() - t0
    except Exception as e:
        return 0, str(e), time.monotonic() - t0


def group_var(name):
    """อ่านค่าจาก group_vars/all.yml (ไม่พิมพ์ออกจอ ใช้แค่ใน request)"""
    try:
        text = (ANSIBLE_DIR / "group_vars" / "all.yml").read_text()
    except OSError:
        return ""
    m = re.search(rf'^{name}:\s*"?([^"\n]*)"?\s*$', text, re.M)
    return m.group(1).strip() if m else ""


def mib(value):
    """'2337Mi' / '4Gi' / '1500000Ki' → MiB"""
    m = re.match(r"(\d+)(Ki|Mi|Gi)?", value or "")
    if not m:
        return 0
    n, unit = int(m.group(1)), m.group(2)
    return {"Ki": n // 1024, "Mi": n, "Gi": n * 1024}.get(unit, n // (1024 * 1024))


def spark(values, width):
    blocks = "▁▂▃▄▅▆▇█"
    values = list(values)[-width:]
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    return "".join(blocks[int((v - lo) / span * (len(blocks) - 1))] for v in values)


def meter(frac, width=20):
    """แถบแบบ btop เขียว → เหลือง → แดง"""
    frac = max(0.0, min(1.0, frac))
    n = round(frac * width)
    t = Text()
    for i in range(width):
        pos = i / width
        color = "green" if pos < 0.6 else "yellow" if pos < 0.85 else "red"
        t.append("■", style=color if i < n else "grey23")
    return t


def ago(ts):
    return f"{int(time.time() - ts)}s" if ts else "-"


# ---------- state (เขียนจาก thread, อ่านตอนวาดจอ)

class Test:
    def __init__(self, tid, group, name, fn):
        self.tid, self.group, self.name, self.fn = tid, group, name, fn
        self.status = "wait"   # wait | run | ok | fail | skip
        self.detail = ""
        self.t0 = self.t1 = None

    @property
    def elapsed(self):
        if not self.t0:
            return ""
        s = int((self.t1 or time.time()) - self.t0)
        return f"{s // 60:02d}:{s % 60:02d}"


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.nodes = []                 # [(name, ready, ip)]
        self.clocks = {}                # host → offset (วินาที) / None
        self.probe = collections.deque(maxlen=120)   # (time, ok, sec) backend → master ทุก 1s
        self.sky_health = (0, 0.0)
        self.sky_mem = collections.deque(maxlen=150)  # MiB ทุก 2s ≈ 5 นาที
        self.sky_limit = 0
        self.sky_restarts = None
        self.sky_restarts_start = None
        self.auth = None                # (none, wrong, right)
        self.cloudflare = None
        self.sky_infra = None           # จาก infra I10
        self.lab_pods = []              # [(name, node, phase)]
        self.warm = []                  # DaemonSet prewarm / warm
        self.sessions = []              # session ของ user ที่ running / pending
        self.ec2 = []                   # [(id, ip, public, cluster)]
        self.updated = {}
        self.log = collections.deque(maxlen=200)
        self.tests = []
        self.running = None             # ชื่อชุดที่กำลังรัน
        self.prompt = None              # (คำถาม, Event, [คำตอบ])
        self.created = set()            # session ที่ script สร้าง (ลบตอนออก)
        self.user_id = os.environ.get("USER_ID", "")
        self.peak_mem = 0
        self.stop = threading.Event()


S = State()
LOG_DIR.mkdir(parents=True, exist_ok=True)
_runner_log = open(LOG_DIR / "runner.log", "a")
PLAIN = False
console = Console()


def log(msg, style=""):
    line = f"{dt.datetime.now():%H:%M:%S} {msg}"
    with S.lock:
        S.log.append((line, style))
    _runner_log.write(ANSI.sub("", line) + "\n")
    _runner_log.flush()
    if PLAIN:
        console.print(Text(line, style=style or "grey62"))


def ask(question, default=False):
    """ถาม y/n — TUI ขึ้นกล่องในจอ, --plain ใช้ input(), YES=1 ตอบ yes ให้"""
    if YES:
        return True
    if PLAIN:
        ans = input(f"{Text.from_markup(question).plain} [{'Y/n' if default else 'y/N'}] ").strip().lower()
        return default if not ans else ans.startswith("y")
    ev, box_ = threading.Event(), [default]
    with S.lock:
        S.prompt = (question, ev, box_, default)
    ev.wait()
    with S.lock:
        S.prompt = None
    return box_[0]


# ---------- monitor (thread)

def poll_fast():
    """ทุก 2s: node, health / memory / restart ของ server, lab pod, session"""
    while not S.stop.is_set():
        rc, out = run(["kubectl", "get", "nodes", "-o", "json"], timeout=8)
        nodes = []
        if rc == 0:
            for n in json.loads(out)["items"]:
                ready = next((c["status"] for c in n["status"]["conditions"] if c["type"] == "Ready"), "?")
                ip = next((a["address"] for a in n["status"]["addresses"] if a["type"] == "InternalIP"), "")
                nodes.append((n["metadata"]["name"], ready == "True", ip))
        code, _, sec = http(SKY_URL + "/api/health", timeout=4)

        rc, out = run(["kubectl", "get", "pod", "-n", "skypilot", "-o", "json"], timeout=8)
        restarts, limit = None, 0
        if rc == 0:
            for p in json.loads(out)["items"]:
                for c in p["spec"]["containers"]:
                    if c["name"] == "skypilot-api":
                        limit = mib(c.get("resources", {}).get("limits", {}).get("memory", ""))
                for cs in p["status"].get("containerStatuses", []):
                    if cs["name"] == "skypilot-api":
                        restarts = cs["restartCount"]
        rc, out = run(["kubectl", "top", "pod", "-n", "skypilot", "--no-headers"], timeout=8)
        mem = next((mib(l.split()[2]) for l in out.splitlines() if "api-server" in l), 0) if rc == 0 else 0

        rc, out = run(["kubectl", "get", "pods", "-A", "-l", "vlab/lab=true", "-o", "json"], timeout=8)
        pods = []
        if rc == 0:
            for p in json.loads(out)["items"]:
                pods.append((p["metadata"]["name"], p["spec"].get("nodeName", "-"), p["status"]["phase"]))
        rc, out = run(["kubectl", "get", "ds", "-n", "default", "--no-headers"], timeout=8)
        warm = [l.split()[0] for l in out.splitlines() if l.startswith(("prewarm-", "warm-"))] if rc == 0 else []

        code_s, body, _ = http(API + "/sessions", timeout=8)
        sessions = []
        if code_s == 200 and S.user_id:
            for s in json.loads(body).get("data") or []:
                if s.get("user_id") == S.user_id and s.get("status") in ("running", "pending"):
                    sessions.append(s)

        with S.lock:
            S.nodes, S.sky_health, S.sky_limit = nodes, (code, sec), limit
            if restarts is not None:
                S.sky_restarts = restarts
                if S.sky_restarts_start is None:
                    S.sky_restarts_start = restarts
            if mem:
                S.sky_mem.append(mem)
                S.peak_mem = max(S.peak_mem, mem)
            S.lab_pods, S.warm, S.sessions = pods, warm, sessions
            S.updated["fast"] = time.time()
        S.stop.wait(2)


def poll_slow():
    """ทุก 15s: นาฬิกาแต่ละเครื่อง, EC2, auth, Cloudflare"""
    domain, pw = group_var("skypilot_domain"), group_var("skypilot_admin_password")
    while not S.stop.is_set():
        clocks = {}
        for name, host in (("master", MASTER), ("worker-pete", WORKER), ("webservice", WEB)):
            t0 = time.time()
            rc, out = ssh(host, "date +%s.%N", timeout=10)
            t1 = time.time()
            try:
                clocks[name] = float(out.strip()) - (t0 + t1) / 2 if rc == 0 else None
            except ValueError:
                clocks[name] = None

        rc, out = run(AWS + ["ec2", "describe-instances",
                             "--filters", "Name=tag-key,Values=skypilot-cluster-name",
                             "Name=instance-state-name,Values=pending,running",
                             "--query", "Reservations[].Instances[].[InstanceId,PrivateIpAddress,PublicIpAddress,"
                                        "Tags[?Key==`skypilot-cluster-name`]|[0].Value]",
                             "--output", "json"], timeout=20)
        ec2 = [tuple(i) for i in json.loads(out)] if rc == 0 else None

        a = None
        if pw:
            a = tuple(http(SKY_URL + "/dashboard/", auth=au, timeout=6)[0]
                      for au in (None, "admin:wrong-password", f"admin:{pw}"))
        cf = http(f"https://{domain}/dashboard/", timeout=8)[0] if domain else None

        with S.lock:
            S.clocks, S.auth, S.cloudflare = clocks, a, cf
            if ec2 is not None:
                S.ec2 = ec2
            S.updated["slow"] = time.time()
        S.stop.wait(15)


def stream(cmd, on_line, name):
    """ssh ค้างไว้อ่านทีละบรรทัด หลุดแล้วต่อใหม่"""
    while not S.stop.is_set():
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1)
            for line in p.stdout:
                if S.stop.is_set():
                    break
                on_line(line.rstrip("\n"))
            p.kill()
        except Exception as e:
            log(f"[{name}] {e}", "red")
        S.stop.wait(3)


def on_probe(line):
    # "<epoch> <http_code> <seconds>" จากเครื่อง webservice
    parts = line.split()
    if len(parts) == 3:
        with S.lock:
            S.probe.append((time.time(), parts[1] == "200", float(parts[2])))


_backend_log = open(LOG_DIR / "backend.log", "a")


def on_backend_log(line):
    _backend_log.write(line + "\n")
    if BACKEND_LOG_PATTERN.search(line) and not line.startswith("INFO:server:") and "WARNING:server:" not in line:
        style = "red" if re.search(r"failed|error|Traceback", line, re.I) else "cyan"
        log("backend " + ANSI.sub("", line).replace("[Server] : ", "")[:220], style)


def start_monitor():
    for fn in (poll_fast, poll_slow):
        threading.Thread(target=fn, daemon=True).start()
    probe = (f"while true; do echo \"$(date +%s) $(curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}' "
             f"--max-time 3 {SKY_URL}/api/health)\"; sleep 1; done")
    threading.Thread(target=stream, args=(SSH + [WEB, probe], on_probe, "probe"), daemon=True).start()
    threading.Thread(target=stream, args=(SSH + [WEB, "docker logs -f --since 1s virtual_lab_backend 2>&1"],
                                          on_backend_log, "backend log"), daemon=True).start()


# ---------- tests: ansible

def ansible(cmd, timeout=120):
    return run(cmd, timeout=timeout, cwd=ANSIBLE_DIR)


def t_syntax(t):
    rc, out = ansible(["ansible-playbook", "-i", INVENTORY, "site.yml", "--syntax-check"])
    return rc == 0, "ok" if rc == 0 else out.strip().splitlines()[-1][:120]


def t_reach(t):
    rc, out = ansible(["ansible", "-i", INVENTORY, "all:!registry", "-b", "-o", "-m", "command", "-a", "hostname"])
    ok = [l.split()[0] for l in out.splitlines() if "rc=0" in l]
    bad = [l.split()[0] for l in out.splitlines() if "FAILED" in l or "UNREACHABLE" in l]
    return not bad and rc == 0, f"sudo ได้ {len(ok)} เครื่อง" + (f"  ไม่ได้: {', '.join(bad)}" if bad else "")


def t_playbook(group):
    def fn(t):
        if not ask(f"รัน playbook จริงบนกลุ่ม [b]{group}[/b] ?"):
            return None, "ข้าม (ตอบ n)"
        logf = LOG_DIR / f"playbook-{group}.log"
        cmd = ["ansible-playbook", "-i", INVENTORY, "site.yml", "--limit", group]
        log(f"$ {' '.join(cmd)}  (log: {logf})")
        recap = ""
        with open(logf, "w") as f:
            p = subprocess.Popen(cmd, cwd=ANSIBLE_DIR, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                f.write(line)
                m = re.match(r"TASK \[(.+?)\]", line)
                if m:
                    t.detail = m.group(1)[:60]
                if re.search(r"\bok=\d+.*failed=", line):
                    recap = line
                if line.startswith("fatal:") and "...ignoring" not in line:
                    log(f"[{group}] {line.strip()[:200]}", "red")
            p.wait()
        failed = int(re.search(r"failed=(\d+)", recap).group(1)) if recap else -1
        unreach = int(re.search(r"unreachable=(\d+)", recap).group(1)) if recap else -1
        changed = re.search(r"changed=(\d+)", recap)
        ok = p.returncode == 0 and failed == 0 and unreach == 0
        return ok, f"failed={failed} unreachable={unreach} changed={changed.group(1) if changed else '?'}"
    return fn


# ---------- tests: infra (อ่านอย่างเดียว)

def t_nodes(t):
    with S.lock:
        nodes = list(S.nodes)
    names = {n for n, ready, _ in nodes if ready}
    bad = [n for n, ready, _ in nodes if not ready]
    ok = {"master", "worker-pete"} <= names and not bad
    return ok, " ".join(f"{n}:{'Ready' if r else 'NotReady'}" for n, r, _ in nodes)


def t_nodeport(t):
    res = [http(SKY_URL + "/api/health", timeout=5) for _ in range(5)]
    ok = all(c == 200 and s < 0.5 for c, _, s in res)
    return ok, " ".join(f"{c}/{s:.2f}s" for c, _, s in res)


def t_auth(t):
    pw = group_var("skypilot_admin_password")
    codes = [http(SKY_URL + "/dashboard/", auth=a, timeout=6)[0] for a in (None, "admin:wrong-password", f"admin:{pw}")]
    return codes == [401, 401, 200], "/".join(map(str, codes)) + " (คาด 401/401/200)"


def t_server(t):
    with S.lock:
        limit, restarts = S.sky_limit, S.sky_restarts
    return limit == 4096 and restarts == 0, f"limit {limit}Mi  restart {restarts}"


def t_api_info(t):
    rc, out = ssh(WEB, f"{BACKEND_EXEC} sky api info", timeout=60)
    ok = "HEALTHY" in out and "vlab-backend" in out
    line = next((l for l in ANSI.sub("", out).splitlines() if "User:" in l), out.strip()[-100:])
    return ok, line.strip(" ├└─")


def t_identity(t):
    rc, out = ssh(WEB, f"{BACKEND_EXEC} python -c \"import boto3;print(boto3.client('sts').get_caller_identity()['Arn'])\"",
                  timeout=60)
    arn = out.strip().splitlines()[-1] if out.strip() else "?"
    return arn.endswith("user/Skypilot-IAM"), arn[-60:]


def t_clocks(t):
    with S.lock:
        clocks = dict(S.clocks)
    if not clocks:
        return False, "ยังไม่มีข้อมูล (รอ 15s)"
    ok = all(v is not None and abs(v) < 30 for v in clocks.values())
    return ok, "  ".join(f"{k} {'?' if v is None else f'{v:+.0f}s'}" for k, v in clocks.items())


def t_probe(t):
    start = time.time()
    while time.time() - start < 32:
        with S.lock:
            n = len([p for p in S.probe if p[0] >= start])
        t.detail = f"เก็บ {n}/30"
        if n >= 30:
            break
        time.sleep(1)
    with S.lock:
        samples = [p for p in S.probe if p[0] >= start]
    lost = [p for p in samples if not p[1]]
    worst = max((p[2] for p in samples), default=0)
    return (len(samples) >= 25 and not lost), f"{len(samples)} ครั้ง หลุด {len(lost)}  ช้าสุด {worst:.2f}s"


def t_cloudflare(t):
    code, _, _ = http(f"https://{group_var('skypilot_domain')}/dashboard/", timeout=10)
    return code == 401, f"{code}" + ("  (530 = tunnel token ใช้ไม่ได้)" if code == 530 else "")


def t_sky_check(t):
    rc, out = ssh(WEB, f"{BACKEND_EXEC} sky check aws kubernetes", timeout=240)
    out = ANSI.sub("", out)
    tail = out.split("Enabled infra")[-1] if "Enabled infra" in out else ""
    aws, k8s = "AWS" in tail, "Kubernetes" in tail
    with S.lock:
        S.sky_infra = (aws, k8s)
    return aws and k8s, f"AWS {'✓' if aws else '✗'}  Kubernetes {'✓' if k8s else '✗'}"


# ---------- tests: launch

def find_user_id():
    if S.user_id:
        return S.user_id
    # SQL ส่งทาง stdin — quote ใน ssh + sh -c ซ้อนกันหลายชั้นแล้วหาย
    rc, out = ssh(WEB, f"cd {WEB_DIR} && docker compose -f docker-compose.prod.yml exec -T db "
                       f"sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -tA'", timeout=30,
                  stdin=f"select id from users where email='{USER_EMAIL}';")
    m = re.search(r"[0-9a-f]{8}-[0-9a-f-]{27}", out)
    if m:
        S.user_id = m.group(0)
        log(f"USER_ID = {S.user_id} (Sophia จาก DB)")
    return S.user_id


def post_session(lab, from_host=None):
    """POST /api/sessions จากเครื่องนี้ หรือผ่าน ssh จากเครื่องอื่น (backend เห็น IP ของเครื่องที่ยิง)"""
    body = json.dumps({"lab_id": lab, "user_id": find_user_id()})
    curl = f"curl -s --max-time 1500 -w '\\n%{{http_code}}' -X POST {API}/sessions -H 'Content-Type: application/json' -d '{body}'"
    for attempt in (1, 2):
        rc, out = ssh(from_host, curl, timeout=1600) if from_host else run(["bash", "-c", curl], timeout=1600)
        text, _, code = out.rpartition("\n")
        try:
            data = json.loads(text)
        except ValueError:
            data = {"message": text[:200]}
        # session ปลอม RUNNING (seed) ทำให้ 409 — ลบแล้วลองใหม่ 1 ครั้ง
        m = re.search(r"already has a running session.*?Session ID: ([0-9a-f-]{36})", json.dumps(data))
        if code == "409" and m and attempt == 1:
            log(f"409 session ค้าง {m.group(1)[:8]} → ลบแล้วลองใหม่", "yellow")
            delete_session(m.group(1))
            continue
        if data.get("success") and data.get("data", {}).get("session_id"):
            S.created.add(data["data"]["session_id"])
        return code, data
    return code, data


def delete_session(sid):
    code, body, sec = http(f"{API}/sessions/{sid}", method="DELETE", timeout=600)
    S.created.discard(sid)
    log(f"DELETE {sid[:8]} → {code} ({sec:.0f}s)", "" if code == 200 else "red")
    return code == 200


def ec2_of(cluster):
    rc, out = run(AWS + ["ec2", "describe-instances", "--filters", f"Name=tag:skypilot-cluster-name,Values={cluster}*",
                         "--query", "Reservations[].Instances[].[InstanceId,State.Name,PublicIpAddress]",
                         "--output", "json"], timeout=30)
    return json.loads(out) if rc == 0 else []


LAST = {}   # ผลของ launch ที่เทสถัดไปใช้ (isolation)


def launch_test(lab, from_host, expect, keep=False):
    def fn(t):
        if expect == "aws" and SKIP_AWS:
            return None, "ข้าม (SKIP_AWS=1)"
        where = from_host.split("@")[-1] if from_host else "เครื่องนี้"
        log(f"POST /api/sessions lab={lab[:8]} จาก {where}")
        t.detail = f"launch จาก {where} ..."
        code, data = post_session(lab, from_host)
        d = data.get("data") or {}
        if code != "201" or not data.get("success"):
            return False, f"HTTP {code} {str(data.get('message') or data.get('detail'))[:150]}"
        target, mode = d.get("run_target"), d.get("launch_mode")
        detail = f"{target} {mode} {t.elapsed}" + (f" node {d['node_name']}" if d.get("node_name") else "")
        ok = target == expect
        if expect == "aws":
            inst = ec2_of(d.get("cluster_name", "?"))
            public = [i[2] for i in inst if i[2]]
            ports = {p: run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "8", u])[1]
                     for p, u in sorted((d.get("endpoints") or {}).items())}
            detail += f"  public IP {'มี ⚠' if public else 'ไม่มี'}  " + " ".join(f"{p}:{c}" for p, c in ports.items())
            ok = ok and not public and all(c not in ("", "000") for c in ports.values())
        if keep:
            LAST.update(d)
        else:
            t.detail = detail + "  ลบ ..."
            ok = delete_session(d["session_id"]) and ok
            if expect == "aws":
                states = [i[1] for i in ec2_of(d.get("cluster_name", "?"))]
                detail += f"  EC2 {','.join(states) or 'หาไม่เจอ'}"
                ok = ok and all(s in ("shutting-down", "terminated") for s in states)
        return ok, detail
    return fn


def t_isolation(t):
    d = dict(LAST)
    if not d:
        return False, "ไม่มี lab จากข้อก่อน"
    worker_ip = WORKER.split("@")[-1]
    eps = d.get("endpoints") or {}
    url = eps.get("8443") or eps.get("8080") or next(iter(eps.values()), "")
    if "localhost" in url:                       # warm pod: เปิดผ่าน localhost ของเครื่องแลปเท่านั้น
        from_worker, from_other = url, url.replace("localhost", worker_ip)
    else:
        from_worker = from_other = url
    curl = lambda u: f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 6 {u}"
    w = ssh(WORKER, curl(from_worker), timeout=20)[1].strip()
    m = ssh(MASTER, curl(from_other), timeout=20)[1].strip()
    web = ssh(WEB, curl(from_other), timeout=20)[1].strip()
    ok = w not in ("", "000") and m == "000" and web == "000"
    result = f"worker-pete {w}  master {m}  webservice {web}  (คาด เปิดได้ / 000 / 000)"
    ok = delete_session(d["session_id"]) and ok
    LAST.clear()
    return ok, result


def t_leftovers(t):
    """pod ที่เพิ่งลบใช้เวลา Terminating สักพัก — ลองซ้ำได้ 60s ก่อนนับว่าค้าง"""
    deadline = time.time() + 60
    while True:
        rc, out = run(["kubectl", "get", "pods", "-A", "-l", "vlab/lab=true", "--no-headers"], timeout=10)
        pods = [l.split()[1] for l in out.splitlines()
                if l.strip() and not l.startswith("No resources") and not l.split()[1].startswith("warm-")]
        with S.lock:
            sessions = list(S.sessions)
        rc, out = run(AWS + ["ec2", "describe-instances", "--filters", "Name=tag-key,Values=skypilot-cluster-name",
                             "Name=instance-state-name,Values=pending,running",
                             "--query", "Reservations[].Instances[].InstanceId", "--output", "text"], timeout=30)
        ec2 = out.split() if rc == 0 else ["?"]
        ok = not pods and not sessions and not ec2
        if ok or time.time() > deadline:
            break
        t.detail = f"รอ pod {len(pods)} session {len(sessions)} EC2 {len(ec2)} ..."
        time.sleep(5)
    detail = f"pod {len(pods)}  session {len(sessions)}  EC2 {len(ec2)}"
    if not ok:
        detail += "  " + " ".join(pods + ec2)[:80] + "  → กด d ลบ"
    return ok, detail


# ---------- ชุดเทส

def suite(name):
    a = [Test("A1", "ansible", "syntax", t_syntax),
         Test("A2", "ansible", "เข้าเครื่องได้ + sudo", t_reach)] + \
        [Test(f"A{3 + n}", "ansible", f"playbook {g}", t_playbook(g)) for n, g in enumerate(("master", "workers", "webservice"))]
    i = [Test("I1", "infra", "node Ready", t_nodes),
         Test("I2", "infra", "NodePort 30880 ×5", t_nodeport),
         Test("I3", "infra", "auth 401/401/200", t_auth),
         Test("I4", "infra", "server memory / restart", t_server),
         Test("I5", "infra", "sky api info ใน backend", t_api_info),
         Test("I6", "infra", "AWS identity ใน backend", t_identity),
         Test("I7", "infra", "นาฬิกาทุกเครื่อง", t_clocks),
         Test("I8", "infra", "backend→master 30s", t_probe),
         Test("I9", "infra", "dashboard ผ่าน Cloudflare", t_cloudflare),
         Test("I10", "infra", "sky check aws kubernetes", t_sky_check)]
    l = [Test("L1", "launch", "K8s จากเครื่องแลป", launch_test(LAB_K8S, WORKER, "kubernetes", keep=True)),
         Test("L2", "launch", "isolation", t_isolation),
         Test("L3", "launch", "AUTO จากเครื่องแลป", launch_test(LAB_AUTO, WORKER, "kubernetes")),
         Test("L4", "launch", "AWS", launch_test(LAB_AWS, None, "aws")),
         Test("L5", "launch", "AUTO จากข้างนอก", launch_test(LAB_AUTO, None, "aws")),
         Test("L6", "launch", "ไม่มีของค้าง", t_leftovers)]
    return {"ansible": a, "infra": i, "launch": l, "all": a + i + l}[name]


def run_suite(name):
    tests = suite(name)
    with S.lock:
        S.tests, S.running = tests, name
    log(f"=== เริ่มชุด {name} ({len(tests)} ข้อ)  log: {LOG_DIR}", "bold")
    for t in tests:
        t.status, t.t0 = "run", time.time()
        try:
            ok, detail = t.fn(t)
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"[:200]
        t.t1 = time.time()
        t.status = "skip" if ok is None else "ok" if ok else "fail"
        t.detail = detail
        log(f"{ICON[t.status]} {t.tid} {t.name}  {detail}", {"ok": "green", "fail": "red"}.get(t.status, "yellow"))
    with S.lock:
        S.running = None
    log(f"=== จบชุด {name}: " + summary_line(tests), "bold")


def summary_line(tests):
    c = collections.Counter(t.status for t in tests)
    return f"✅ {c['ok']}  ❌ {c['fail']}  ⏭ {c['skip']}  | server memory สูงสุด {S.peak_mem}Mi  restart " \
           f"{(S.sky_restarts or 0) - (S.sky_restarts_start or 0):+d}"


def cleanup(confirm=True):
    """ลบ session ที่เปิดอยู่ของ user + EC2 ที่ค้าง (sky down ผ่าน backend ที่มี token)"""
    with S.lock:
        sessions, ec2 = list(S.sessions), list(S.ec2)
    clusters = sorted({re.sub(r"-sa-[0-9a-f]+$", "", c or "") for *_, c in ec2 if c})
    if not sessions and not clusters:
        log("ไม่มีของค้าง")
        return
    if confirm and not ask(f"ลบ session {len(sessions)} ตัว + EC2 cluster {len(clusters)} ตัว ?", default=True):
        return
    for s in sessions:
        delete_session(s["id"])
    for c in clusters:
        log(f"sky down {c} ...", "yellow")
        rc, out = ssh(WEB, f"{BACKEND_EXEC} sky down -y {c}", timeout=600)
        log(f"sky down {c} → {'ok' if rc == 0 else ANSI.sub('', out)[-150:]}", "" if rc == 0 else "red")
    if clusters:
        log("ถ้า EC2 ยังไม่หาย: aws ec2 terminate-instances --profile skypilot --instance-ids ...", "yellow")


# ---------- วาดจอ

ICON = {"wait": "·", "run": "⠋", "ok": "✅", "fail": "❌", "skip": "⏭"}
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def title(n, name, color):
    t = Text()
    t.append(n, style="bold " + color)
    t.append(name, style="bold white")
    return t


def panel(body, n, name, color, subtitle=None):
    return Panel(body, title=title(n, name, color), title_align="left", border_style=color, box=box.ROUNDED,
                 subtitle=subtitle, subtitle_align="right", padding=(0, 1))


def ok_text(ok, good="ok", bad="down"):
    return Text(good, style="bold green") if ok else Text(bad, style="bold red")


def render_cluster(width):
    g = Table.grid(padding=(0, 2))
    g.add_column(style="white")
    g.add_column()
    g.add_column(style="grey62")
    g.add_column()
    with S.lock:
        nodes, clocks, probe = list(S.nodes), dict(S.clocks), list(S.probe)
    for name, ready, ip in nodes:
        off = clocks.get(name)
        g.add_row(name, ok_text(ready, "Ready", "NotReady"), ip, clock_text(off))
    if not nodes:
        g.add_row("kubectl", Text("ไม่ตอบ", style="red"), "", "")
    g.add_row("webservice", Text("vm", style="cyan"), WEB.split("@")[-1], clock_text(clocks.get("webservice")))
    w = max(10, width - 34)
    lost = sum(1 for p in probe[-60:] if not p[1])
    line = Text()
    for p in probe[-w:]:
        line.append("▁" if p[1] and p[2] < 0.5 else "▄" if p[1] else "█", style="green" if p[1] and p[2] < 0.5 else "yellow" if p[1] else "red")
    g.add_row("backend→master", line, "", Text(f"หลุด {lost}/60s", style="red" if lost else "green"))
    return panel(g, "¹", "cluster", "green")


def clock_text(off):
    if off is None:
        return Text("clock ?", style="grey50")
    return Text(f"clock {off:+.0f}s", style="green" if abs(off) < 5 else "yellow" if abs(off) < 30 else "bold red")


def render_server(width):
    with S.lock:
        (code, sec), mem, limit = S.sky_health, list(S.sky_mem), S.sky_limit
        restarts, auth, cf, infra = S.sky_restarts, S.auth, S.cloudflare, S.sky_infra
    g = Table.grid(padding=(0, 2))
    g.add_column(style="white")
    g.add_column()
    g.add_row("health", Text(f"{code}  {sec:.2f}s", style="green" if code == 200 and sec < 0.5 else "red"))
    cur = mem[-1] if mem else 0
    m = Text()
    m.append_text(meter(cur / limit if limit else 0, 20))
    m.append(f"  {cur}Mi / {limit}Mi", style="white")
    g.add_row("memory", m)
    g.add_row("", Text(spark(mem, max(10, width - 16)), style="yellow"))
    g.add_row("restart", Text(str(restarts), style="green" if restarts == 0 else "bold red"))
    if auth:
        g.add_row("auth", Text("/".join(map(str, auth)), style="green" if auth == (401, 401, 200) else "red"))
    if infra:
        g.add_row("infra", Text(f"aws {'✓' if infra[0] else '✗'}  k8s {'✓' if infra[1] else '✗'}",
                                style="green" if all(infra) else "red"))
    if cf is not None:
        g.add_row("cloudflare", Text(str(cf), style="green" if cf == 401 else "red"))
    return panel(g, "²", "skypilot server", "yellow", subtitle=Text(SKY_URL, style="grey50"))


def render_tests():
    with S.lock:
        tests, running, prompt = list(S.tests), S.running, S.prompt
    if prompt:
        q, _, _, default = prompt
        body = Group(Text(""), Text.from_markup(q, justify="center"), Text(""),
                     Text.from_markup(f"[bold green]y[/] ใช่   [bold red]n[/] ไม่  "
                                      f"[grey50](Enter = {'y' if default else 'n'})[/]", justify="center"))
        return panel(body, "³", "ยืนยัน", "magenta")
    g = Table.grid(padding=(0, 1), expand=True)
    g.add_column(width=2)
    g.add_column(style="grey62", width=4)
    g.add_column(style="white", width=26, no_wrap=True)
    g.add_column(style="grey62", width=5)
    g.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    group = None
    for t in tests:
        if t.group != group:
            group = t.group
            g.add_row("", "", Text(group, style="bold cyan"), "", "")
        icon = SPIN[int(time.time() * 8) % 10] if t.status == "run" else ICON[t.status]
        style = {"ok": "green", "fail": "red", "skip": "yellow", "run": "cyan"}.get(t.status, "grey50")
        g.add_row(Text(icon, style=style), t.tid, t.name, t.elapsed, Text(t.detail, style=style))
    if not tests:
        g.add_row("", "", Text("กด a / i / l / t เพื่อเริ่มเทส", style="grey50"), "", "")
    sub = Text(summary_line(tests) if tests and not running else (f"กำลังรัน {running}" if running else ""),
               style="grey62")
    return panel(g, "³", "tests", "red", subtitle=sub)


def render_open():
    with S.lock:
        pods, warm, sessions, ec2 = list(S.lab_pods), list(S.warm), list(S.sessions), list(S.ec2)
    g = Table.grid(padding=(0, 1))
    g.add_column(no_wrap=True, overflow="ellipsis")
    g.add_row(Text("lab pods", style="bold cyan"))
    for name, node, phase in pods:
        g.add_row(Text(f"  {name[:34]}  {node}  {phase}", style="white"))
    if not pods:
        g.add_row(Text("  -", style="grey50"))
    if warm:
        g.add_row(Text("prewarm / warm", style="bold cyan"))
        for w in warm:
            g.add_row(Text(f"  {w}", style="white"))
    g.add_row(Text("sessions", style="bold cyan"))
    for s in sessions:
        where = "EC2" if s.get("is_cloud") else ("warm" if s.get("k8s_pod_name") else "k8s")
        g.add_row(Text(f"  {s['id'][:8]}  {s['status']}  {where}  {s.get('sky_cluster_name') or ''}", style="white"))
    if not sessions:
        g.add_row(Text("  -", style="grey50"))
    g.add_row(Text("EC2 running", style="bold cyan"))
    for iid, ip, public, cluster in ec2:
        g.add_row(Text(f"  {iid}  {ip}{'  PUBLIC ' + public if public else ''}  ⚠ เสียเงิน", style="bold yellow"))
    if not ec2:
        g.add_row(Text("  -", style="grey50"))
    return panel(g, "⁴", "ของที่เปิดอยู่", "blue")


def render_log(height):
    with S.lock:
        lines = list(S.log)[-max(1, height - 2):]
    body = Group(*[Text(l, style=s or "grey70", no_wrap=True, overflow="ellipsis") for l, s in lines])
    return panel(body, "⁵", "log", "magenta", subtitle=Text(str(LOG_DIR), style="grey50"))


def render_header():
    t = Text()
    t.append(" vlab ", style="bold black on green")
    t.append(f"  {dt.datetime.now():%H:%M:%S}  ", style="bold white")
    t.append(f"backend {BACKEND_URL}  ", style="grey62")
    t.append(f"user {S.user_id[:8] or '?'}  ", style="grey62")
    t.append(f"log {LOG_DIR.name}", style="grey50")
    return t


def render_footer():
    t = Text(" ")
    busy = S.running is not None
    for key, label in (("a", "ansible"), ("i", "infra"), ("l", "launch"), ("t", "ทั้งหมด"), ("d", "ลบของค้าง"), ("q", "ออก")):
        t.append(key, style="bold red" if not busy or key == "q" else "grey35")
        t.append(f" {label}   ", style="white" if not busy or key == "q" else "grey35")
    if SKIP_AWS:
        t.append("SKIP_AWS", style="yellow")
    return t


def render(console_size):
    width, height = console_size
    layout = Layout()
    layout.split_column(Layout(name="head", size=1), Layout(name="top", size=10),
                        Layout(name="mid", ratio=1), Layout(name="log", size=9), Layout(name="foot", size=1))
    layout["top"].split_row(Layout(name="cluster"), Layout(name="server"))
    layout["mid"].split_row(Layout(name="tests", ratio=3), Layout(name="open", ratio=2))
    layout["head"].update(render_header())
    layout["cluster"].update(render_cluster(width // 2))
    layout["server"].update(render_server(width // 2))
    layout["tests"].update(render_tests())
    layout["open"].update(render_open())
    layout["log"].update(render_log(9))
    layout["foot"].update(render_footer())
    return layout


# ---------- main

def start(name):
    if S.running:
        return
    threading.Thread(target=run_suite, args=(name,), daemon=True).start()


def tui():
    start_monitor()
    threading.Thread(target=find_user_id, daemon=True).start()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    quitting = False
    try:
        tty.setcbreak(fd)
        with Live(render(console.size), console=console, screen=True, auto_refresh=False) as live:
            while True:
                if select.select([sys.stdin], [], [], 0.25)[0]:
                    ch = sys.stdin.read(1).lower()
                    with S.lock:
                        prompt = S.prompt
                    if prompt:
                        _, ev, box_, default = prompt
                        if ch in ("y", "n", "\n"):
                            box_[0] = default if ch == "\n" else ch == "y"
                            ev.set()
                    elif quitting:
                        pass
                    elif ch == "q":
                        quitting = True
                        def bye():
                            with S.lock:
                                left = [s for s in S.sessions if s["id"] in S.created]
                            if left and ask(f"ยังมี session ที่ script สร้างเปิดอยู่ {len(left)} ตัว (EC2 เสียเงิน) ลบก่อนออก?",
                                            default=True):
                                for s in left:
                                    delete_session(s["id"])
                            S.stop.set()
                        threading.Thread(target=bye, daemon=True).start()
                    elif ch in "ailt" and not S.running:
                        start({"a": "ansible", "i": "infra", "l": "launch", "t": "all"}[ch])
                    elif ch == "d" and not S.running:
                        threading.Thread(target=cleanup, daemon=True).start()
                if S.stop.is_set():
                    break
                live.update(render(console.size), refresh=True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    console.print(f"log: {LOG_DIR}")


def plain(name):
    global PLAIN
    PLAIN = True
    start_monitor()
    find_user_id()
    time.sleep(3)   # ให้ monitor เก็บข้อมูลรอบแรก (node / memory)
    try:
        run_suite(name)
    except KeyboardInterrupt:
        log("ยกเลิก (Ctrl+C)", "yellow")
    finally:
        left = [sid for sid in list(S.created)]
        for sid in left:
            delete_session(sid)
    table = Table(box=box.ROUNDED, title=f"สรุป {name}", title_style="bold")
    for col in ("", "ข้อ", "เทส", "เวลา", "ผล"):
        table.add_column(col)
    for t in S.tests:
        table.add_row(ICON[t.status], t.tid, t.name, t.elapsed, t.detail[:90])
    console.print(table)
    console.print(summary_line(S.tests))
    console.print(f"log: {LOG_DIR}")
    S.stop.set()
    return 0 if all(t.status in ("ok", "skip") for t in S.tests) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="monitor + เทส Ansible / launch (docs/archive/TEST_ALL.md)")
    ap.add_argument("--plain", choices=["ansible", "infra", "launch", "all"], help="ไม่มีจอ: รันชุดนี้แล้วพิมพ์สรุป")
    args = ap.parse_args()
    if args.plain or not sys.stdin.isatty():
        sys.exit(plain(args.plain or "infra"))
    tui()
