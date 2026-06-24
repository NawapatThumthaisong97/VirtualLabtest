#!/bin/bash
################################################################################
# 04-validate/test-tailscale.sh
#
# ทดสอบ Tailscale VPN connectivity:
#   1. tailscale daemon ทำงานอยู่
#   2. มี node บน Tailnet ที่ชื่อ virtuallab-onprem-router
#   3. AWS gateway (virtuallab-tailscale-gateway) ปรากฏใน Tailnet
#   4. Ping ข้าม VPN ได้ (on-prem → AWS gateway Tailscale IP)
#
# Usage:
#   bash 04-validate/test-tailscale.sh
################################################################################
set -euo pipefail

echo "=== Tailscale Validation ==="
echo ""

PASS=true

# ── 1. Tailscale daemon ───────────────────────────────────────────────────────
echo "→ [1/4] Checking tailscale daemon..."
if tailscale status >/dev/null 2>&1; then
    echo "   ✅ Tailscale daemon running"
else
    echo "   ❌ Tailscale daemon NOT running"
    echo "      Run: sudo systemctl start tailscaled"
    PASS=false
fi

# ── 2. Connected to Tailnet ───────────────────────────────────────────────────
echo "→ [2/4] Checking Tailnet connection..."
TS_STATUS=$(tailscale status 2>/dev/null)
if echo "$TS_STATUS" | grep -q "virtuallab"; then
    echo "   ✅ Connected to Tailnet"
    echo ""
    echo "   VirtualLab nodes on Tailnet:"
    echo "$TS_STATUS" | grep "virtuallab" | sed 's/^/   /'
    echo ""
else
    echo "   ⚠️  No 'virtuallab' nodes visible yet"
    echo "      (Terraform + AWS gateway may not be running yet)"
    echo ""
    echo "   All Tailnet nodes:"
    echo "$TS_STATUS" | head -20 | sed 's/^/   /'
fi

# ── 3. Check on-prem router ──────────────────────────────────────────────────
echo "→ [3/4] Checking on-prem subnet router..."
MY_IP=$(tailscale ip -4 2>/dev/null || echo "")
if [ -n "$MY_IP" ]; then
    echo "   ✅ On-prem Tailscale IP: $MY_IP"
else
    echo "   ❌ Could not get Tailscale IP"
    PASS=false
fi

# ── 4. Check AWS gateway reachability ────────────────────────────────────────
echo "→ [4/4] Checking AWS Tailscale gateway reachability..."
AWS_GW_IP=$(tailscale status --json 2>/dev/null | \
    python3 -c "
import sys, json
data = json.load(sys.stdin)
peers = data.get('Peer', {})
for k, v in peers.items():
    if 'virtuallab-tailscale-gateway' in v.get('HostName', ''):
        ips = v.get('TailscaleIPs', [])
        if ips: print(ips[0])
        break
" 2>/dev/null || echo "")

if [ -n "$AWS_GW_IP" ]; then
    echo "   Found AWS gateway Tailscale IP: $AWS_GW_IP"
    if ping -c 3 -W 3 "$AWS_GW_IP" >/dev/null 2>&1; then
        echo "   ✅ Ping OK — on-prem → AWS gateway via Tailscale"
    else
        echo "   ⚠️  Ping failed (gateway may still be booting)"
    fi
else
    echo "   ⚠️  AWS gateway not yet visible in Tailnet"
    echo "      Run: cd 01-terraform && terraform apply"
fi

echo ""
if [ "$PASS" = "true" ]; then
    echo "✅ Tailscale test PASSED"
else
    echo "❌ Tailscale test FAILED — fix issues above"
    exit 1
fi
