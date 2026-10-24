/**
 * AdminMonitor Page — Full-Screen Grafana 5-Layer SIEM Command Center & Visual Threat Analytics
 * Replaces legacy monitor tabs with 2 full-screen Grafana SIEM views:
 * - Tab 1: SIEM Command Center (SOC Overview, Fast-Track, MITRE, GeoIP, Live Logs)
 * - Tab 2: Visual Threat Analytics (Gauge, Donut Chart, Pie Chart, LCD Bar Gauge, Stacked Area Time-Series, Node Bar Chart)
 */
import { useState } from 'react';
import {
  BarChart3,
  Database,
  ExternalLink,
  HardDrive,
  Lock,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';

const GRAFANA_COMMAND_CENTER_URL =
  import.meta.env.VITE_SIEM_GRAFANA_URL ||
  'http://100.69.137.47:30300/d/vlab-siem-5layer?orgId=1&kiosk';
const GRAFANA_VISUAL_ANALYTICS_URL =
  'http://100.69.137.47:30300/d/vlab-siem-analytics?orgId=1&kiosk';
const VICTORIALOGS_UI_URL =
  import.meta.env.VITE_SIEM_VICTORIALOGS_URL ||
  'http://100.69.137.47:30428/select/vmui';
const S3_EXPLORER_URL =
  import.meta.env.VITE_SIEM_S3_EXPLORER_URL ||
  'http://100.69.137.47:30900';

export default function AdminMonitorPage() {
  const [activeDashboard, setActiveDashboard] = useState<'command' | 'analytics'>('command');
  const [iframeKey, setIframeKey] = useState<number>(0);

  const handleReloadGrafana = () => {
    setIframeKey((prev) => prev + 1);
  };

  const currentGrafanaUrl =
    activeDashboard === 'command'
      ? GRAFANA_COMMAND_CENTER_URL
      : GRAFANA_VISUAL_ANALYTICS_URL;

  const currentFullTabUrl =
    activeDashboard === 'command'
      ? 'http://100.69.137.47:30300/d/vlab-siem-5layer?orgId=1'
      : 'http://100.69.137.47:30300/d/vlab-siem-analytics?orgId=1';

  return (
    <div className="flex h-screen w-full flex-col bg-[#0a0a0d] text-white overflow-hidden">
      {/* Compact Full-Screen SIEM Header Bar */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-[#111217] px-4 py-2 shrink-0">
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

          {/* Dashboard View Switcher Tabs */}
          <div className="flex items-center rounded-lg border border-white/10 bg-black/40 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setActiveDashboard('command')}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-semibold transition cursor-pointer ${
                activeDashboard === 'command'
                  ? 'bg-emerald-600 text-white shadow'
                  : 'text-white/60 hover:text-white'
              }`}
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>SIEM Command Center</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveDashboard('analytics')}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-semibold transition cursor-pointer ${
                activeDashboard === 'analytics'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-white/60 hover:text-white'
              }`}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              <span>Visual Threat Analytics (Graphs)</span>
            </button>
          </div>

          <div className="hidden 2xl:flex items-center gap-1 text-[10px] text-white/60">
            <span className="rounded bg-white/5 px-1.5 py-0.5 border border-white/10">
              L1: Vector + Falco eBPF
            </span>
            <span className="rounded bg-white/5 px-1.5 py-0.5 border border-white/10">
              L2: NATS JetStream + KV
            </span>
            <span className="rounded bg-white/5 px-1.5 py-0.5 border border-white/10">
              L3: ECS + GeoIP + Threat Intel
            </span>
            <span className="rounded bg-white/5 px-1.5 py-0.5 border border-white/10">
              L4: VictoriaLogs + AWS S3 (.parquet)
            </span>
            <span className="rounded bg-emerald-500/15 text-emerald-300 px-1.5 py-0.5 border border-emerald-500/30 font-semibold">
              L5: Grafana + Sigma + Fast-Track
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <div className="hidden lg:flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-white/60">
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
            href={currentFullTabUrl}
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
          key={`${activeDashboard}-${iframeKey}`}
          data-testid="grafana-siem-fullscreen-iframe"
          title="Grafana 5-Layer SIEM Command Center"
          src={currentGrafanaUrl}
          className="h-full w-full border-0"
        />
      </main>
    </div>
  );
}
