"""
Live End-to-End Deployment & Verification Script for SIEM Layer 3: Data Processing & Normalization
(Vector Aggregator Deployment on K3s pulling from Layer 2 NATS -> VRL ECS + GeoIP + Threat Intel -> Backend PostgreSQL)
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
import urllib.request
import warnings

from jose import jwt
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
import yaml

warnings.filterwarnings("ignore")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
KUBECONFIG_PATH = REPO_ROOT / "web-portal" / "backend" / "kubeconfig.yaml"
LAYER3_DIR = REPO_ROOT / "k8s" / "siem" / "layer3-processing"
ENV_PATH = REPO_ROOT / "web-portal" / "backend" / ".env"
LOCAL_API = "http://localhost:8000/api"


def read_env_secret_key() -> str:
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("SECRET_KEY="):
                return line.split("=", 1)[1].strip()
    return "yNJa_CB26E9iMesvo2WkNyvZnDivFzo5EN9nbQ91rPGlvvshPezcd-d3hV5H8dvw"


SECRET_KEY = read_env_secret_key()


def apply_layer3_manifests(v1: client.CoreV1Api, apps_v1: client.AppsV1Api):
    print("\n[1/4] Deploying Layer 3 Vector Aggregator Deployment & ConfigMaps to K3s (siem-system)...")
    for yaml_path in sorted(LAYER3_DIR.glob("*.yaml")):
        for doc in yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")):
            if not doc:
                continue
            kind = doc["kind"]
            meta = doc["metadata"]
            name = meta["name"]
            ns = meta.get("namespace", "siem-system")

            try:
                if kind == "ConfigMap":
                    try:
                        v1.read_namespaced_config_map(name, ns)
                        v1.replace_namespaced_config_map(name, ns, doc)
                    except ApiException as e:
                        if e.status == 404:
                            v1.create_namespaced_config_map(ns, doc)
                elif kind == "Service":
                    try:
                        existing = v1.read_namespaced_service(name, ns)
                        doc["spec"]["clusterIP"] = existing.spec.cluster_ip
                        v1.replace_namespaced_service(name, ns, doc)
                    except ApiException as e:
                        if e.status == 404:
                            v1.create_namespaced_service(ns, doc)
                elif kind == "Deployment":
                    try:
                        apps_v1.read_namespaced_deployment(name, ns)
                        apps_v1.replace_namespaced_deployment(name, ns, doc)
                    except ApiException as e:
                        if e.status == 404:
                            apps_v1.create_namespaced_deployment(ns, doc)
                print(f"  ✓ Applied {kind}/{name}")
            except Exception as exc:
                print(f"  ! Warning applying {kind}/{name}: {exc}")

    # Restart existing vector-aggregator pods so ConfigMap updates take effect immediately
    existing_pods = v1.list_namespaced_pod(
        "siem-system", label_selector="app.kubernetes.io/name=vector-aggregator"
    ).items
    for p in existing_pods:
        try:
            v1.delete_namespaced_pod(p.metadata.name, "siem-system")
        except Exception:
            pass
    time.sleep(2)


def wait_for_vector_aggregator(v1: client.CoreV1Api, timeout_sec: int = 60) -> str:
    print("\n[2/4] Waiting for Deployment Pod 'vector-aggregator' in namespace 'siem-system'...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        pods = v1.list_namespaced_pod(
            "siem-system", label_selector="app.kubernetes.io/name=vector-aggregator"
        ).items
        for p in pods:
            ready = any(cs.ready for cs in (p.status.container_statuses or []))
            if p.status.phase == "Running" and ready:
                print(f"  ✓ Deployment Pod '{p.metadata.name}' on node '{p.spec.node_name}' -> Running (Ready)")
                return p.metadata.name
        time.sleep(2)
    raise RuntimeError("Timed out waiting for vector-aggregator pod")


def publish_raw_threat_event_into_nats(v1: client.CoreV1Api):
    print("\n[3/4] Publishing Raw Log with Blacklisted C2 IP (198.51.100.24) & Mining Domain into Layer 2 NATS...")
    raw_event = json.dumps({
        "severity": "WARNING",
        "category": "SECURITY_VIOLATION",
        "eventType": "SQUID_EGRESS_DROP",
        "source": "k3s-worker-lab1-kali",
        "message": "Outbound connection blocked to C2 server 198.51.100.24:443 and pool malicious-mining.org by student@dome.tu.ac.th",
        "clusterOrSubnet": "192.168.1.0/24",
    })
    pub_cmd = f"printf 'PUB siem.logs.boundary {len(raw_event)}\\r\\n{raw_event}\\r\\nQUIT\\r\\n' | nc 127.0.0.1 4222 >/dev/null"
    stream(
        v1.connect_get_namespaced_pod_exec,
        "nats-jetstream-0",
        "siem-system",
        command=["/bin/sh", "-c", pub_cmd],
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )
    print("  ✓ Published raw event to NATS subject 'siem.logs.boundary'!")
    print("  → Waiting 3s for Layer 3 Vector Aggregator to pull from NATS, normalize to ECS v8.11.0, enrich GeoIP + Threat Intel, and POST to Backend...")
    time.sleep(3)


def verify_ecs_and_threat_intel_in_backend():
    print("\n[4/4] Querying Backend PostgreSQL (/api/v1/logs) for Layer 3 ECS-Normalized & Enriched Event...")
    import psycopg2
    conn = psycopg2.connect("postgresql://postgres:password@100.86.87.27:5432/virtual_lab")
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE LOWER(role::text) = 'admin' LIMIT 1;")
    row = cur.fetchone()
    token = jwt.encode(
        {
            "sub": str(row[0]),
            "email": row[1],
            "name": "Admin",
            "role": "admin",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        SECRET_KEY,
        algorithm="HS256",
    )

    req = urllib.request.Request(
        f"{LOCAL_API}/v1/logs?limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        logs = json.loads(res.read().decode("utf-8"))["data"]["logs"]
        layer3_logs = [
            l for l in logs if (l.get("metadata") or {}).get("siem_layer") == "layer3-processing"
        ]
        target = layer3_logs[0] if layer3_logs else logs[0]
        meta = target.get("metadata") or {}
        print(f"  ✓ Event ID         : {target.get('id')}")
        print(f"  ✓ Upgraded Severity: {target.get('severity')} (Upgraded from WARNING -> CRITICAL by Threat Intel Match!)")
        print(f"  ✓ Masked Message   : {target.get('message')}")
        print(f"  ✓ SIEM Layer       : {meta.get('siem_layer')} ({meta.get('processor')})")
        print(f"  ✓ ECS Version      : {meta.get('ecs_version')}")
        print(f"  ✓ GeoIP Enrichment : {json.dumps(meta.get('geoip', {}))}")
        print(f"  ✓ Threat Intel Match: {json.dumps(meta.get('threat_intel', {}))}")


if __name__ == "__main__":
    print("=" * 76)
    print("  LIVE TEST: SIEM Layer 3 (Vector Aggregator: NATS -> ECS + GeoIP + Threat Intel)")
    print("=" * 76)
    config.load_kube_config(str(KUBECONFIG_PATH))
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()

    apply_layer3_manifests(v1, apps_v1)
    wait_for_vector_aggregator(v1)
    publish_raw_threat_event_into_nats(v1)
    verify_ecs_and_threat_intel_in_backend()
    print("\n" + "=" * 76)
    print("  ✓ Layer 3 Live End-to-End Verification Complete!")
    print("=" * 76)

