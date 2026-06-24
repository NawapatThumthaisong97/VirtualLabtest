#!/bin/bash
################################################################################
# 02-k3s/install-master.sh
#
# ติดตั้ง K3s Master Node และแสดง join command สำหรับ worker nodes
#
# รัน script นี้บน on-prem machine ที่จะเป็น K3s master
# Prerequisites: Ubuntu/Debian Linux, curl
#
# Usage:
#   bash install-master.sh
################################################################################
set -euo pipefail

echo "════════════════════════════════════════════════════════════"
echo "  VirtualLab — K3s Master Node Install"
echo "════════════════════════════════════════════════════════════"
echo ""

# ── 1. Install K3s ───────────────────────────────────────────────────────────
echo "→ Installing K3s (latest stable)..."
curl -sfL https://get.k3s.io | sh -s - server \
  --disable traefik \
  --write-kubeconfig-mode 644

echo "✅ K3s installed"

# ── 2. Wait for node to be Ready ─────────────────────────────────────────────
echo ""
echo "→ Waiting for master node to be Ready..."
for i in $(seq 1 30); do
  STATUS=$(sudo kubectl get node --no-headers 2>/dev/null | awk '{print $2}' | head -1)
  if [ "$STATUS" = "Ready" ]; then
    echo "✅ Master node is Ready"
    break
  fi
  echo "   Attempt $i/30 — status: ${STATUS:-not yet}. Waiting 5s..."
  sleep 5
done

# ── 3. Setup kubeconfig for current user ─────────────────────────────────────
echo ""
echo "→ Setting up kubeconfig..."
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$(id -u):$(id -g)" ~/.kube/config
export KUBECONFIG=~/.kube/config
echo "✅ kubeconfig ready: ~/.kube/config"

# ── 4. Show node status ───────────────────────────────────────────────────────
echo ""
echo "=== K3s Nodes ==="
kubectl get nodes -o wide
echo ""

# ── 5. Show join token for workers ───────────────────────────────────────────
MASTER_IP=$(hostname -I | awk '{print $1}')
NODE_TOKEN=$(sudo cat /var/lib/rancher/k3s/server/node-token)

echo "════════════════════════════════════════════════════════════"
echo "✅ Master ready! To join a worker node, run on the worker:"
echo ""
echo "  K3S_URL=https://${MASTER_IP}:6443 \\"
echo "  K3S_TOKEN=${NODE_TOKEN} \\"
echo "  bash 02-k3s/install-worker.sh"
echo ""
echo "Or set these in credentials.env:"
echo "  K3S_MASTER_IP=${MASTER_IP}"
echo "  K3S_NODE_TOKEN=${NODE_TOKEN}"
echo "════════════════════════════════════════════════════════════"
