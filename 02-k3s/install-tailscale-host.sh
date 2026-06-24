#!/bin/bash
################################################################################
# 02-k3s/install-tailscale-host.sh
#
# ติดตั้ง Tailscale โดยตรงบน K3s master host (on-prem)
# และ advertise on-prem subnet ไปยัง Tailnet
#
# ทำงานร่วมกับ Terraform: t4g.nano บน AWS จะ advertise VPC CIDR ฝั่ง AWS
# script นี้ advertise on-prem CIDR ฝั่ง on-prem
#
# Prerequisites:
#   - TAILSCALE_AUTH_KEY ใน environment
#   - K3S_ONPREM_CIDR ใน environment (default: 192.168.0.0/24)
#
# Usage:
#   source credentials.env
#   bash 02-k3s/install-tailscale-host.sh
################################################################################
set -euo pipefail

echo "════════════════════════════════════════════════════════════"
echo "  VirtualLab — Tailscale Host Install (On-Prem Router)"
echo "════════════════════════════════════════════════════════════"
echo ""

# ── Validate ─────────────────────────────────────────────────────────────────
if [[ -z "${TAILSCALE_AUTH_KEY:-}" ]]; then
  echo "❌ TAILSCALE_AUTH_KEY is not set."
  echo "   source credentials.env then re-run."
  exit 1
fi

# Default on-prem CIDR — override via K3S_ONPREM_CIDR env var
ONPREM_CIDR="${K3S_ONPREM_CIDR:-192.168.0.0/24}"
echo "→ Will advertise on-prem CIDR: $ONPREM_CIDR"
echo ""

# ── 1. Install Tailscale ──────────────────────────────────────────────────────
echo "→ Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh
echo "✅ Tailscale installed"

# ── 2. Enable IP forwarding (required for subnet routing) ────────────────────
echo ""
echo "→ Enabling IP forwarding..."
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
echo "✅ IP forwarding enabled"

# ── 3. Authenticate and advertise routes ─────────────────────────────────────
echo ""
echo "→ Connecting to Tailnet and advertising routes..."
sudo tailscale up \
  --authkey="${TAILSCALE_AUTH_KEY}" \
  --advertise-routes="${ONPREM_CIDR}" \
  --advertise-tags="tag:virtuallab-router" \
  --hostname="virtuallab-onprem-router" \
  --accept-routes

echo "✅ Tailscale connected"

# ── 4. Verify ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Tailscale Status ==="
tailscale status
echo ""
echo "=== Tailscale IP ==="
tailscale ip -4
echo ""

echo "════════════════════════════════════════════════════════════"
echo "✅ Tailscale ready!"
echo ""
echo "⚠️  NEXT STEP: ใน Tailscale Admin Console:"
echo "   https://login.tailscale.com/admin/machines"
echo "   → คลิก machine 'virtuallab-onprem-router'"
echo "   → Enable route: $ONPREM_CIDR"
echo "   (ต้อง approve subnet route ก่อนถึงจะ route ได้)"
echo "════════════════════════════════════════════════════════════"
