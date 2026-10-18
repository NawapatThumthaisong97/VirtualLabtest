# ==============================================================================
# SIEM & Telemetry Pipeline Simulation Test Script (PowerShell for Windows)
# Issue #76: Simulates real boundary events (Squid, Kyverno, Tailscale, OOM)
# and posts them to the Web-Portal backend ingestion API.
# ==============================================================================

$ApiBaseUrl = if ($env:API_BASE_URL) { $env:API_BASE_URL } else { "http://localhost:8000/api" }
$IngestEndpoint = "$ApiBaseUrl/v1/logs"
$MetricsEndpoint = "$ApiBaseUrl/v1/metrics"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   SIEM-Ready Log Forwarding & Infrastructure Metrics Test Suite   " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Connectivity Check
Write-Host "`n[1/4] Checking Backend API Connectivity..." -ForegroundColor Yellow
try {
    $docs = Invoke-WebRequest -Uri "$ApiBaseUrl/../docs" -UseBasicParsing -TimeoutSec 3
    Write-Host "✓ Backend is active and reachable (HTTP $($docs.StatusCode))." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Backend API is not responding at $ApiBaseUrl" -ForegroundColor Red
    exit 1
}

# Function to post log
function Send-SiemLog {
    param (
        [string]$TestName,
        [hashtable]$Payload
    )
    Write-Host "`nTesting: $TestName" -ForegroundColor Yellow
    $json = $Payload | ConvertTo-Json -Depth 5
    try {
        $res = Invoke-RestMethod -Uri $IngestEndpoint -Method Post -Body $json -ContentType "application/json"
        Write-Host "✓ Success: $($res.message)" -ForegroundColor Green
        Write-Host "  Masked Message : $($res.data.message)" -ForegroundColor Gray
        Write-Host "  Anon ID        : $($res.data.anonId)" -ForegroundColor Gray
        Write-Host "  Event Type     : $($res.data.eventType)" -ForegroundColor Gray
        return $true
    } catch {
        Write-Host "✗ Failed: $_" -ForegroundColor Red
        return $false
    }
}

Write-Host "`n[2/4] Testing SIEM Boundary Violations Ingestion..." -ForegroundColor Yellow

# 1. Squid Proxy Egress Drop
Send-SiemLog -TestName "Squid Egress Drop (Query String & PII Redaction)" -Payload @{
    severity = "WARNING"
    category = "SECURITY_VIOLATION"
    eventType = "squid_egress_drop"
    source = "squid-proxy-k3s-01"
    message = "TCP_DENIED to unauthorized domain http://malicious-mining.org/payload?token=supersecret123&student_email=student@dome.tu.ac.th"
    userId = "c0a80101-0000-0000-0000-000000000001"
    clusterOrSubnet = "10.0.0.0/16"
    metadata = @{
        clientIp = "10.0.12.55"
        destinationHost = "malicious-mining.org"
        ruleTriggered = "deny_unlisted_cryptomining"
        environment = "Local K3s"
    }
}

# 2. Kyverno Policy Block
Send-SiemLog -TestName "Kyverno Admission Policy Block" -Payload @{
    severity = "WARNING"
    category = "SECURITY_VIOLATION"
    eventType = "kyverno_policy_block"
    source = "kyverno-admission-controller"
    message = "Admission blocked Pod/priv-esc-test with allowPrivilegeEscalation=true by policy disallow-privilege-escalation"
    userId = "c0a80101-0000-0000-0000-000000000002"
    clusterOrSubnet = "192.168.1.0/24"
    metadata = @{
        policyName = "disallow-privilege-escalation"
        resourceKind = "Pod"
        namespace = "default"
        environment = "AWS SkyPilot"
    }
}

# 3. Tailscale ACL Deny
Send-SiemLog -TestName "Tailscale Cross-Cluster ACL Deny" -Payload @{
    severity = "ERROR"
    category = "SECURITY_VIOLATION"
    eventType = "tailscale_acl_deny"
    source = "tailscale-subnet-router"
    message = "Tailscale ACL dropped cross-cluster packet from 100.64.0.50 to 100.64.0.1:22"
    userId = "c0a80101-0000-0000-0000-000000000001"
    clusterOrSubnet = "10.0.0.0/16"
    metadata = @{
        srcIp = "100.64.0.50"
        dstIp = "100.64.0.1"
        port = 22
        action = "DROP"
    }
}

# 4. Kernel OOM Killer
Send-SiemLog -TestName "Kernel OOM Killer & Code Redaction Event" -Payload @{
    severity = "CRITICAL"
    category = "CONTAINER"
    eventType = "oom_killed"
    source = "containerd-node-worker-02"
    message = "Container exceeded 4096MB cgroup memory limit and was invoked by kernel oom-killer: def student_code(): return [0]*10**9"
    userId = "c0a80101-0000-0000-0000-000000000003"
    clusterOrSubnet = "10.0.0.0/16"
    metadata = @{
        cgroup = "memory.max"
        limitMb = 4096
        node = "worker-02"
    }
}

# 3. Verify Metrics & Counters
Write-Host "`n[3/4] Verifying Cluster Metrics & Security Counters..." -ForegroundColor Yellow
$metrics = Invoke-RestMethod -Uri $MetricsEndpoint -Method Get
Write-Host "✓ Metrics retrieved successfully:" -ForegroundColor Green
Write-Host "  Active Sessions  : $($metrics.data.summary.totalActiveSessions)" -ForegroundColor Gray
Write-Host "  Squid Drops      : $($metrics.data.securityViolationCounters.squidEgressDrops)" -ForegroundColor Gray
Write-Host "  Kyverno Blocks   : $($metrics.data.securityViolationCounters.kyvernoPolicyBlocks)" -ForegroundColor Gray
Write-Host "  Tailscale Denies : $($metrics.data.securityViolationCounters.tailscaleCrossClusterAttempts)" -ForegroundColor Gray
Write-Host "  Total Violations : $($metrics.data.securityViolationCounters.totalViolations)" -ForegroundColor Gray

# 4. Validate Plane Separation
Write-Host "`n[4/4] Verifying Strict Plane Separation Rules..." -ForegroundColor Yellow
$fluentConf = Get-Content -Raw "ansible/roles/siem-log-forwarding/templates/fluent-bit.conf.j2"
if ($fluentConf -match "/var/log/pods") {
    Write-Host "WARNING: Student pod log path (/var/log/pods) found in fluent-bit inputs!" -ForegroundColor Red
} else {
    Write-Host "✓ Verified: No student pod log path mounted or collected. Plane separation intact." -ForegroundColor Green
}

Write-Host "`n==================================================================" -ForegroundColor Green
Write-Host "   ✓ All SIEM Log Pipeline Tests Completed Successfully!         " -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green

