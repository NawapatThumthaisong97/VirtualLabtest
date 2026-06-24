#!/bin/bash
################################################################################
# 04-validate/validate-all.sh
#
# Master validation script — รัน test ทุกอย่างตามลำดับ
# ผ่านทุก test = POC concept พิสูจน์แล้ว ✅
#
# Usage:
#   source credentials.env
#   source ~/skypilot-venv/bin/activate
#   bash 04-validate/validate-all.sh
################################################################################
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0
SKIP=0

print_header() {
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  $1"
    echo "════════════════════════════════════════════════════════"
}

print_result() {
    local status=$1 msg=$2
    if [ "$status" = "PASS" ]; then
        echo "✅ PASS — $msg"
        ((PASS++)) || true
    elif [ "$status" = "FAIL" ]; then
        echo "❌ FAIL — $msg"
        ((FAIL++)) || true
    else
        echo "⚠️  SKIP — $msg"
        ((SKIP++)) || true
    fi
}

echo "════════════════════════════════════════════════════════"
echo "  VirtualLab POC — Full Validation Suite"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "════════════════════════════════════════════════════════"

# ── Test 1: Tailscale ─────────────────────────────────────────────────────────
print_header "Test 1: Tailscale Connectivity"
bash "$REPO_ROOT/04-validate/test-tailscale.sh" && \
    print_result "PASS" "Tailscale connected + routing" || \
    print_result "FAIL" "Tailscale not healthy"

# ── Test 2: K3s Cluster ───────────────────────────────────────────────────────
print_header "Test 2: K3s Cluster"
bash "$REPO_ROOT/04-validate/test-k3s-sky.sh" && \
    print_result "PASS" "K3s nodes Ready + sky check OK" || \
    print_result "FAIL" "K3s or SkyPilot not ready"

# ── Test 3: AWS Infrastructure ────────────────────────────────────────────────
print_header "Test 3: AWS Infrastructure (Terraform outputs)"
TF_DIR="$REPO_ROOT/01-terraform"
if terraform -chdir="$TF_DIR" output -raw private_subnet_id >/dev/null 2>&1; then
    SUBNET=$(terraform -chdir="$TF_DIR" output -raw private_subnet_id)
    print_result "PASS" "Terraform outputs available — subnet: $SUBNET"
else
    print_result "FAIL" "Terraform outputs not available — run terraform apply first"
fi

# ── Test 4: SkyPilot K3s Branch (Branch A) ───────────────────────────────────
print_header "Test 4: SkyPilot K3s Branch (on-prem)"
echo "→ Launching task-k3s-test.yaml (takes 1-3 min)..."
if sky launch "$REPO_ROOT/03-skypilot/task-k3s-test.yaml" \
    --cluster vlab-validate-k3s \
    --env JOB_ID="validate-k3s-$(date +%s)" \
    --env S3_BUCKET="${ML_BUCKET_NAME:-virtuallab-ml-artifacts}" \
    --yes 2>&1 | tee /tmp/sky-k3s-test.log; then
    print_result "PASS" "K3s Branch A — job completed on on-prem"
else
    print_result "FAIL" "K3s Branch A — job failed (see /tmp/sky-k3s-test.log)"
fi

# ── Test 5: SkyPilot AWS Burst Branch (Branch B) ─────────────────────────────
print_header "Test 5: SkyPilot AWS Burst Branch (cloud)"
echo "→ Launching task-aws-burst.yaml (takes 3-8 min for Spot provisioning)..."
if sky launch "$REPO_ROOT/03-skypilot/task-aws-burst.yaml" \
    --cluster vlab-validate-aws \
    --env JOB_ID="validate-aws-$(date +%s)" \
    --env S3_BUCKET="${ML_BUCKET_NAME:-virtuallab-ml-artifacts}" \
    --yes 2>&1 | tee /tmp/sky-aws-test.log; then
    print_result "PASS" "AWS Branch B — Spot job completed, no public IP"
else
    print_result "FAIL" "AWS Branch B — failed (see /tmp/sky-aws-test.log)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Validation Summary"
echo "  ✅ PASSED : $PASS"
echo "  ❌ FAILED : $FAIL"
echo "  ⚠️  SKIPPED: $SKIP"
echo "════════════════════════════════════════════════════════"

if [ "$FAIL" -eq 0 ]; then
    echo ""
    echo "🎉 ALL TESTS PASSED — POC concept proven!"
    echo ""
    echo "Next: test the 2-tier auto routing:"
    echo "  sky launch 03-skypilot/task-2tier.yaml \\"
    echo "    --env S3_BUCKET=${ML_BUCKET_NAME:-virtuallab-ml-artifacts}"
    exit 0
else
    echo ""
    echo "⚠️  $FAIL test(s) failed. Fix issues before running task-2tier.yaml"
    exit 1
fi
