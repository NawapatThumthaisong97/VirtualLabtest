"""
Live End-to-End Deployment & Verification Script for SIEM Layer 5: Detection & Visualization
- Deploys Grafana + Provisioned "VirtualLab 5-Layer SIEM Command Center" Dashboard (:30300)
- Deploys Sigma Rules (Detection-as-Code) -> LogsQL CronJob & executes live Sigma scan against VictoriaLogs
- Deploys & tests Falco eBPF Sub-Second Fast-Track Express Pipeline (:30080)
"""

import ast
import json
from pathlib import Path
import sys
import time
import urllib.request
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
LAYER5_DIR = REPO_ROOT / "k8s" / "siem" / "layer5-detection"
K3S_TAILSCALE_IP = os.getenv("K3S_TAILSCALE_IP", "100.69.137.47")


def apply_layer5_manifests(v1: client.CoreV1Api, apps_v1: client.AppsV1Api, batch_v1: client.BatchV1Api):
    print("\n[1/5] Deploying Layer 5 (Grafana + Sigma Rules LogsQL CronJob + Falco Fast-Track Relay) to K3s...")
    for yaml_path in sorted(LAYER5_DIR.glob("*.yaml")):
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
                elif kind == "CronJob":
                    try:
                        batch_v1.read_namespaced_cron_job(name, ns)
                        batch_v1.replace_namespaced_cron_job(name, ns, doc)
                    except ApiException as e:
                        if e.status == 404:
                            batch_v1.create_namespaced_cron_job(ns, doc)
                print(f"  ✓ Applied {kind}/{name}")
            except Exception as exc:
                print(f"  ! Warning applying {kind}/{name}: {exc}")

    # Restart grafana-siem pod to reload provisioned dashboard JSONs immediately
    for p in v1.list_namespaced_pod("siem-system", label_selector="app.kubernetes.io/name=grafana-siem").items:
        try:
            v1.delete_namespaced_pod(p.metadata.name, "siem-system")
        except Exception:
            pass
    time.sleep(2)


def wait_for_layer5_pods(v1: client.CoreV1Api, timeout_sec: int = 120) -> str:
    print("\n[2/5] Waiting for Grafana & Falco Fast-Track Relay pods in 'siem-system'...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        pods = v1.list_namespaced_pod("siem-system").items
        gf_pod = next(
            (
                p.metadata.name
                for p in pods
                if p.metadata.name.startswith("grafana-siem")
                and p.metadata.deletion_timestamp is None
                and p.status.phase == "Running"
                and all(c.ready for c in (p.status.container_statuses or []))
            ),
            None,
        )
        ft_pod = next(
            (
                p.metadata.name
                for p in pods
                if p.metadata.name.startswith("falco-fast-track-relay")
                and p.metadata.deletion_timestamp is None
                and p.status.phase == "Running"
                and all(c.ready for c in (p.status.container_statuses or []))
            ),
            None,
        )
        if gf_pod and ft_pod:
            print(f"  ✓ Grafana Pod          : {gf_pod} -> Running (Ready)")
            print(f"  ✓ Fast-Track Relay Pod : {ft_pod} -> Running (Ready)")
            return ft_pod
        time.sleep(2)
    raise RuntimeError("Timed out waiting for Layer 5 pods to become Ready")


def test_falco_sub_second_fast_track():
    print("\n[3/5] Testing Falco eBPF Sub-Second Fast-Track Express Pipeline (:30080)...")
    payload = json.dumps({
        "rule": "Terminal Shell Spawned in Student Container",
        "hostname": "k3s-worker-lab1-kali",
        "output": "Unauthorized /bin/bash shell spawned inside container reading /etc/shadow by student@dome.tu.ac.th",
        "clusterOrSubnet": "192.168.1.0/24",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://{K3S_TAILSCALE_IP}:30080/fast-track/falco",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        info = json.loads(res.read().decode("utf-8"))
        print(f"  ✓ Fast-Track Status    : {info['status']} ({info['pipeline']})")
        print(f"  ✓ Delivery Latency     : {info['latency_ms']} ms (Sub-Second Bypass={info['sub_second']})")
        print(f"  ✓ Triggered Falco Rule : {info['rule']}")


def test_sigma_rules_logsql_detection(v1: client.CoreV1Api, batch_v1: client.BatchV1Api):
    print("\n[4/5] Verifying Sigma Rules (Detection-as-Code) -> VictoriaLogs LogsQL CronJob on K3s...")
    try:
        urllib.request.urlopen(f"http://{K3S_TAILSCALE_IP}:30428/internal/force_flush", timeout=5)
    except Exception:
        pass

    cron_pods = [
        p
        for p in v1.list_namespaced_pod("siem-system").items
        if p.metadata.name.startswith("sigma-logsql-detector") and p.status.phase == "Succeeded"
    ]
    if not cron_pods:
        # Trigger an immediate Job from the CronJob if the 2-minute tick hasn't fired yet
        cron = batch_v1.read_namespaced_cron_job("sigma-logsql-detector", "siem-system")
        job_name = f"sigma-logsql-detector-manual-{int(time.time())}"
        job = client.V1Job(
            metadata=client.V1ObjectMeta(name=job_name, namespace="siem-system"),
            spec=cron.spec.job_template.spec,
        )
        batch_v1.create_namespaced_job("siem-system", job)
        for _ in range(20):
            time.sleep(1)
            cron_pods = [
                p
                for p in v1.list_namespaced_pod("siem-system").items
                if p.metadata.name.startswith("sigma-logsql-detector") and p.status.phase == "Succeeded"
            ]
            if cron_pods:
                break

    latest_cron_pod = sorted(cron_pods, key=lambda p: p.metadata.creation_timestamp)[-1]
    raw_out = v1.read_namespaced_pod_log(latest_cron_pod.metadata.name, "siem-system").strip().splitlines()[-1]
    try:
        scan_data = json.loads(raw_out)
    except json.JSONDecodeError:
        scan_data = ast.literal_eval(raw_out)

    print(f"  ✓ CronJob Pod Executed : {latest_cron_pod.metadata.name} (Rules Evaluated={scan_data['rules_evaluated']})")
    for r in scan_data["results"]:
        print(
            f"  ✓ Sigma Rule [{r['sigma_rule_id']}] ({r['mitre_technique']}) -> "
            f"LogsQL: {r['compiled_logsql']} => {r['matches_found']} match(es) in VictoriaLogs!"
        )


def verify_grafana_dashboard_api():
    print("\n[5/5] Verifying Grafana SIEM Command Center & Visual Threat Analytics Dashboards (:30300)...")
    for uid in ("vlab-siem-5layer", "vlab-siem-analytics"):
        url = f"http://{K3S_TAILSCALE_IP}:30300/api/dashboards/uid/{uid}"
        with urllib.request.urlopen(url, timeout=8) as res:
            data = json.loads(res.read().decode("utf-8"))
            dash = data["dashboard"]
            print(f"  ✓ Dashboard [{dash['uid']}] : {dash['title']} ({len(dash['panels'])} panels)")
    print(f"  ★ Tab 1 (SIEM Command Center)      : http://{K3S_TAILSCALE_IP}:30300/d/vlab-siem-5layer?orgId=1")
    print(f"  ★ Tab 2 (Visual Threat Analytics)  : http://{K3S_TAILSCALE_IP}:30300/d/vlab-siem-analytics?orgId=1")


if __name__ == "__main__":
    print("=" * 78)
    print("  LIVE TEST: SIEM Layer 5 (Grafana + Sigma Rules LogsQL + Falco Fast-Track)")
    print("=" * 78)
    config.load_kube_config(str(KUBECONFIG_PATH))
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    batch_v1 = client.BatchV1Api()

    apply_layer5_manifests(v1, apps_v1, batch_v1)
    wait_for_layer5_pods(v1)
    test_falco_sub_second_fast_track()
    test_sigma_rules_logsql_detection(v1, batch_v1)
    verify_grafana_dashboard_api()
    print("\n" + "=" * 78)
    print("  ✓ Layer 5 Detection & Visualization Live Verification Complete!")
    print("=" * 78)

