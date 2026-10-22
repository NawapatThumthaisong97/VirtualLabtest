/**
 * Runbook Recommendation Engine
 * Generates copy-only CLI commands for Admin to inspect or remediate incidents
 * via Bastion Host terminal. The Web UI maintains a strict 100% Read-Only mode.
 */
import type { InfrastructureLog } from '../services/monitor';

export interface RunbookCommand {
  title: string;
  command: string;
  description: string;
}

export function getRunbookCommands(log: InfrastructureLog): RunbookCommand[] {
  const commands: RunbookCommand[] = [];
  const event = (log.eventType || '').toUpperCase();
  const category = (log.category || '').toUpperCase();
  const msg = (log.message || '').toLowerCase();

  // 1. Squid Proxy / Egress drops
  if (category.includes('EGRESS') || category.includes('SQUID') || event.includes('EGRESS') || msg.includes('squid')) {
    commands.push({
      title: 'Inspect Squid Proxy Access Logs',
      command: 'ssh admin@bastion.tu.ac.th "kubectl logs -n proxy -l app=squid-proxy --tail=200 | grep -E \'(TCP_DENIED|NONE/403)\'"',
      description: 'ตรวจสอบคำขอออกนอกเครือข่ายที่ถูก Drop หรือ Deny บน Squid Proxy',
    });
    commands.push({
      title: 'Verify Squid Allowlist ConfigMap',
      command: 'ssh admin@bastion.tu.ac.th "kubectl get configmap squid-allowlist -n proxy -o yaml"',
      description: 'ตรวจสอบรายชื่อ Domain allowlist ปัจจุบันของห้องแล็บ',
    });
  }

  // 2. Kyverno / OPA Policy Blocks
  if (category.includes('KYVERNO') || category.includes('POLICY') || event.includes('KYVERNO') || msg.includes('kyverno')) {
    commands.push({
      title: 'Inspect Kyverno Admission Reports',
      command: 'ssh admin@bastion.tu.ac.th "kubectl get policyreports -A -o wide"',
      description: 'ตรวจสอบ PolicyReport ในทุกลูปเนมสเปซที่มีการบล็อก Resource',
    });
    commands.push({
      title: 'Check Kyverno Controller Logs',
      command: 'ssh admin@bastion.tu.ac.th "kubectl logs -n kyverno -l app.kubernetes.io/name=kyverno --tail=100"',
      description: 'ตรวจสอบสาเหตุที่ Policy ปฏิเสธ Pod หรือ Service Configuration',
    });
  }

  // 3. Tailscale Denies / Cross-zone boundary
  if (category.includes('TAILSCALE') || event.includes('TAILSCALE') || msg.includes('tailscale')) {
    commands.push({
      title: 'Check Tailscale Mesh Status',
      command: 'ssh admin@bastion.tu.ac.th "tailscale status --peers=false && tailscale netcheck"',
      description: 'ตรวจสอบการเชื่อมต่อและสถานะของ Tailscale Node ในคลัสเตอร์',
    });
    commands.push({
      title: 'Inspect Tailscale ACL Audit Logs',
      command: 'ssh admin@bastion.tu.ac.th "tailscale ping --until-direct --timeout=5s 100.64.0.1"',
      description: 'ทดสอบเส้นทางข้าม Subnet ระหว่างห้องแล็บและคลาวด์',
    });
  }

  // 4. OOM Kill / Resource Exhaustion
  if (category.includes('OOM') || event.includes('OOM') || msg.includes('oom') || msg.includes('memory')) {
    commands.push({
      title: 'Identify OOMKilled Pods in Cluster',
      command: 'ssh admin@bastion.tu.ac.th "kubectl get pods -A -o jsonpath=\'{range .items[*]}{.metadata.namespace}{\"/\"}{.metadata.name}{\": \"}{.status.containerStatuses[*].lastState.terminated.reason}{\"\\n\"}{end}\' | grep -i OOMKilled"',
      description: 'ค้นหารายชื่อ Pod ในทุก Namespace ที่ถูกระบบ Kernel สั่งยุติเนื่องจากหน่วยความจำเต็ม',
    });
    commands.push({
      title: 'Check Node Memory Pressure',
      command: 'ssh admin@bastion.tu.ac.th "kubectl describe nodes | grep -E \'(MemoryPressure|Allocated resources)\' -A 6"',
      description: 'ตรวจสอบสถานะหน่วยความจำของโหนดทั้งหมดในคลัสเตอร์',
    });
  }

  // 5. SkyPilot Burst / Cloud Failures
  if (msg.includes('skypilot') || msg.includes('sky') || msg.includes('cloud') || event.includes('BURST')) {
    commands.push({
      title: 'Check SkyPilot Cluster Status',
      command: 'ssh admin@bastion.tu.ac.th "sky status --refresh && sky check"',
      description: 'ตรวจสอบความพร้อมและโควตาของ AWS EC2 / SkyPilot Instances',
    });
    commands.push({
      title: 'Inspect SkyPilot Job Logs',
      command: 'ssh admin@bastion.tu.ac.th "sky logs --all"',
      description: 'ดึง Log การสร้างเครื่องและ Task บน AWS SkyPilot',
    });
  }

  // Standard Fallback Diagnostic
  if (commands.length === 0) {
    commands.push({
      title: 'Inspect Unhealthy Pods',
      command: 'ssh admin@bastion.tu.ac.th "kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded"',
      description: 'ตรวจสอบรายชื่อ Pod ที่อยู่ในสถานะผิดปกติในคลัสเตอร์',
    });
    commands.push({
      title: 'Check Cluster Node Conditions',
      command: 'ssh admin@bastion.tu.ac.th "kubectl get nodes -o wide"',
      description: 'ตรวจสอบสถานะของ Node K3s และสถานะ Ready/NotReady',
    });
  }

  return commands;
}

