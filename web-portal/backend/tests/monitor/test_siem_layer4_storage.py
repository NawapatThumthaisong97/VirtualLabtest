"""
Automated verification tests for SIEM Layer 4: Storage & Retention (Dual-Tier)
- Tier 1 (Hot Storage): VictoriaLogs on K3s (7-14 days retention, Schema-less, low RAM, fast LogsQL search)
- Tier 2 (Cold Storage): AWS S3 .parquet Archival (90 days - 1 year retention, compressed .parquet format)
- Dual-Tier fan-out from Layer 3 Vector Aggregator
"""

import json
from pathlib import Path
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
