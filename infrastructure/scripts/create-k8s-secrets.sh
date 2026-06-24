#!/usr/bin/env bash
###############################################################################
# create-k8s-secrets.sh
#
# Day-0 script: Creates the Kubernetes Secret containing AWS credentials for
# the SkyPilot / FastAPI pod.
#
# USAGE:
#   cd infrastructure/terraform
#   terraform apply
#   # Then from repo root:
#   bash infrastructure/scripts/create-k8s-secrets.sh
#
# ⚠️  NEVER commit the actual key values to git.
#     This script reads them from Terraform outputs at runtime.
###############################################################################

set -euo pipefail

NAMESPACE="ailab"

echo "=== AI Learner Lab: Create K8s AWS Credentials Secret ==="

# ── Pre-flight checks ──────────────────────────────────────────────────────────

if ! command -v kubectl &>/dev/null; then
  echo "ERROR: kubectl not found. Install it first (see README Prerequisites)."
  exit 1
fi

if ! command -v terraform &>/dev/null; then
  echo "ERROR: terraform not found. Run this script from inside WSL."
  exit 1
fi

TERRAFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../terraform" && pwd)"

if [ ! -f "$TERRAFORM_DIR/terraform.tfstate" ]; then
  echo "ERROR: No terraform.tfstate found at $TERRAFORM_DIR"
  echo "       Run 'terraform apply' first."
  exit 1
fi

# ── Read credentials from Terraform outputs ────────────────────────────────────

echo "Reading IAM credentials from Terraform outputs..."
pushd "$TERRAFORM_DIR" > /dev/null

AWS_ACCESS_KEY_ID=$(terraform output -raw iam_access_key_id)
AWS_SECRET_ACCESS_KEY=$(terraform output -raw iam_secret_access_key)

popd > /dev/null

if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" ]]; then
  echo "ERROR: Could not read IAM credentials from Terraform outputs."
  exit 1
fi

echo "  AWS_ACCESS_KEY_ID  = ${AWS_ACCESS_KEY_ID:0:8}... (truncated for safety)"

# ── Create namespace if it doesn't exist ──────────────────────────────────────

kubectl get namespace "$NAMESPACE" &>/dev/null || \
  kubectl create namespace "$NAMESPACE"
echo "  Namespace '$NAMESPACE' ready."

# ── Create (or update) the secret ─────────────────────────────────────────────

kubectl create secret generic aws-credentials \
  --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  --namespace="$NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "[OK] Secret 'aws-credentials' created/updated in namespace '$NAMESPACE'"
echo ""
echo "Verify with:"
echo "  kubectl get secret aws-credentials -n $NAMESPACE"
echo "  (Do NOT run kubectl get secret ... -o yaml in a shared terminal — it shows the values)"
