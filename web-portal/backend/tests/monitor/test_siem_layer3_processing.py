"""
Tests for 5-Layer SIEM Architecture — Layer 3: Data Processing & Normalization (Vector Aggregator)

Verifies:
1. All YAML manifests in k8s/siem/layer3-processing/ are syntactically valid and labeled vlab.siem/layer: "3-processing"
2. Vector Aggregator runs as a Kubernetes Deployment with nodeAffinity preferring Worker nodes separate from Master (control-plane)
3. Vector Aggregator pulls buffered telemetry from Layer 2 NATS JetStream (nats://nats-jetstream.siem-system.svc.cluster.local:4222)
4. VRL pipeline normalizes logs into ECS (Elastic Common Schema v8.11.0), enriches GeoIP (source.geo, destination.geo),
   and matches Threat Intelligence IOCs (C2 IPs, cryptomining domains, sensitive credential file access)
"""

from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
K8S_LAYER3_DIR = REPO_ROOT / "k8s" / "siem" / "layer3-processing"


class TestLayer3VectorAggregatorManifests:
    """Verify K3s Deployment, ConfigMaps, Master-Node Separation, and VRL ECS/GeoIP/ThreatIntel pipeline"""

    def test_all_layer3_k8s_manifests_are_valid_yaml(self):
        yaml_files = sorted(K8S_LAYER3_DIR.glob("*.yaml"))
        assert len(yaml_files) >= 3, "Expected at least 3 Layer 3 K8s manifests"

        for path in yaml_files:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            assert len(docs) >= 1, f"{path.name} is empty"
            for doc in docs:
                assert isinstance(doc, dict)
                assert "apiVersion" in doc
                assert "kind" in doc
                assert doc["metadata"]["labels"]["vlab.siem/layer"] == "3-processing"

    def test_threat_intel_and_geoip_lookup_tables_exist(self):
        cm_doc = yaml.safe_load(
            (K8S_LAYER3_DIR / "00-threat-intel-geoip-configmap.yaml").read_text(encoding="utf-8")
        )
        iocs_csv = cm_doc["data"]["threat_intel_iocs.csv"]
        assert "198.51.100.24" in iocs_csv
        assert "malicious-mining.org" in iocs_csv
        assert "T1496" in iocs_csv

        geoip_json = cm_doc["data"]["geoip_subnets.json"]
        assert "country_iso_code" in geoip_json
        assert "TU-Rangsit-Lab-Room-1" in geoip_json

    def test_vector_aggregator_pulls_from_nats_and_normalizes_to_ecs_with_geoip_and_threat_intel(self):
        cm_doc = yaml.safe_load(
            (K8S_LAYER3_DIR / "01-vector-aggregator-configmap.yaml").read_text(encoding="utf-8")
        )
        vec_cfg = yaml.safe_load(cm_doc["data"]["vector-aggregator.yaml"])

        # 1. Source pulls from Layer 2 NATS
        nats_src = vec_cfg["sources"]["nats_jetstream_telemetry"]
        assert nats_src["type"] == "nats"
        assert "nats-jetstream.siem-system.svc.cluster.local:4222" in nats_src["url"]
        assert nats_src["subject"] == "siem.logs.>"

        # 2. VRL Transform performs ECS normalization, GeoIP, and Threat Intelligence matching
        vrl_src = vec_cfg["transforms"]["ecs_normalize_and_enrich"]["source"]
        assert '"ecs": { "version": "8.11.0" }' in vrl_src
        assert '"country_iso_code"' in vrl_src
        assert '"threat":' in vrl_src
        assert '"ioc_matched"' in vrl_src
        assert '"mitre_technique"' in vrl_src

        # 3. Filter transform filters out routine INFO system logs to protect DB volume
        filter_cfg = vec_cfg["transforms"]["filter_control_plane_events"]
        assert filter_cfg["type"] == "filter"
        assert "ecs_normalize_and_enrich" in filter_cfg["inputs"]
        assert '.eventType != "SYSTEM_LOG"' in filter_cfg["condition"]
        assert 'includes(["WARNING", "ERROR", "CRITICAL"], .severity)' in filter_cfg["condition"]
        assert "filter_control_plane_events" in vec_cfg["sinks"]["central_siem_control_plane"]["inputs"]

    def test_vector_aggregator_deployment_separates_from_master_node(self):
        docs = list(
            yaml.safe_load_all(
                (K8S_LAYER3_DIR / "02-vector-aggregator-deployment.yaml").read_text(encoding="utf-8")
            )
        )
        dep_doc = next(d for d in docs if d["kind"] == "Deployment")
        assert dep_doc["metadata"]["name"] == "vector-aggregator"

        affinity = dep_doc["spec"]["template"]["spec"]["affinity"]["nodeAffinity"]
        pref = affinity["preferredDuringSchedulingIgnoredDuringExecution"][0]["preference"]
        keys = {expr["key"] for expr in pref["matchExpressions"]}
        assert "node-role.kubernetes.io/control-plane" in keys

    def test_vector_aggregator_config_passes_strict_binary_validation(self):
        """Strict validation of vector-aggregator.yaml using official Vector binary if Docker is available"""
        import shutil
        import subprocess
        import pytest

        if not shutil.which("docker"):
            pytest.skip("Docker is not available for strict Vector binary validation")

        cm_doc = yaml.safe_load(
            (K8S_LAYER3_DIR / "01-vector-aggregator-configmap.yaml").read_text(encoding="utf-8")
        )
        vector_yaml = cm_doc["data"]["vector-aggregator.yaml"]

        tmp_cfg = REPO_ROOT / "test_tmp_vector_aggregator.yaml"
        try:
            tmp_cfg.write_text(vector_yaml, encoding="utf-8")
            res = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "-v", f"{tmp_cfg.resolve()}:/etc/vector/vector.yaml:ro",
                    "-e", "SIEM_COLLECTOR_TOKEN=dummy-token",
                    "timberio/vector:0.42.0-debian",
                    "validate", "--deny-warnings", "--no-environment"
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert res.returncode == 0, f"Vector aggregator validate failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
        finally:
            if tmp_cfg.exists():
                tmp_cfg.unlink()

