import os
from pathlib import Path
import yaml
import pytest


def get_k8s_auth_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    k8s_auth = repo_root / "k8s" / "auth"
    assert k8s_auth.is_dir(), f"k8s auth directory not found at {k8s_auth}"
    return k8s_auth


class TestKubernetesAuthInfrastructure:
    """DevOps - Authentication Secrets & Infrastructure (Issue #81)"""

    def test_all_k8s_manifests_are_valid_yaml(self):
        """All YAML manifests in k8s/auth must be syntactically valid"""
        k8s_dir = get_k8s_auth_dir()
        yaml_files = list(k8s_dir.glob("*.yaml"))
        assert len(yaml_files) >= 6, "Expected at least 6 k8s manifest files"

        for yf in yaml_files:
            with open(yf, "r", encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f))
                assert len(docs) > 0, f"Empty YAML file: {yf.name}"
                for doc in docs:
                    if doc is not None:
                        assert "apiVersion" in doc, f"Missing apiVersion in {yf.name}"
                        assert "kind" in doc, f"Missing kind in {yf.name}"

    def test_constraint_no_hardcoded_secrets_in_manifests(self):
        """Constraint 1: Secrets must never be hardcoded in manifests (only secretKeyRef or template placeholders)"""
        k8s_dir = get_k8s_auth_dir()

        for yf in k8s_dir.glob("*.yaml"):
            content = yf.read_text(encoding="utf-8")
            # Ensure no real JWT key, private tokens, or unmasked client secrets are committed
            assert "eyJh" not in content, f"Possible hardcoded JWT token found in {yf.name}"
            assert "AIzaSy" not in content, f"Possible Google API key found in {yf.name}"

    def test_rbac_least_privilege_enforcement(self):
        """RBAC Role must restrict secret access to specific resourceNames with read-only verbs"""
        k8s_dir = get_k8s_auth_dir()
        rbac_file = k8s_dir / "01-rbac.yaml"

        with open(rbac_file, "r", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))

        roles = [d for d in docs if d and d.get("kind") == "Role"]
        assert len(roles) >= 2, "Expected at least auth-secrets-reader and oauth2-proxy-secret-reader roles"

        auth_role = next(r for r in roles if r["metadata"]["name"] == "auth-secrets-reader")
        rule = auth_role["rules"][0]
        assert rule["resources"] == ["secrets"]
        assert "jwt-secret" in rule["resourceNames"]
        assert "google-oauth-secret" in rule["resourceNames"]
        assert "oauth2-proxy-secret" in rule["resourceNames"]
        # Only read verbs allowed, no delete, create, or update
        for verb in rule["verbs"]:
            assert verb in ["get", "watch", "list"]

    def test_oauth2_proxy_google_sso_and_domain_restrictions(self):
        """oauth2-proxy config must enforce Google provider and dome.tu.ac.th / tu.ac.th domain filtering"""
        k8s_dir = get_k8s_auth_dir()
        config_file = k8s_dir / "03-oauth2-proxy-config.yaml"

        with open(config_file, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)

        cfg_text = doc["data"]["oauth2-proxy.cfg"]
        assert 'provider = "google"' in cfg_text
        assert "dome.tu.ac.th" in cfg_text
        assert "tu.ac.th" in cfg_text
        assert "set_xauthrequest = true" in cfg_text
        assert "pass_user_headers = true" in cfg_text

    def test_backend_and_oauth2_proxy_use_kubernetes_secrets(self):
        """Backend and oauth2-proxy deployments must mount credentials via secretKeyRef"""
        k8s_dir = get_k8s_auth_dir()

        # Check oauth2-proxy deployment
        proxy_file = k8s_dir / "04-oauth2-proxy-deployment.yaml"
        with open(proxy_file, "r", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
        proxy_dep = next(d for d in docs if d and d.get("kind") == "Deployment")
        env_vars = proxy_dep["spec"]["template"]["spec"]["containers"][0]["env"]
        env_map = {e["name"]: e.get("valueFrom", {}).get("secretKeyRef", {}) for e in env_vars}

        assert env_map["OAUTH2_PROXY_CLIENT_ID"]["name"] == "google-oauth-secret"
        assert env_map["OAUTH2_PROXY_CLIENT_SECRET"]["name"] == "google-oauth-secret"
        assert env_map["OAUTH2_PROXY_COOKIE_SECRET"]["name"] == "oauth2-proxy-secret"

        # Check backend deployment
        backend_file = k8s_dir / "06-backend-deployment.yaml"
        with open(backend_file, "r", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
        backend_dep = next(d for d in docs if d and d.get("kind") == "Deployment")
        b_env_vars = backend_dep["spec"]["template"]["spec"]["containers"][0]["env"]
        b_env_map = {e["name"]: e.get("valueFrom", {}).get("secretKeyRef", {}) for e in b_env_vars if "valueFrom" in e}

        assert b_env_map["SECRET_KEY"]["name"] == "jwt-secret"
        assert b_env_map["GOOGLE_CLIENT_ID"]["name"] == "google-oauth-secret"
        assert b_env_map["GOOGLE_CLIENT_SECRET"]["name"] == "google-oauth-secret"
        assert b_env_map["DATABASE_URL"]["name"] == "database-secret"
