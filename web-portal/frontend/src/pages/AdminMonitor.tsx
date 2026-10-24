/**
 * AdminMonitor Page — Full-Screen Grafana 5-Layer SIEM Command Center
 * Replaces legacy monitor tabs with a dedicated full-screen Grafana SIEM view:
 * - Layer 1: Collector (Vector Agent + Falco eBPF over Tailscale)
 * - Layer 2: Buffer (NATS JetStream StatefulSet + KV Store)
 * - Layer 3: Processing (Vector Aggregator VRL -> ECS v8.11.0 + GeoIP + Threat Intel)
 * - Layer 4: Storage (VictoriaLogs 14d Hot Storage + AWS S3 .parquet 90d-365d Cold Storage)
 * - Layer 5: Detection & Visualization (Grafana + Sigma Rules LogsQL CronJob + Falco Fast-Track)
 */
import { useState } from 'react';
import {
  ExternalLink,
  Lock,
  RefreshCw,
  ShieldAlert,
  Database,
  HardDrive,
} from 'lucide-react';

const GRAFANA_DASHBOARD_URL =
  import.meta.env.VITE_SIEM_GRAFANA_URL ||
  'http://100.69.137.47:30300/d/vlab-siem-5layer?orgId=1&kiosk';
const GRAFANA_FULL_URL =
  'http://100.69.137.47:30300/d/vlab-siem-5layer?orgId=1';
const VICTORIALOGS_UI_URL =
  import.meta.env.VITE_SIEM_VICTORIALOGS_URL ||
  'http://100.69.137.47:30428/select/vmui';
const S3_EXPLORER_URL =
  import.meta.env.VITE_SIEM_S3_EXPLORER_URL ||
  'http://100.69.137.47:30900';

export default function AdminMonitorPage() {
  const [iframeKey, setIframeKey] = useState<number>(0);

  const handleReloadGrafana = () => {
    setIframeKey((prev) => prev + 1);
  };

  return (
    <div className="flex h-screen w-full flex-col bg-[#0a0a0d] text-white overflow-hidden">
      {/* Compact Full-Screen SIEM Header Bar */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-[#111217] px-4 py-2.5 shrink-0">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-emerald-400" />
            <h1 className="text-base font-bold tracking-tight text-white">
              Admin Monitor & SIEM Dashboard
            </h1>
          </div>

          <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-amber-300">
            [🔒 READ-ONLY MODE]
          </span>

          <div className="hidden xl:flex items-center gap-1.5 text-[11px] text-white/70">
            <span className="rounded bg-white/5 px-2 py-0.5 border border-white/10">
              L1: Vector + Falco eBPF
            </span>
            <span>&rarr;</span>
            <span className="rounded bg-white/5 px-2 py-0.5 border border-white/10">
              L2: NATS JetStream + KV
            </span>
            <span>&rarr;</span>
            <span className="rounded bg-white/5 px-2 py-0.5 border border-white/10">
              L3: ECS + GeoIP + Threat Intel
            </span>
            <span>&rarr;</span>
            <span className="rounded bg-white/5 px-2 py-0.5 border border-white/10">
              L4: VictoriaLogs + AWS S3 (.parquet)
            </span>
            <span>&rarr;</span>
            <span className="rounded bg-emerald-500/15 text-emerald-300 px-2 py-0.5 border border-emerald-500/30 font-semibold">
              L5: Grafana + Sigma + Fast-Track
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <div className="hidden md:flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-white/60">
            <Lock className="h-3 w-3 text-amber-400" />
            <span>Strict View-Only</span>
          </div>

          <button
            type="button"
            onClick={handleReloadGrafana}
            className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 hover:bg-white/10 px-2.5 py-1 text-xs font-medium text-white transition cursor-pointer"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Refresh SIEM</span>
          </button>

          <a
            href={VICTORIALOGS_UI_URL}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-lg border border-sky-500/40 bg-sky-500/10 hover:bg-sky-500/20 px-2.5 py-1 text-xs font-semibold text-sky-300 transition"
          >
            <Database className="h-3.5 w-3.5" />
            <span>VictoriaLogs (LogsQL)</span>
            <ExternalLink className="h-3 w-3" />
          </a>

          <a
            href={S3_EXPLORER_URL}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-lg border border-indigo-500/40 bg-indigo-500/10 hover:bg-indigo-500/20 px-2.5 py-1 text-xs font-semibold text-indigo-300 transition"
          >
            <HardDrive className="h-3.5 w-3.5" />
            <span>AWS S3 (.parquet)</span>
            <ExternalLink className="h-3 w-3" />
          </a>

          <a
            href={GRAFANA_FULL_URL}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3 py-1 text-xs font-semibold text-white transition"
          >
            <span>Open Grafana Tab</span>
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </header>

      {/* Full-Screen Embedded Grafana 5-Layer SIEM Dashboard */}
      <main className="relative flex-1 w-full bg-[#111217]">
        <iframe
          key={iframeKey}
          data-testid="grafana-siem-fullscreen-iframe"
          title="Grafana 5-Layer SIEM Command Center"
          src={GRAFANA_DASHBOARD_URL}
          className="h-full w-full border-0"
        />
      </main>
    </div>
  );
}
