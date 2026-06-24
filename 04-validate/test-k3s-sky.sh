#!/bin/bash
################################################################################
# 04-validate/test-k3s-sky.sh
#
# ทดสอบ K3s cluster + SkyPilot readiness:
#   1. kubectl ทำงาน และ nodes อยู่ใน Ready state
#   2. sky check ผ่าน kubernetes context
#   3. sky check ผ่าน aws context
#
# Usage:
#   source ~/skypilot-venv/bin/activate
#   bash 04-validate/test-k3s-sky.sh
################################################################################
set -euo pipefail

echo "=== K3s + SkyPilot Validation ==="
echo ""

PASS=true

# ── 1. kubectl connectivity ───────────────────────────────────────────────────
echo "→ [1/3] Checking kubectl + K3s nodes..."
if ! command -v kubectl &>/dev/null; then
    echo "   ❌ kubectl not found — install kubectl first"
    PASS=false
else
    echo "   kubectl version: $(kubectl version --client --short 2>/dev/null | head -1)"
    echo ""
    NODE_STATUS=$(kubectl get nodes --no-headers 2>/dev/null || echo "")
    if [ -z "$NODE_STATUS" ]; then
        echo "   ❌ Cannot reach K3s cluster (check KUBECONFIG)"
        PASS=false
    else
        NOT_READY=$(echo "$NODE_STATUS" | grep -v " Ready " | wc -l)
        TOTAL=$(echo "$NODE_STATUS" | wc -l)
        echo "   K3s Nodes ($TOTAL total, $NOT_READY not ready):"
        echo "$NODE_STATUS" | sed 's/^/   /'
        if [ "$NOT_READY" -eq 0 ]; then
            echo "   ✅ All $TOTAL K3s node(s) Ready"
        else
            echo "   ❌ $NOT_READY node(s) NOT Ready"
            PASS=false
        fi
    fi
fi

# ── 2. SkyPilot installed ─────────────────────────────────────────────────────
echo ""
echo "→ [2/3] Checking SkyPilot..."
if ! command -v sky &>/dev/null; then
    echo "   ❌ 'sky' command not found"
    echo "      Activate venv: source ~/skypilot-venv/bin/activate"
    echo "      Or install:    bash 03-skypilot/setup-skypilot.sh"
    PASS=false
else
    echo "   SkyPilot version: $(sky --version 2>/dev/null)"
fi

# ── 3. sky check ─────────────────────────────────────────────────────────────
echo ""
echo "→ [3/3] Running sky check..."
if sky check 2>&1 | tee /tmp/sky-check.log; then
    if grep -q "kubernetes.*OK\|kubernetes.*enabled" /tmp/sky-check.log 2>/dev/null; then
        echo "   ✅ SkyPilot: Kubernetes context OK"
    else
        echo "   ⚠️  SkyPilot: Kubernetes context not confirmed"
    fi
    if grep -q "aws.*OK\|aws.*enabled" /tmp/sky-check.log 2>/dev/null; then
        echo "   ✅ SkyPilot: AWS context OK"
    else
        echo "   ⚠️  SkyPilot: AWS not configured — check credentials.env"
    fi
else
    echo "   ❌ sky check failed"
    PASS=false
fi

echo ""
if [ "$PASS" = "true" ]; then
    echo "✅ K3s + SkyPilot test PASSED"
else
    echo "❌ K3s + SkyPilot test FAILED — fix issues above"
    exit 1
fi
