"""
Automated verification tests for SIEM Layer 4: Storage & Retention (Dual-Tier)
- Tier 1 (Hot Storage): VictoriaLogs on K3s (7-14 days retention, Schema-less, low RAM, fast LogsQL search)
- Tier 2 (Cold Storage): AWS S3 .parquet Archival (90 days - 1 year retention, compressed .parquet format)
- Dual-Tier fan-out from Layer 3 Vector Aggregator
- Live CI Verification (when SIEM_CI_LIVE=1): ingests & queries real VictoriaLogs (:9428) and S3 .parquet Gateway (:9000)
"""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
K8S_LAYER3_DIR = REPO_ROOT / "k8s" / "siem" / "layer3-processing"
K8S_LAYER4_DIR = REPO_ROOT / "k8s" / "siem" / "layer4-storage"


class TestLayer4DualTierStorageManifests:
    """Verify K3s VictoriaLogs Hot Storage, AWS S3 .parquet Cold Storage, and Dual-Tier routing."""

    def test_all_layer4_k8s_manifests_are_valid_yaml(self):
        expected_files = [
            "00-victorialogs-hot-storage.yaml",
            "01-aws-s3-cold-storage.yaml",
        ]
        for fname in expected_files:
            fpath = K8S_LAYER4_DIR / fname
            assert fpath.exists(), f"Missing Layer 4 manifest: {fpath}"
            docs = list(yaml.safe_load_all(fpath.read_text(encoding="utf-8")))
            assert len(docs) >= 1
            for doc in docs:
                assert doc is not None
                assert "apiVersion" in doc
                assert "kind" in doc
                assert doc["metadata"]["namespace"] == "siem-system"
                assert doc["metadata"]["labels"]["vlab.siem/layer"] == "4-storage"

    def test_victorialogs_hot_storage_has_14d_retention_and_low_ram(self):
        vlogs_docs = list(
            yaml.safe_load_all(
                (K8S_LAYER4_DIR / "00-victorialogs-hot-storage.yaml").read_text(encoding="utf-8")
            )
        )
        sts = next(d for d in vlogs_docs if d["kind"] == "StatefulSet")
        assert sts["metadata"]["name"] == "victorialogs"
        assert sts["metadata"]["labels"]["vlab.siem/storage-tier"] == "hot"

        container = sts["spec"]["template"]["spec"]["containers"][0]
        assert "victoria-logs" in container["image"]
        args = " ".join(container["args"])
        # Must configure 7-14 days retention period on K3s
        assert "-retentionPeriod=14d" in args
        assert "-storageDataPath=/vlogs-data" in args

        # Must use very low RAM footprint
        mem_req = container["resources"]["requests"]["memory"]
        mem_lim = container["resources"]["limits"]["memory"]
        assert mem_req in ("32Mi", "64Mi")
        assert mem_lim in ("128Mi", "192Mi", "256Mi")

        # Must persist hot data on K3s PVC
        vct = sts["spec"]["volumeClaimTemplates"][0]
        assert vct["metadata"]["name"] == "victorialogs-hot-disk"
        assert "ReadWriteOnce" in vct["spec"]["accessModes"]

    def test_aws_s3_cold_storage_compresses_parquet_with_90_to_365_days_retention(self):
        s3_docs = list(
            yaml.safe_load_all(
                (K8S_LAYER4_DIR / "01-aws-s3-cold-storage.yaml").read_text(encoding="utf-8")
            )
        )
        cm = next(d for d in s3_docs if d["kind"] == "ConfigMap")
        assert cm["metadata"]["labels"]["vlab.siem/storage-tier"] == "cold"

        lifecycle = json.loads(cm["data"]["s3-lifecycle-policy.json"])
        assert lifecycle["Format"] == "apache-parquet"
        assert lifecycle["Compression"] == "zstd"

        rule = lifecycle["Rules"][0]
        assert rule["Status"] == "Enabled"
        transition_days = [t["Days"] for t in rule["Transitions"]]
        assert 90 in transition_days
        assert rule["Expiration"]["Days"] == 365

        ref_cfg = yaml.safe_load(cm["data"]["vector-aws-s3-parquet-reference.yaml"])
        s3_sink = ref_cfg["sinks"]["aws_s3_cold_storage_parquet"]
        assert s3_sink["type"] == "aws_s3"
        assert s3_sink["filename_extension"] == "parquet"
        assert s3_sink["compression"] == "zstd"

    def test_vector_aggregator_fans_out_to_victorialogs_and_s3_parquet(self):
        agg_cm = yaml.safe_load(
            (K8S_LAYER3_DIR / "01-vector-aggregator-configmap.yaml").read_text(encoding="utf-8")
        )
        vec_cfg = yaml.safe_load(agg_cm["data"]["vector-aggregator.yaml"])
        sinks = vec_cfg["sinks"]

        assert "victorialogs_hot_storage" in sinks
        hot_sink = sinks["victorialogs_hot_storage"]
        assert "victorialogs.siem-system.svc.cluster.local:9428/insert/jsonline" in hot_sink["uri"]
        assert "ecs_normalize_and_enrich" in hot_sink["inputs"]

        assert "aws_s3_cold_storage_parquet" in sinks
        cold_sink = sinks["aws_s3_cold_storage_parquet"]
        assert "s3-cold-storage.siem-system.svc.cluster.local:9000" in cold_sink["uri"]
        assert "ecs_normalize_and_enrich" in cold_sink["inputs"]

    @pytest.mark.skipif(os.getenv("SIEM_CI_LIVE") != "1", reason="Runs against live VictoriaLogs & S3 Parquet containers in CI")
    def test_live_ci_victorialogs_and_s3_parquet_cold_storage(self):
        """Verifies real VictoriaLogs ingestion/LogsQL search (:9428) and real S3 .parquet PAR1 archive (:9000)."""
        ecs_events = [
            {
                "severity": "CRITICAL",
                "category": "SECURITY_VIOLATION",
                "eventType": "FALCO_EBPF_ALERT",
                "source": "k3s-worker-ci",
                "message": "Unauthorized read of /etc/shadow by container process",
                "metadata": {"ecs_version": "8.11.0", "siem_layer": "layer4-ci"},
            },
            {
                "severity": "CRITICAL",
                "category": "SECURITY_VIOLATION",
                "eventType": "SQUID_EGRESS_DROP",
                "source": "k3s-worker-ci",
                "message": "Blocked outbound C2 traffic to 198.51.100.24 (c2-botnet.darknet.io) T1071",
                "metadata": {"ecs_version": "8.11.0", "siem_layer": "layer4-ci"},
            },
            {
                "severity": "CRITICAL",
                "category": "SECURITY_VIOLATION",
                "eventType": "CRYPTOMINING_DETECTED",
                "source": "aws-skypilot-ci",
                "message": "Blocked stratum+tcp connection to malicious-mining.org (203.0.113.66)",
                "metadata": {"ecs_version": "8.11.0", "siem_layer": "layer4-ci"},
            },
            {
                "severity": "CRITICAL",
                "category": "SECURITY_VIOLATION",
                "eventType": "OPA_KYVERNO_BLOCK",
                "source": "k3s-worker-ci",
                "message": "KYVERNO_POLICY_BLOCK pod attempted privileged=true container launch",
                "metadata": {"ecs_version": "8.11.0", "siem_layer": "layer4-ci"},
            },
        ]

        # 1. Insert JSON lines into real VictoriaLogs Hot Storage (:9428)
        vlogs_insert = "http://127.0.0.1:9428/insert/jsonline?_stream_fields=source,category,severity&_msg_field=message"
        ndjson_body = ("\n".join(json.dumps(e) for e in ecs_events) + "\n").encode("utf-8")
        req = urllib.request.Request(vlogs_insert, data=ndjson_body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status in (200, 204)

        # Query back via LogsQL
        q_data = urllib.parse.urlencode({"query": 'category:"SECURITY_VIOLATION" AND "/etc/shadow"', "limit": "10"}).encode("utf-8")
        q_req = urllib.request.Request("http://127.0.0.1:9428/select/logsql/query", data=q_data, method="POST")
        with urllib.request.urlopen(q_req, timeout=5) as q_res:
            lines = [json.loads(line) for line in q_res.read().decode("utf-8").splitlines() if line.strip()]
        assert len(lines) >= 1
        assert "/etc/shadow" in lines[0].get("_msg", "")

        # 2. Archive to real S3 Cold Storage .parquet Gateway (:9000)
        s3_req = urllib.request.Request(
            "http://127.0.0.1:9000/ingest",
            data=json.dumps(ecs_events).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(s3_req, timeout=5) as s3_res:
            s3_out = json.loads(s3_res.read().decode("utf-8"))
        assert s3_out["status"] == "archived"
        assert s3_out["s3_key"].endswith(".parquet")

        # Verify PAR1 magic bytes and columnar preview via /buckets API
        with urllib.request.urlopen("http://127.0.0.1:9000/buckets", timeout=5) as b_res:
            b_info = json.loads(b_res.read().decode("utf-8"))
        assert b_info["object_count"] >= 1
        assert b_info["objects"][0]["format"] == "parquet (PAR1)"
        assert "ecs_version" in b_info["latest_parquet_columns"]
