#!/bin/bash
################################################################################
# 02-k3s/install-worker.sh
#
# Join a worker node เข้า K3s cluster
#
# รัน script นี้บน on-prem machine ที่จะเป็น K3s worker node
#
# Usage (ตัวเลือก 1 — ตั้ง env ก่อน):
#   export K3S_MASTER_IP=192.168.1.100
#   export K3S_NODE_TOKEN=K10xxx...
#   bash install-worker.sh
#
# Usage (ตัวเลือก 2 — inline):
#   K3S_MASTER_IP=192.168.1.100 K3S_NODE_TOKEN=K10xxx... bash install-worker.sh
#
# หรือ source credentials.env แล้วรัน (credentials.env ต้องมี K3S_MASTER_IP + K3S_NODE_TOKEN)
################################################################################
set -euo pipefail

echo "════════════════════════════════════════════════════════════"
echo "  VirtualLab — K3s Worker Node Join"
echo "════════════════════════════════════════════════════════════"
echo ""

# ── Validate required env vars ───────────────────────────────────────────────
if [[ -z "${K3S_MASTER_IP:-}" ]]; then
  echo "❌ K3S_MASTER_IP is not set."
  echo "   export K3S_MASTER_IP=<master-ip> then re-run."
  exit 1
fi
if [[ -z "${K3S_NODE_TOKEN:-}" ]]; then
  echo "❌ K3S_NODE_TOKEN is not set."
  echo "   Get it from master: sudo cat /var/lib/rancher/k3s/server/node-token"
  exit 1
fi

echo "→ Joining cluster at https://${K3S_MASTER_IP}:6443 ..."

curl -sfL https://get.k3s.io | \
  K3S_URL="https://${K3S_MASTER_IP}:6443" \
  K3S_TOKEN="${K3S_NODE_TOKEN}" \
  sh -

echo ""
echo "✅ Worker joined! Verify on master node:"
echo "   kubectl get nodes -o wide"
