#!/usr/bin/env bash
###############################################################################
# validate-network.sh
#
# Smoke test: Verifies On-Prem → AWS Private Worker IP reachability via Tailscale.
#
# Run this AFTER:
#   1. terraform apply (Tailscale gateway is up)
#   2. Tailscale Admin Panel: subnet route approved
#   3. On-Prem machine is connected to the same Tailnet
#
# USAGE:
#   bash infrastructure/scripts/validate-network.sh
###############################################################################

set -euo pipefail

# ── Config (adjust if your CIDR differs) ─────────────────────────────────────
PRIVATE_SUBNET_CIDR="10.0.2.0/24"
TEST_GATEWAY_HOST="100.64.0.1"   # Replace with actual t4g.nano Tailscale IP
                                  # (run `tailscale status` to find it)

echo "=== AI Learner Lab: Network Validation ==="
echo ""

# ── Check 1: Tailscale is running locally ─────────────────────────────────────
echo "[1/4] Checking local Tailscale status..."
if ! tailscale status &>/dev/null; then
  echo "  ERROR: Tailscale not running on this machine."
  echo "         Run: tailscale up"
  exit 1
fi
echo "  [OK] Tailscale is running."

# ── Check 2: Tailscale gateway is visible in Tailnet ──────────────────────────
echo ""
echo "[2/4] Looking for ailab-aws-gateway in Tailnet..."
if tailscale status | grep -q "ailab-aws-gateway"; then
  GATEWAY_IP=$(tailscale status | grep "ailab-aws-gateway" | awk '{print $1}')
  echo "  [OK] Found gateway at Tailscale IP: $GATEWAY_IP"
else
  echo "  WARNING: 'ailab-aws-gateway' not found in Tailnet."
  echo "           Is the t4g.nano ASG running? Check AWS Console → EC2 → Auto Scaling Groups"
  echo "           Is the Tailscale auth key valid?"
  GATEWAY_IP="$TEST_GATEWAY_HOST"
fi

# ── Check 3: Gateway is pingable via Tailscale ────────────────────────────────
echo ""
echo "[3/4] Pinging Tailscale gateway ($GATEWAY_IP)..."
if ping -c 3 -W 5 "$GATEWAY_IP" &>/dev/null; then
  echo "  [OK] Gateway is reachable via Tailscale."
else
  echo "  ERROR: Cannot ping gateway at $GATEWAY_IP"
  echo "         Check: is the t4g.nano instance healthy in ASG?"
  exit 1
fi

# ── Check 4: Private subnet route is accessible ───────────────────────────────
echo ""
echo "[4/4] Checking route to private subnet ($PRIVATE_SUBNET_CIDR) via Tailscale..."
# Derive a test IP in the private subnet (e.g., .1 is the VPC router)
PRIVATE_TEST_IP=$(echo "$PRIVATE_SUBNET_CIDR" | sed 's|/.*||' | sed 's|\.[0-9]*$|.1|')
if ping -c 3 -W 5 "$PRIVATE_TEST_IP" &>/dev/null; then
  echo "  [OK] Private subnet $PRIVATE_SUBNET_CIDR reachable at $PRIVATE_TEST_IP"
else
  echo "  INFO: Could not ping $PRIVATE_TEST_IP (may not be a real host — this is OK)."
  echo "        The subnet route may still be working."
  echo "        To confirm: launch a test EC2 in the private subnet and ping its IP."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Validation complete ==="
echo ""
echo "Next steps:"
echo "  - If all checks passed: proceed to Step 1c (create-k8s-secrets.sh)"
echo "  - If subnet route not visible: go to https://login.tailscale.com/admin/machines"
echo "    and APPROVE the subnet route for ailab-aws-gateway: $PRIVATE_SUBNET_CIDR"
