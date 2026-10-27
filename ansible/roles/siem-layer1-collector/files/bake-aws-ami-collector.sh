#!/usr/bin/env bash
# ==============================================================================
# bake-aws-ami-collector.sh
# Provisions Layer 1 SIEM Collector (Vector Agent + Falco modern_ebpf + Tailscale)
# into the AWS EC2 Base AMI used by SkyPilot (AWS_LAB_AMI).
#
# Why bake into AMI?
# Ephemeral EC2 instances launched by SkyPilot boot in <60s and may terminate
# immediately after a student finishes or attacks a lab. Baking Vector + Falco
# (modern_ebpf) directly into the AMI ensures zero install time at boot and
# immediate kernel-level eBPF monitoring + log streaming over Tailscale.
# ==============================================================================
set -euo pipefail

SIEM_CENTRAL_TAILSCALE_IP="${SIEM_CENTRAL_TAILSCALE_IP:-100.86.87.27}"
SIEM_CENTRAL_PORT="${SIEM_CENTRAL_PORT:-8000}"

echo "[1/4] Installing Tailscale for encrypted overlay transport..."
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable tailscaled

echo "[2/4] Installing Falco (modern_ebpf engine - CO-RE, no kernel headers needed)..."
install -m 0755 -d /usr/share/keyrings /var/log/falco /etc/falco/rules.d
curl -fsSL https://falco.org/repo/falcosecurity-packages.asc -o /usr/share/keyrings/falco-archive-keyring.asc
echo "deb [signed-by=/usr/share/keyrings/falco-archive-keyring.asc] https://download.falco.org/packages/deb stable main" \
  > /etc/apt/sources.list.d/falcosecurity.list

echo "[3/4] Installing Vector Agent..."
curl -1sLf 'https://repositories.timber.io/public/vector/cfg/setup/bash.deb.sh' | bash

export DEBIAN_FRONTEND=noninteractive
export FALCO_FRONTEND=noninteractive
export FALCO_DRIVER_CHOICE=modern_ebpf
apt-get update -y
apt-get install -y --no-install-recommends falco vector
apt-get clean && rm -rf /var/lib/apt/lists/*

echo "[4/4] Enabling systemd units for AWS EC2 SkyPilot boot..."
systemctl enable falco-modern-bpf.service || true
systemctl enable vector.service

echo "✓ Layer 1 SIEM Collector (Vector Agent + Falco eBPF) baked into AWS AMI."
echo "  Outbound telemetry target: http://${SIEM_CENTRAL_TAILSCALE_IP}:${SIEM_CENTRAL_PORT} (via tailscale0 only)"
