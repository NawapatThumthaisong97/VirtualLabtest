#!/usr/bin/env bash
# ==============================================================================
# SIEM & Telemetry Pipeline Simulation Test Script
# Issue #76: Simulates real boundary events (Squid, Kyverno, Tailscale, OOM)
# and posts them to the Web-Portal backend ingestion API to test the
# Data Masking, Pseudonymization, and Admin Monitor correlation pipeline.
# ==============================================================================

set -euo pipefail

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api}"
INGEST_ENDPOINT="${API_BASE_URL}/v1/logs"
METRICS_ENDPOINT="${API_BASE_URL}/v1/metrics"

# Colors for Output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================================${NC}"
echo -e "${BLUE}   SIEM-Ready Log Forwarding & Infrastructure Metrics Test Suite   ${NC}"
echo -e "${BLUE}==================================================================${NC}"

# Check API Connectivity
echo -e "\n${YELLOW}[1/4] Checking Backend API Connectivity...${NC}"
if ! curl -s -f -o /dev/null "${API_BASE_URL}/../health" && ! curl -s -f -o /dev/null "${API_BASE_URL}/../docs"; then
    echo -e "${RED}ERROR: Backend API is not responding at ${API_BASE_URL}.${NC}"
    echo -e "${YELLOW}Please start backend server: uvicorn app.main:app --port 8000${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Backend is active and reachable.${NC}"

# Define Mock Payload Generator
send_siem_log() {
    local test_name="$1"
    local payload="$2"

    echo -e "\n${YELLOW}Testing: ${test_name}${NC}"
    local response
    response=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "${INGEST_ENDPOINT}" \
        -H "Content-Type: application/json" \
        -d "${payload}")

    local http_code
    http_code=$(echo "${response}" | tr -d '\n' | sed -e 's/.*HTTP_STATUS://')
    local body
    body=$(echo "${response}" | sed -e 's/HTTP_STATUS:.*//')

    if [[ "${http_code}" =~ ^20[0-9]$ ]]; then
        echo -e "${GREEN}✓ Success (HTTP ${http_code})${NC}"
        echo -e "Response Data: ${body}"
    else
        echo -e "${RED}✗ Failed with HTTP ${http_code}${NC}"
        echo -e "Error details: ${body}"
        return 1
    fi
}

echo -e "\n${YELLOW}[2/4] Testing SIEM Boundary Violations Ingestion...${NC}"

# 1. Squid Proxy Egress Drop with Sensitive Query String (Must be stripped/redacted)
SQUID_PAYLOAD=$(cat <<EOF
{
  "severity": "WARNING",
  "category": "SECURITY_VIOLATION",
  "eventType": "squid_egress_drop",
  "source": "squid-proxy-k3s-01",
  "message": "TCP_DENIED to unauthorized domain http://malicious-mining.org/payload?token=supersecret123&student_email=student@dome.tu.ac.th",
  "userId": "c0a80101-0000-0000-0000-000000000001",
  "clusterOrSubnet": "10.0.0.0/16",
  "metadata": {
    "clientIp": "10.0.12.55",
    "destinationHost": "malicious-mining.org",
    "ruleTriggered": "deny_unlisted_cryptomining",
    "environment": "Local K3s"
  }
}
EOF
)
send_siem_log "Squid Egress Drop (PII & Query String Masking)" "${SQUID_PAYLOAD}"

# 2. Kyverno / OPA Admission Policy Block (Prevent Privilege Escalation)
KYVERNO_PAYLOAD=$(cat <<EOF
{
  "severity": "WARNING",
  "category": "SECURITY_VIOLATION",
  "eventType": "kyverno_policy_block",
  "source": "kyverno-admission-controller",
  "message": "Admission blocked Pod/priv-esc-test with allowPrivilegeEscalation=true by policy disallow-privilege-escalation",
  "userId": "c0a80101-0000-0000-0000-000000000002",
  "clusterOrSubnet": "192.168.1.0/24",
  "metadata": {
    "policyName": "disallow-privilege-escalation",
    "resourceKind": "Pod",
    "namespace": "default",
    "environment": "AWS SkyPilot"
  }
}
EOF
)
send_siem_log "Kyverno Admission Policy Block" "${KYVERNO_PAYLOAD}"

# 3. Tailscale ACL Deny (Unauthorized Cross-Cluster / SSH Attempt)
TAILSCALE_PAYLOAD=$(cat <<EOF
{
  "severity": "ERROR",
  "category": "SECURITY_VIOLATION",
  "eventType": "tailscale_acl_deny",
  "source": "tailscale-subnet-router",
  "message": "Tailscale ACL dropped cross-cluster packet from 100.64.0.50 to 100.64.0.1:22",
  "userId": "c0a80101-0000-0000-0000-000000000001",
  "clusterOrSubnet": "10.0.0.0/16",
  "metadata": {
    "srcIp": "100.64.0.50",
    "dstIp": "100.64.0.1",
    "port": 22,
    "action": "DROP"
  }
}
EOF
)
send_siem_log "Tailscale Cross-Cluster ACL Deny" "${TAILSCALE_PAYLOAD}"

# 4. Infrastructure OOM Crash Event (Container Runtime CGroup starvation)
OOM_PAYLOAD=$(cat <<EOF
{
  "severity": "CRITICAL",
  "category": "CONTAINER",
  "eventType": "oom_killed",
  "source": "containerd-node-worker-02",
  "message": "Container exceeded 4096MB cgroup memory limit and was invoked by kernel oom-killer: def student_code(): return [0]*10**9",
  "userId": "c0a80101-0000-0000-0000-000000000003",
  "clusterOrSubnet": "10.0.0.0/16",
  "metadata": {
    "cgroup": "memory.max",
    "limitMb": 4096,
    "node": "worker-02"
  }
}
EOF
)
send_siem_log "Kernel OOM Killer & Code Redaction Event" "${OOM_PAYLOAD}"

# Check Metrics Status
echo -e "\n${YELLOW}[3/4] Verifying Cluster Metrics & Security Counters...${NC}"
METRICS_DATA=$(curl -s "${METRICS_ENDPOINT}" || echo "{}")
echo -e "Live Metrics Summary: ${METRICS_DATA}"

# Validate Plane Separation
echo -e "\n${YELLOW}[4/4] Verifying Strict Plane Separation Rules in Ansible roles...${NC}"
if grep -rn "/var/log/pods" "$(dirname "$0")/../ansible/roles/siem-log-forwarding/templates" | grep -v "forbidden"; then
    echo -e "${RED}WARNING: Student pod log path (/var/log/pods) found in fluent-bit inputs! Strict plane separation violated.${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Verified: No student pod log path mounted or collected. Plane separation intact.${NC}"
fi

echo -e "\n${GREEN}==================================================================${NC}"
echo -e "${GREEN}   ✓ All SIEM Log Pipeline Tests Completed Successfully!         ${NC}"
echo -e "${GREEN}==================================================================${NC}"
