-- transform_siem.lua
-- Maps raw boundary events and journal entries into Standard SIEM Schema:
-- {
--   "timestamp": "ISO8601 string",
--   "severity": "CRITICAL" | "ERROR" | "WARNING" | "INFO",
--   "category": "INFRASTRUCTURE" | "SECURITY_VIOLATION" | "CONTAINER" | "BURST",
--   "eventType": "string",
--   "source": "string",
--   "message": "string (sanitized)",
--   "userId": "string (optional raw_user_id for pseudonymization by backend)",
--   "clusterOrSubnet": "string",
--   "metadata": {}
-- }

function cb_transform_boundary(tag, timestamp, record)
    local new_record = {}
    local now_iso = os.date("!%Y-%m-%dT%H:%M:%SZ")

    new_record["timestamp"] = now_iso
    new_record["source"] = record["source"] or tag
    new_record["metadata"] = {}

    if string.find(tag, "squid") then
        new_record["category"] = "SECURITY_VIOLATION"
        new_record["severity"] = "WARNING"
        new_record["eventType"] = "squid_egress_drop"
        
        -- Strip query parameters from URL if present
        local raw_url = record["url"] or ""
        local clean_url = string.gsub(raw_url, "%?.*", "")
        
        new_record["message"] = string.format("Squid egress dropped/denied request to %s (Status: %s)", clean_url, record["status_code"] or "TCP_DENIED")
        new_record["userId"] = record["user"] ~= "-" and record["user"] or nil
        new_record["metadata"]["clientIp"] = record["client_ip"]
        new_record["metadata"]["serverIp"] = record["server_ip"]
        new_record["metadata"]["httpStatus"] = record["http_status"]
        new_record["metadata"]["method"] = record["method"]
        new_record["metadata"]["url"] = clean_url

    elseif string.find(tag, "kyverno") then
        new_record["category"] = "SECURITY_VIOLATION"
        new_record["severity"] = "WARNING"
        new_record["eventType"] = "kyverno_policy_block"
        new_record["message"] = record["message"] or "Kyverno admission policy blocked prohibited operation"
        new_record["userId"] = record["user_id"]
        new_record["metadata"]["policy"] = record["policy"]
        new_record["metadata"]["resource"] = record["resource"]
        new_record["metadata"]["namespace"] = record["namespace"]

    elseif string.find(tag, "tailscale") then
        new_record["category"] = "SECURITY_VIOLATION"
        new_record["severity"] = "ERROR"
        new_record["eventType"] = "tailscale_acl_deny"
        new_record["message"] = record["message"] or "Tailscale ACL deny: unauthorized cross-cluster access attempt"
        new_record["userId"] = record["user_id"]
        new_record["metadata"]["src"] = record["src"]
        new_record["metadata"]["dst"] = record["dst"]
        new_record["metadata"]["action"] = "DENY"

    else
        new_record["category"] = "INFRASTRUCTURE"
        new_record["severity"] = "INFO"
        new_record["eventType"] = "system_event"
        new_record["message"] = record["message"] or "Generic boundary event"
    end

    new_record["clusterOrSubnet"] = "10.0.0.0/16"
    new_record["metadata"]["environment"] = "Local K3s"
    new_record["metadata"]["clusterId"] = "k3s-lab-edge"

    return 2, timestamp, new_record
end

function cb_transform_journal(tag, timestamp, record)
    local new_record = {}
    local now_iso = os.date("!%Y-%m-%dT%H:%M:%SZ")
    local msg = record["MESSAGE"] or ""

    new_record["timestamp"] = now_iso
    new_record["source"] = record["_SYSTEMD_UNIT"] or record["SYSLOG_IDENTIFIER"] or "systemd-kernel"
    new_record["metadata"] = {}

    if string.find(string.lower(msg), "oom") or string.find(string.lower(msg), "out of memory") then
        new_record["category"] = "CONTAINER"
        new_record["severity"] = "CRITICAL"
        new_record["eventType"] = "oom_killed"
        new_record["message"] = "Process or container invoked OOM-killer due to memory starvation"
        new_record["metadata"]["rawKernelMessage"] = msg
    elseif string.find(string.lower(msg), "panic") or string.find(string.lower(msg), "segfault") then
        new_record["category"] = "INFRASTRUCTURE"
        new_record["severity"] = "CRITICAL"
        new_record["eventType"] = "node_crash"
        new_record["message"] = "Kernel panic or fatal hardware fault detected on host"
        new_record["metadata"]["rawKernelMessage"] = msg
    else
        new_record["category"] = "INFRASTRUCTURE"
        new_record["severity"] = "ERROR"
        new_record["eventType"] = "service_failure"
        new_record["message"] = string.format("Systemd unit failed or stopped unexpectedly: %s", msg)
    end

    new_record["clusterOrSubnet"] = "10.0.0.0/16"
    new_record["metadata"]["environment"] = "Local K3s"
    new_record["metadata"]["clusterId"] = "k3s-lab-edge"

    return 2, timestamp, new_record
end

