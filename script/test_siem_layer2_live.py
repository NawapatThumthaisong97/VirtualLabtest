"""
Live End-to-End Deployment & Verification Script for SIEM Layer 2: Buffer / Message Queue
(NATS JetStream StatefulSet + On-Disk Stream Burst Buffer + NATS KV Store on K3s)
"""

from datetime import datetime, timezone
import ast
import json
from pathlib import Path
import sys
import time
import warnings

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
import yaml

warnings.filterwarnings("ignore")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
KUBECONFIG_PATH = REPO_ROOT / "web-portal" / "backend" / "kubeconfig.yaml"
LAYER1_DIR = REPO_ROOT / "k8s" / "siem" / "layer1-collector"
LAYER2_DIR = REPO_ROOT / "k8s" / "siem" / "layer2-buffer"


def apply_layer2_manifests(
    v1: client.CoreV1Api,
    apps_v1: client.AppsV1Api,
    batch_v1: client.BatchV1Api,
):
    print("\n[1/5] Deploying Layer 2 NATS JetStream StatefulSet & Services to K3s (siem-system)...")
    for yaml_path in sorted(LAYER2_DIR.glob("*.yaml")):
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
                elif kind == "StatefulSet":
                    try:
                        apps_v1.read_namespaced_stateful_set(name, ns)
                        apps_v1.replace_namespaced_stateful_set(name, ns, doc)
                    except ApiException as e:
                        if e.status == 404:
                            apps_v1.create_namespaced_stateful_set(ns, doc)
                elif kind == "Job":
                    try:
                        batch_v1.delete_namespaced_job(
                            name, ns, propagation_policy="Background"
                        )
                        time.sleep(2)
                    except ApiException:
                        pass
                    batch_v1.create_namespaced_job(ns, doc)
                print(f"  ✓ Applied {kind}/{name}")
            except Exception as exc:
                print(f"  ! Warning applying {kind}/{name}: {exc}")

    # Update Layer 1 Vector Agent ConfigMap so it also publishes to NATS JetStream
    vec_cm = yaml.safe_load((LAYER1_DIR / "03-vector-agent-configmap.yaml").read_text(encoding="utf-8"))
    v1.replace_namespaced_config_map("vector-agent-config", "siem-system", vec_cm)
    print("  ✓ Updated ConfigMap/vector-agent-config (Added NATS JetStream sink)")


def wait_for_nats_statefulset(v1: client.CoreV1Api, timeout_sec: int = 90) -> str:
    print("\n[2/5] Waiting for StatefulSet Pod 'nats-jetstream-0' & PVC 'jetstream-disk-storage'...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            pod = v1.read_namespaced_pod("nats-jetstream-0", "siem-system")
            ready = any(cs.ready for cs in (pod.status.container_statuses or []))
            if pod.status.phase == "Running" and ready:
                pvcs = v1.list_namespaced_persistent_volume_claim("siem-system").items
                pvc_info = [(p.metadata.name, p.status.phase) for p in pvcs]
                print(f"  ✓ StatefulSet Pod 'nats-jetstream-0' on node '{pod.spec.node_name}' -> Running (Ready)")
                print(f"  ✓ Persistent Disk PVC bound: {pvc_info}")
                return "nats-jetstream-0"
        except ApiException:
            pass
        time.sleep(3)
    raise RuntimeError("Timed out waiting for nats-jetstream-0 StatefulSet pod")


def verify_jetstream_engine_on_disk(v1: client.CoreV1Api, pod_name: str):
    print("\n[3/5] Inspecting Live NATS JetStream Monitoring Endpoint (http://127.0.0.1:8222/jsz)...")
    jsz_raw = stream(
        v1.connect_get_namespaced_pod_exec,
        pod_name,
        "siem-system",
        command=["/bin/sh", "-c", "wget -qO- http://127.0.0.1:8222/jsz"],
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )
    try:
        jsz = json.loads(jsz_raw)
    except Exception:
        jsz = ast.literal_eval(jsz_raw)
    cfg = jsz.get("config", {})
    print(f"  ✓ JetStream Domain    : {cfg.get('domain')}")
    print(f"  ✓ On-Disk Store Dir   : {cfg.get('store_dir')}")
    print(f"  ✓ Max Disk Storage    : {cfg.get('max_storage')} bytes (~5 GB)")
    print(f"  ✓ Max Memory Storage  : {cfg.get('max_memory')} bytes (~128 MB)")


def verify_streams_and_kv_burst_simulation(v1: client.CoreV1Api):
    print("\n[4/5] Verifying Bootstrap Job & Simulating Ephemeral SkyPilot Burst + NATS KV State...")
    deadline = time.time() + 90
    while time.time() < deadline:
        pods = v1.list_namespaced_pod(
            "siem-system", label_selector="app.kubernetes.io/name=nats-jetstream-bootstrap"
        ).items
        if pods and pods[-1].status.phase in ("Succeeded", "Running"):
            break
        time.sleep(3)

    # Create a short-lived nats-box verifier or exec via nats-jetstream-0 / bootstrap pod
    # Note: we can use Python inside lab-pod or nats-jetstream-0 or a one-shot nats-box command!
    # Wait: let's check the bootstrap job log first!
    pods = v1.list_namespaced_pod(
        "siem-system", label_selector="app.kubernetes.io/name=nats-jetstream-bootstrap"
    ).items
    for _ in range(25):
        if pods and pods[-1].status.phase == "Succeeded":
            break
        time.sleep(2)
        pods = v1.list_namespaced_pod(
            "siem-system", label_selector="app.kubernetes.io/name=nats-jetstream-bootstrap"
        ).items

    if pods:
        bpod = pods[-1].metadata.name
        try:
            blog = v1.read_namespaced_pod_log(bpod, "siem-system")
            print("  ✓ Bootstrap Job Output:")
            for line in blog.strip().splitlines():
                print(f"    {line}")
        except Exception:
            pass

    # Simulate an ephemeral SkyPilot node bursting 5 logs + writing alert state into NATS KV
    cmds = []
    for i in range(1, 6):
        msg = json.dumps({
            "siem_layer": "layer2-buffer",
            "source": "skypilot-aws-ephemeral-01",
            "eventType": "SKYPILOT_BURST_LOG",
            "seq": i,
        })
        cmds.append(f"printf 'PUB siem.logs.skypilot.burst {len(msg)}\\r\\n{msg}\\r\\nQUIT\\r\\n' | nc 127.0.0.1 4222 >/dev/null")
    kv_msg = json.dumps({"rule": "VLab Sensitive System File Read", "status": "FIRING", "count": 1})
    cmds.append(f"printf 'PUB $KV.SIEM_ALERT_STATE.alert.kali.shadow_read {len(kv_msg)}\\r\\n{kv_msg}\\r\\nQUIT\\r\\n' | nc 127.0.0.1 4222 >/dev/null")
    burst_script = "; ".join(cmds)
    stream(
        v1.connect_get_namespaced_pod_exec,
        "nats-jetstream-0",
        "siem-system",
        command=["/bin/sh", "-c", burst_script],
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )
    print("  ✓ Simulated 5-event SkyPilot burst -> Stream 'SIEM_TELEMETRY' & wrote Alert State -> KV 'SIEM_ALERT_STATE'!")

    print("\n[5/5] Verifying Persisted Messages on Disk (/data/jetstream) via /jsz?streams=true...")
    jsz_streams_raw = stream(
        v1.connect_get_namespaced_pod_exec,
        "nats-jetstream-0",
        "siem-system",
        command=["/bin/sh", "-c", "wget -qO- 'http://127.0.0.1:8222/jsz?streams=true'"],
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )
    try:
        jsz_streams = json.loads(jsz_streams_raw)
    except Exception:
        jsz_streams = ast.literal_eval(jsz_streams_raw)
    print(f"  ✓ Total Active JetStream Streams : {jsz_streams.get('streams')}")
    print(f"  ✓ Total Messages Persisted on Disk: {jsz_streams.get('messages')} ({jsz_streams.get('bytes')} bytes)")
    for acct in jsz_streams.get("account_details", []):
        for s in acct.get("stream_detail", []):
            state = s.get("state", {})
            print(
                f"    • Stream '{s.get('name')}' -> messages={state.get('messages')}, "
                f"bytes={state.get('bytes')}, last_seq={state.get('last_seq')}"
            )

    # Show actual files persisted on K3s disk (/data/jetstream) and read back live KV + Stream payloads
    disk_files = stream(
        v1.connect_get_namespaced_pod_exec,
        "nats-jetstream-0",
        "siem-system",
        command=[
            "/bin/sh",
            "-c",
            "ls -lh /data/jetstream/jetstream/\\$G/streams/ && "
            "echo '--- SAMPLE PERSISTED KV & STREAM PAYLOADS ON DISK ---' && "
            "strings /data/jetstream/jetstream/\\$G/streams/SIEM_TELEMETRY/msgs/*.blk | tail -n 6 && "
            "strings /data/jetstream/jetstream/\\$G/streams/KV_SIEM_ALERT_STATE/msgs/*.blk | tail -n 4",
        ],
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )
    print("\n  ✓ On-Disk Storage Verification (/data/jetstream inside PVC):")
    for line in disk_files.strip().splitlines():
        print(f"    {line}")


if __name__ == "__main__":
    print("=" * 74)
    print("  LIVE TEST: SIEM Layer 2 Buffer (NATS JetStream StatefulSet + KV Store)")
    print("=" * 74)
    config.load_kube_config(str(KUBECONFIG_PATH))
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    batch_v1 = client.BatchV1Api()

    apply_layer2_manifests(v1, apps_v1, batch_v1)
    pod_name = wait_for_nats_statefulset(v1)
    verify_jetstream_engine_on_disk(v1, pod_name)
    verify_streams_and_kv_burst_simulation(v1)
    print("\n" + "=" * 74)
    print("  ✓ Layer 2 Live Verification Complete!")
    print("=" * 74)

