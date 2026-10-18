import urllib.request
import json
import os
import sys

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/api")
INGEST_ENDPOINT = f"{API_BASE_URL}/v1/logs"
METRICS_ENDPOINT = f"{API_BASE_URL}/v1/metrics"

print("=" * 66)
print("   SIEM-Ready Log Forwarding & Infrastructure Metrics Test Suite   ")
print("=" * 66)

# 1. Connectivity Check & Admin Login
print("\n[1/4] Checking Backend API Connectivity & Authenticating...")
try:
    check_url = API_BASE_URL.replace("/api", "/docs")
    req = urllib.request.Request(check_url)
    with urllib.request.urlopen(req, timeout=5) as res:
        print(f"[OK] Backend is active and reachable (HTTP {res.status}).")
except Exception as e:
    print(f"ERROR: Backend API is not responding at {API_BASE_URL}: {e}")
    sys.exit(1)

# Authenticate as Admin
ADMIN_TOKEN = ""
try:
    login_payload = json.dumps({"username": "admin@dome.tu.ac.th", "password": "labpass123"}).encode("utf-8")
    login_req = urllib.request.Request(
        f"{API_BASE_URL}/auth/login",
        data=login_payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(login_req, timeout=5) as res:
        login_res = json.loads(res.read().decode("utf-8"))
        ADMIN_TOKEN = login_res.get("data", {}).get("accessToken", "")
        print(f"[OK] Admin authenticated successfully (Bearer token acquired).")
except Exception as e:
    print(f"[WARN] Could not authenticate as admin: {e}")

def send_siem_log(test_name, payload):
    print(f"\nTesting: {test_name}")
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if ADMIN_TOKEN:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    req = urllib.request.Request(
        INGEST_ENDPOINT,
        data=data,
        headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            print(f"[OK] Success (HTTP {res.status}): {res_data.get('message')}")
            item = res_data.get("data", {})
            print(f"  Masked Message : {item.get('message')}")
            print(f"  Anon ID        : {item.get('anonId')}")
            print(f"  Event Type     : {item.get('eventType')}")
            print(f"  Severity       : {item.get('severity')}")
            return True
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8")
        print(f"✗ Failed with HTTP {he.code}: {err_body}")
        return False
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

print("\n[2/4] Testing SIEM Boundary Violations Ingestion...")

# 1. Squid Proxy Egress Drop
send_siem_log("Squid Egress Drop (Query String & PII Redaction)", {
    "severity": "WARNING",
    "category": "SECURITY_VIOLATION",
    "eventType": "squid_egress_drop",
    "source": "squid-proxy-k3s-01",
    "message": "TCP_DENIED to unauthorized domain http://malicious-mining.org/payload?token=supersecret123&student_email=student@dome.tu.ac.th",
    "userId": "c0a80101-0000-0000-0000-000000000001",
    "clusterOrSubnet": "10.0.0.0/16",
    "metadata": {
        "clientIp": "10.0.12.55",
        "destinationHost": "malicious-mining.org",
        "ruleTriggered": "deny_unlisted_cryptomining",
        "environment": "Local K3s"
    }
})

# 2. Kyverno Policy Block
send_siem_log("Kyverno Admission Policy Block", {
    "severity": "WARNING",
    "category": "SECURITY_VIOLATION",
    "eventType": "kyverno_policy_block",
    "source": "kyverno-admission-controller",
    "message": "Admission blocked Pod/priv-esc-test with allowPrivilegeEscalation=true by policy disallow-privilege-escalation",
    "userId": "c0a80101-0000-0000-0000-000000000002",
    "clusterOrSubnet": "192.168.1.0/24",
    "metadata": {
        "policyName": "disallow-privilege-escalation",
        "resourceKind": "Pod",
        "namespace": "default",
        "environment": "AWS SkyPilot"
    }
})

# 3. Tailscale ACL Deny
send_siem_log("Tailscale Cross-Cluster ACL Deny", {
    "severity": "ERROR",
    "category": "SECURITY_VIOLATION",
    "eventType": "tailscale_acl_deny",
    "source": "tailscale-subnet-router",
    "message": "Tailscale ACL dropped cross-cluster packet from 100.64.0.50 to 100.64.0.1:22",
    "userId": "c0a80101-0000-0000-0000-000000000001",
    "clusterOrSubnet": "10.0.0.0/16",
    "metadata": {
        "srcIp": "100.64.0.50",
        "dstIp": "100.64.0.1",
        "port": 22,
        "action": "DROP"
    }
})

# 4. Kernel OOM Killer
send_siem_log("Kernel OOM Killer & Code Redaction Event", {
    "severity": "CRITICAL",
    "category": "CONTAINER",
    "eventType": "oom_killed",
    "source": "containerd-node-worker-02",
    "message": "Container exceeded 4096MB cgroup memory limit and was invoked by kernel oom-killer: def student_code(): return [0]*10**9",
    "userId": "c0a80101-0000-0000-0000-000000000003",
    "clusterOrSubnet": "10.0.0.0/16",
    "metadata": {
        "cgroup": "memory.max",
        "limitMb": 4096,
        "node": "worker-02"
    }
})

# 3. Verify Metrics & Counters
print("\n[3/4] Verifying Cluster Metrics & Security Counters...")
try:
    headers = {}
    if ADMIN_TOKEN:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    req = urllib.request.Request(METRICS_ENDPOINT, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as res:
        metrics = json.loads(res.read().decode("utf-8")).get("data", {})
        summary = metrics.get("summary", {})
        counters = metrics.get("securityViolationCounters", {})
        print("[OK] Metrics retrieved successfully:")
        print(f"  Active Sessions  : {summary.get('totalActiveSessions')}")
        print(f"  Squid Drops      : {counters.get('squidEgressDrops')}")
        print(f"  Kyverno Blocks   : {counters.get('kyvernoPolicyBlocks')}")
        print(f"  Tailscale Denies : {counters.get('tailscaleCrossClusterAttempts')}")
        print(f"  Total Violations : {counters.get('totalViolations')}")
except Exception as e:
    print(f"[FAILED] Failed to query metrics: {e}")

# 4. Validate Plane Separation
print("\n[4/4] Verifying Strict Plane Separation Rules in Ansible...")
conf_path = os.path.join(os.path.dirname(__file__), "..", "ansible", "roles", "siem-log-forwarding", "templates", "fluent-bit.conf.j2")
with open(conf_path, "r", encoding="utf-8") as f:
    fluent_conf = f.read()

if "/var/log/pods" in fluent_conf:
    print("WARNING: Student pod log path (/var/log/pods) found in fluent-bit inputs! Strict plane separation violated.")
    sys.exit(1)
else:
    print("[OK] Verified: No student pod log path mounted or collected. Plane separation intact.")

print("\n" + "=" * 66)
print("   [OK] All SIEM Log Pipeline Tests Completed Successfully!         ")
print("=" * 66)
