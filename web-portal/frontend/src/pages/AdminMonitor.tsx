/**
 * AdminMonitor Page
 * SIEM Observability Workspace powered by Grafana, VictoriaLogs, and AWS S3.
 */
import { useState } from 'react';
import {
  BarChart3,
  ChevronRight,
  ExternalLink,
  LayoutDashboard,
  RefreshCw,
} from 'lucide-react';

const GRAFANA_VISUAL_ANALYTICS_URL =
  'http://100.69.137.47:30300/d/vlab-siem-analytics?orgId=1&kiosk';
const GRAFANA_COMMAND_CENTER_URL =
  import.meta.env.VITE_SIEM_GRAFANA_URL ||
  'http://100.69.137.47:30300/d/vlab-siem-5layer?orgId=1&kiosk';
const VICTORIALOGS_UI_URL =
  import.meta.env.VITE_SIEM_VICTORIALOGS_URL ||
  'http://100.69.137.47:30428/select/vmui';
const S3_EXPLORER_URL =
  import.meta.env.VITE_SIEM_S3_EXPLORER_URL ||
  'http://100.69.137.47:30900';

export default function AdminMonitorPage() {
  // Graphs tab ('analytics') is first and default
  const [activeDashboard, setActiveDashboard] = useState<'analytics' | 'command'>('analytics');
  const [iframeKey, setIframeKey] = useState<number>(0);

  const handleReloadGrafana = () => {
    setIframeKey((prev) => prev + 1);
  };

  const currentGrafanaUrl =
    activeDashboard === 'analytics'
      ? GRAFANA_VISUAL_ANALYTICS_URL
      : GRAFANA_COMMAND_CENTER_URL;

  const currentFullTabUrl =
    activeDashboard === 'analytics'
      ? 'http://100.69.137.47:30300/d/vlab-siem-analytics?orgId=1'
      : 'http://100.69.137.47:30300/d/vlab-siem-5layer?orgId=1';

  return (
    <div className="flex h-[calc(100vh-56px)] w-full flex-col bg-[#111217] text-white overflow-hidden">
      {/* Unified Dark Toolbar blending seamlessly with Navigation (#0B0B0B) and Grafana (#111217) */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 bg-[#111217] px-6 py-2.5 shrink-0">
        <div className="flex flex-wrap items-center gap-5">
          <div>
            <div className="flex items-center gap-1.5 text-xs text-white/45">
              <span>Admin workspace</span>
              <ChevronRight size={13} />
              <span className="font-medium text-white/75">SIEM Monitoring</span>
              <span className="ml-1 rounded border border-white/15 bg-white/[0.04] px-1.5 py-0.5 text-[11px] font-medium text-white/65">
                [🔒 READ-ONLY MODE]
              </span>
            </div>
            <h1 className="mt-0.5 text-base font-semibold tracking-tight text-white">
              Admin Monitor & SIEM Dashboard
            </h1>
          </div>

          {/* Unified Dark Tab Navigation */}
          <div className="flex gap-1 rounded-lg border border-white/10 bg-[#0B0B0B] p-1">
            <button
              type="button"
              onClick={() => setActiveDashboard('analytics')}
              className={`inline-flex h-8 items-center gap-2 rounded-md px-3.5 text-xs font-medium transition cursor-pointer ${
                activeDashboard === 'analytics'
                  ? 'bg-white/15 text-white shadow-sm'
                  : 'text-white/55 hover:bg-white/[0.05] hover:text-white/90'
              }`}
            >
              <BarChart3 size={14} />
              <span>Threat Analytics & Charts</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveDashboard('command')}
              className={`inline-flex h-8 items-center gap-2 rounded-md px-3.5 text-xs font-medium transition cursor-pointer ${
                activeDashboard === 'command'
                  ? 'bg-white/15 text-white shadow-sm'
                  : 'text-white/55 hover:bg-white/[0.05] hover:text-white/90'
              }`}
            >
              <LayoutDashboard size={14} />
              <span>SIEM Command Center</span>
            </button>
          </div>
        </div>

        {/* Clean Dark Action Links */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            onClick={handleReloadGrafana}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.04] px-3 font-medium text-white/80 hover:bg-white/10 hover:text-white transition cursor-pointer"
          >
            <RefreshCw size={13} />
            <span>Refresh</span>
          </button>

          <a
            href={VICTORIALOGS_UI_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.04] px-3 font-medium text-white/80 hover:bg-white/10 hover:text-white transition"
          >
            <span>VictoriaLogs</span>
            <ExternalLink size={12} className="text-white/40" />
          </a>

          <a
            href={S3_EXPLORER_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.04] px-3 font-medium text-white/80 hover:bg-white/10 hover:text-white transition"
          >
            <span>S3 Cold Storage</span>
            <ExternalLink size={12} className="text-white/40" />
          </a>

          <a
            href={currentFullTabUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-white/20 bg-white/15 px-3.5 font-medium text-white hover:bg-white/25 transition"
          >
            <span>Open in Grafana</span>
            <ExternalLink size={12} />
          </a>
        </div>
      </div>

      {/* Full-Screen Grafana SIEM View */}
      <div className="relative flex-1 w-full bg-[#111217]">
        <iframe
          key={`${activeDashboard}-${iframeKey}`}
          data-testid="grafana-siem-fullscreen-iframe"
          title="Grafana SIEM Dashboard"
          src={currentGrafanaUrl}
          className="h-full w-full border-0"
        />
      </div>
    </div>
  );
}
