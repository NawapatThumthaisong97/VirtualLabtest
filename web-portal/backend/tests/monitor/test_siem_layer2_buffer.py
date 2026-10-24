"""
Tests for 5-Layer SIEM Architecture — Layer 2: Buffer / Message Queue (NATS JetStream)

Verifies:
1. All YAML manifests in k8s/siem/layer2-buffer/ are syntactically valid and labeled vlab.siem/layer: "2-buffer"
2. NATS JetStream runs as an isolated StatefulSet on K3s with persistent disk storage (volumeClaimTemplates)
   and JetStream file store (/data/jetstream) to absorb bursts from ephemeral SkyPilot nodes without data loss
3. NATS Services are strictly internal (ClusterIP / Headless) — no public NodePort or LoadBalancer exposed
4. Bootstrap Job provisions persistent file-backed Streams (SIEM_TELEMETRY, SIEM_FAST_TRACK) and
   NATS Key-Value Store bucket (SIEM_ALERT_STATE) for alert deduplication/state tracking
5. Layer 1 Vector Agent ConfigMap is wired to publish telemetry into Layer 2 NATS JetStream (nats_jetstream_buffer)
"""

from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
K8S_LAYER1_DIR = REPO_ROOT / "k8s" / "siem" / "layer1-collector"
K8S_LAYER2_DIR = REPO_ROOT / "k8s" / "siem" / "layer2-buffer"


class TestLayer2NatsJetStreamManifests:
    """Verify K3s StatefulSet, ConfigMap, Services, and Stream/KV Bootstrap for Layer 2 Buffer"""

    def test_all_layer2_k8s_manifests_are_valid_yaml(self):
        yaml_files = sorted(K8S_LAYER2_DIR.glob("*.yaml"))
        assert len(yaml_files) >= 4, "Expected at least 4 Layer 2 K8s manifests"

        for path in yaml_files:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            assert len(docs) >= 1, f"{path.name} is empty"
            for doc in docs:
                assert isinstance(doc, dict)
                assert "apiVersion" in doc
                assert "kind" in doc
                assert doc["metadata"]["labels"]["vlab.siem/layer"] == "2-buffer"

    def test_nats_jetstream_config_enables_disk_file_store(self):
        cm_doc = yaml.safe_load(
            (K8S_LAYER2_DIR / "00-nats-configmap.yaml").read_text(encoding="utf-8")
        )
        conf_text = cm_doc["data"]["nats-server.conf"]
        assert "jetstream {" in conf_text
        assert 'store_dir: "/data/jetstream"' in conf_text
        assert "max_file_store:" in conf_text

    def test_nats_services_are_internal_only_without_public_exposure(self):
        svc_docs = list(
            yaml.safe_load_all(
                (K8S_LAYER2_DIR / "01-nats-services.yaml").read_text(encoding="utf-8")
            )
        )
        assert len(svc_docs) == 2
        for svc in svc_docs:
            assert svc["kind"] == "Service"
            svc_type = svc["spec"].get("type", "ClusterIP")
            assert svc_type == "ClusterIP", "NATS JetStream must not expose NodePort or LoadBalancer"

    def test_nats_runs_as_statefulset_with_persistent_volume_claim(self):
        sts_doc = yaml.safe_load(
            (K8S_LAYER2_DIR / "02-nats-statefulset.yaml").read_text(encoding="utf-8")
        )
        assert sts_doc["kind"] == "StatefulSet"
        assert sts_doc["metadata"]["name"] == "nats-jetstream"
        assert sts_doc["spec"]["serviceName"] == "nats-jetstream-headless"

        # Verify persistent volume claim template for disk buffering
        vcts = sts_doc["spec"]["volumeClaimTemplates"]
        assert len(vcts) >= 1
        assert vcts[0]["metadata"]["name"] == "jetstream-disk-storage"
        assert "ReadWriteOnce" in vcts[0]["spec"]["accessModes"]

        # Verify container mounts /data/jetstream
        container = sts_doc["spec"]["template"]["spec"]["containers"][0]
        mounts = {m["name"]: m["mountPath"] for m in container["volumeMounts"]}
        assert mounts.get("jetstream-disk-storage") == "/data/jetstream"

    def test_bootstrap_provisions_disk_streams_and_kv_store_for_alert_state(self):
        docs = list(
            yaml.safe_load_all(
                (K8S_LAYER2_DIR / "03-nats-streams-kv-bootstrap.yaml").read_text(encoding="utf-8")
            )
        )
        cm_doc = next(d for d in docs if d["kind"] == "ConfigMap")
        job_doc = next(d for d in docs if d["kind"] == "Job")

        script = cm_doc["data"]["bootstrap.sh"]
        # Must create on-disk streams for normal telemetry & fast-track alerts
        assert "stream add SIEM_TELEMETRY" in script
        assert "--storage=file" in script
        assert "stream add SIEM_FAST_TRACK" in script

        # Must create NATS Key-Value (KV) bucket for alert state / deduplication
        assert "kv add SIEM_ALERT_STATE" in script

        assert job_doc["metadata"]["name"] == "nats-jetstream-bootstrap"

    def test_layer1_vector_agent_publishes_to_layer2_nats_jetstream(self):
        cm_doc = yaml.safe_load(
            (K8S_LAYER1_DIR / "03-vector-agent-configmap.yaml").read_text(encoding="utf-8")
        )
        vector_cfg = yaml.safe_load(cm_doc["data"]["vector.yaml"])
        sinks = vector_cfg["sinks"]
        assert "nats_jetstream_buffer" in sinks
        nats_sink = sinks["nats_jetstream_buffer"]
        assert nats_sink["type"] == "nats"
        assert "nats-jetstream.siem-system.svc.cluster.local:4222" in nats_sink["url"]
        assert nats_sink["subject"] == "siem.logs.telemetry"

