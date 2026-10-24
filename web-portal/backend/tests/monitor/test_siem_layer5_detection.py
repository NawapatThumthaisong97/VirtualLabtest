"""
Automated verification tests for SIEM Layer 5: Detection & Visualization
- Grafana Deployment & Provisioned SIEM Command Center Dashboard (replacing/unifying all SIEM panels)
- Sigma Rules (Detection-as-Code) compiled to VictoriaLogs LogsQL running via K8s CronJob (every 1-5 minutes)
- Dedicated Fast-Track Express Pipeline for sub-second Falco eBPF critical alerts
"""

import json
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
K8S_LAYER5_DIR = REPO_ROOT / "k8s" / "siem" / "layer5-detection"


class TestLayer5DetectionAndVisualizationManifests:
    """Verify K3s Grafana SIEM Dashboard, Sigma Rules LogsQL CronJob, and Falco Fast-Track Relay."""

    def test_all_layer5_k8s_manifests_are_valid_yaml(self):
        expected_files = [
            "00-grafana-deployment.yaml",
            "01-grafana-dashboards-configmap.yaml",
            "02-sigma-rules-cronjob.yaml",
            "03-falco-fast-track-relay.yaml",
        ]
        for fname in expected_files:
            fpath = K8S_LAYER5_DIR / fname
            assert fpath.exists(), f"Missing Layer 5 manifest: {fpath}"
            docs = list(yaml.safe_load_all(fpath.read_text(encoding="utf-8")))
            assert len(docs) >= 1
            for doc in docs:
                assert doc is not None
                assert "apiVersion" in doc
                assert "kind" in doc
                assert doc["metadata"]["namespace"] == "siem-system"
                assert doc["metadata"]["labels"]["vlab.siem/layer"] == "5-detection"

    def test_grafana_provisions_complete_siem_command_center_dashboard(self):
        gf_docs = list(
            yaml.safe_load_all(
                (K8S_LAYER5_DIR / "00-grafana-deployment.yaml").read_text(encoding="utf-8")
            )
        )
        prov_cm = next(d for d in gf_docs if d["kind"] == "ConfigMap")
        assert "datasources.yaml" in prov_cm["data"]
        assert "dashboards.yaml" in prov_cm["data"]
        assert "alerting.yaml" in prov_cm["data"]

        dash_cm = yaml.safe_load(
            (K8S_LAYER5_DIR / "01-grafana-dashboards-configmap.yaml").read_text(encoding="utf-8")
        )
        dashboard = json.loads(dash_cm["data"]["vlab-siem-command-center.json"])
        assert dashboard["uid"] == "vlab-siem-5layer"
        panel_titles = " ".join(p["title"] for p in dashboard["panels"])
        assert "Falco eBPF Fast-Track" in panel_titles
        assert "Squid Proxy Egress Drops" in panel_titles
        assert "Kyverno Policy Blocks" in panel_titles
        assert "Tailscale Unauthorized Access" in panel_titles
        assert "Sigma Rule Detections" in panel_titles
        assert "MITRE ATT&CK" in panel_titles
        assert "GeoIP Enrichment" in panel_titles

    def test_sigma_rules_compile_to_logsql_and_run_on_1_to_5_minute_cronjob(self):
        sigma_docs = list(
            yaml.safe_load_all(
                (K8S_LAYER5_DIR / "02-sigma-rules-cronjob.yaml").read_text(encoding="utf-8")
            )
        )
        cm = next(d for d in sigma_docs if d["kind"] == "ConfigMap")
        for rule_file in (
            "sigma_rule_01_container_shadow_access.yml",
            "sigma_rule_02_c2_botnet_egress.yml",
            "sigma_rule_03_cryptomining_stratum.yml",
            "sigma_rule_04_k8s_privilege_escalation.yml",
        ):
            assert rule_file in cm["data"]
            parsed_rule = yaml.safe_load(cm["data"][rule_file])
            assert "detection" in parsed_rule
            assert "selection" in parsed_rule["detection"]

        engine_code = cm["data"]["sigma_logsql_engine.py"]
        assert "compile_sigma_to_logsql" in engine_code
        assert "/select/logsql/query" in engine_code
        assert "SIGMA_RULE_MATCH" in engine_code

        cron = next(d for d in sigma_docs if d["kind"] == "CronJob")
        assert cron["metadata"]["name"] == "sigma-logsql-detector"
        assert cron["spec"]["schedule"] == "*/2 * * * *"

    def test_falco_fast_track_express_pipeline_bypasses_batching_in_sub_second(self):
        ft_docs = list(
            yaml.safe_load_all(
                (K8S_LAYER5_DIR / "03-falco-fast-track-relay.yaml").read_text(encoding="utf-8")
            )
        )
        cm = next(d for d in ft_docs if d["kind"] == "ConfigMap")
        assert cm["metadata"]["labels"]["vlab.siem/pipeline"] == "fast-track"
        relay_code = cm["data"]["fast_track_relay.py"]
        assert '"fast_track": True' in relay_code
        assert '"bypass_sigma_batch": True' in relay_code
        assert "sub_second" in relay_code

