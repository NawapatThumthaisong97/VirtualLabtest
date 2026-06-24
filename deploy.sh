#!/bin/bash
################################################################################
# deploy.sh — Deploy entire AI Learner Lab stack from credentials.env
#
# Prerequisites:
#   1. credentials.env filled in (cp credentials.env.example credentials.env)
#   2. terraform apply done (infrastructure/terraform/)
#   3. kubectl connected to K3s cluster
#   4. Helm 3 installed
#
# Usage:
#   bash deploy.sh              # Full deploy
#   bash deploy.sh --dry-run    # Show helm diff only (requires helm-diff plugin)
#   bash deploy.sh --tf-only    # Terraform only
#   bash deploy.sh --helm-only  # Helm only (skip Terraform)
################################################################################

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED_FILE="$REPO_ROOT/credentials.env"
TF_DIR="$REPO_ROOT/infrastructure/terraform"
HELM_DIR="$REPO_ROOT/k8s-helm"
NAMESPACE="virtuallab"

# ── Parse flags ───────────────────────────────────────────────────────────────
DRY_RUN=false
TF_ONLY=false
HELM_ONLY=false
for arg in "$@"; do
  case $arg in
    --dry-run)  DRY_RUN=true ;;
    --tf-only)  TF_ONLY=true ;;
    --helm-only) HELM_ONLY=true ;;
  esac
done

echo "════════════════════════════════════════════════════════════"
echo "  AI Learner Lab — Full Stack Deploy"
echo "════════════════════════════════════════════════════════════"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# Step 0: Load credentials.env
# ══════════════════════════════════════════════════════════════════════════════

if [ ! -f "$CRED_FILE" ]; then
    echo "❌ credentials.env not found!"
    echo "   Run: cp credentials.env.example credentials.env"
    echo "   Then fill in all values."
    exit 1
fi

# shellcheck disable=SC1090
source "$CRED_FILE"
echo "✅ [0/3] credentials.env loaded"

# Validate required values
REQUIRED_VARS=(
    "AWS_ACCESS_KEY_ID"
    "AWS_SECRET_ACCESS_KEY"
    "AWS_DEFAULT_REGION"
    "TAILSCALE_AUTH_KEY"
    "CLOUDFLARE_TUNNEL_TOKEN"
    "CLOUDFLARE_TUNNEL_DOMAIN"
    "GOOGLE_CLIENT_ID"
    "GOOGLE_CLIENT_SECRET"
    "OAUTH2_COOKIE_SECRET"
    "POSTGRES_PASSWORD"
    "ML_BUCKET_NAME"
)
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
    val="${!var:-}"
    if [[ -z "$val" || "$val" == *"REPLACE_ME"* ]]; then
        MISSING+=("$var")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "❌ Missing or unfilled credentials:"
    for v in "${MISSING[@]}"; do echo "   • $v"; done
    exit 1
fi

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION

# ══════════════════════════════════════════════════════════════════════════════
# Step 1: Terraform (if not --helm-only)
# ══════════════════════════════════════════════════════════════════════════════

if [ "$HELM_ONLY" = false ]; then
    echo ""
    echo "--- [1/3] Terraform ---"
    pushd "$TF_DIR" > /dev/null

    terraform init -upgrade
    terraform plan -out=tfplan

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] Skipping terraform apply"
    else
        terraform apply tfplan
        echo "✅ [1/3] Terraform apply complete"
    fi
    popd > /dev/null
fi

# ══════════════════════════════════════════════════════════════════════════════
# Step 2: Read Terraform outputs (needed for Helm --set values)
# ══════════════════════════════════════════════════════════════════════════════

if [ "$TF_ONLY" = false ]; then
    echo ""
    echo "--- [2/3] Reading Terraform outputs ---"
    pushd "$TF_DIR" > /dev/null

    PRIVATE_SUBNET_ID=$(terraform output -raw private_subnet_id 2>/dev/null || echo "")
    SG_SPOT_WORKERS_ID=$(terraform output -raw sg_spot_workers_id 2>/dev/null || echo "")

    popd > /dev/null

    if [[ -z "$PRIVATE_SUBNET_ID" || -z "$SG_SPOT_WORKERS_ID" ]]; then
        echo "❌ Could not read Terraform outputs."
        echo "   Run terraform apply first, or use --helm-only and set manually:"
        echo "   export PRIVATE_SUBNET_ID=subnet-xxxx"
        echo "   export SG_SPOT_WORKERS_ID=sg-xxxx"
        PRIVATE_SUBNET_ID="${PRIVATE_SUBNET_ID:-subnet-REPLACE_ME}"
        SG_SPOT_WORKERS_ID="${SG_SPOT_WORKERS_ID:-sg-REPLACE_ME}"
    fi

    echo "  private_subnet_id:  $PRIVATE_SUBNET_ID"
    echo "  sg_spot_workers_id: $SG_SPOT_WORKERS_ID"
    echo "✅ [2/3] Terraform outputs read"

    # ── Step 2b: Create aws-credentials K8s Secret ────────────────────────────
    echo ""
    echo "  Creating/updating aws-credentials K8s Secret..."
    kubectl get namespace "$NAMESPACE" &>/dev/null || kubectl create namespace "$NAMESPACE"

    kubectl create secret generic aws-credentials \
        --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
        --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
        --namespace="$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "  ✅ aws-credentials Secret ready"

    # ══════════════════════════════════════════════════════════════════════════
    # Step 3: Helm deploy
    # ══════════════════════════════════════════════════════════════════════════

    echo ""
    echo "--- [3/3] Helm Deploy ---"

    HELM_CMD=(
        helm upgrade --install virtuallab "$HELM_DIR"
        --namespace "$NAMESPACE"
        --create-namespace
        # ── From credentials.env ──
        --set global.cloudflare.tunnelToken="$CLOUDFLARE_TUNNEL_TOKEN"
        --set global.domain="$CLOUDFLARE_TUNNEL_DOMAIN"
        --set global.aws.region="$AWS_DEFAULT_REGION"
        --set global.aws.mlBucketName="$ML_BUCKET_NAME"
        --set global.oauth2.clientId="$GOOGLE_CLIENT_ID"
        --set global.oauth2.clientSecret="$GOOGLE_CLIENT_SECRET"
        --set global.oauth2.cookieSecret="$OAUTH2_COOKIE_SECRET"
        --set postgresql.password="$POSTGRES_PASSWORD"
        --set tailscale.authKey="$TAILSCALE_AUTH_KEY"
        --set tailscale.onPremCidr="${K3S_MASTER_IP:-192.168.0.0}/24"
        # ── From Terraform outputs ──
        --set global.aws.privateSubnetId="$PRIVATE_SUBNET_ID"
        --set global.aws.sgSpotWorkersId="$SG_SPOT_WORKERS_ID"
    )

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] Would run:"
        printf '    %s \\\n' "${HELM_CMD[@]}"
        "${HELM_CMD[@]}" --dry-run
    else
        "${HELM_CMD[@]}"
        echo "✅ [3/3] Helm deploy complete"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════════════════════

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ Deploy complete!"
echo ""
echo "Verify:"
echo "  kubectl get pods -n $NAMESPACE"
echo "  kubectl logs -n $NAMESPACE deployment/fastapi"
echo "════════════════════════════════════════════════════════════"
