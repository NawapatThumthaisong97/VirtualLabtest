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
    <div className="flex h-[calc(100vh-56px)] w-full flex-col bg-[#f7f9fc] overflow-hidden">
      {/* Top Toolbar matching InstructorPage design language */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-3 shrink-0">
        <div className="flex flex-wrap items-center gap-5">
          <div>
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <span>Admin workspace</span>
              <ChevronRight size={13} />
              <span className="font-semibold text-slate-700">SIEM Monitoring</span>
              <span className="ml-1 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                [🔒 READ-ONLY MODE]
              </span>
            </div>
            <h1 className="mt-0.5 text-lg font-semibold tracking-tight text-slate-900">
              Admin Monitor & SIEM Dashboard
            </h1>
          </div>

          {/* Tab Navigation matching InstructorPage */}
          <div className="flex gap-1 rounded-xl border border-slate-200 bg-[#f7f9fc] p-1">
            <button
              type="button"
              onClick={() => setActiveDashboard('analytics')}
              className={`inline-flex h-8 items-center gap-2 rounded-lg px-3.5 text-xs font-semibold transition cursor-pointer ${
                activeDashboard === 'analytics'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-white hover:text-slate-900'
              }`}
            >
              <BarChart3 size={14} />
              <span>Threat Analytics & Charts</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveDashboard('command')}
              className={`inline-flex h-8 items-center gap-2 rounded-lg px-3.5 text-xs font-semibold transition cursor-pointer ${
                activeDashboard === 'command'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-white hover:text-slate-900'
              }`}
            >
              <LayoutDashboard size={14} />
              <span>SIEM Command Center</span>
            </button>
          </div>
        </div>

        {/* Clean Action Links */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            onClick={handleReloadGrafana}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 font-medium text-slate-700 hover:bg-slate-50 transition cursor-pointer"
          >
            <RefreshCw size={13} />
            <span>Refresh</span>
          </button>

          <a
            href={VICTORIALOGS_UI_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 font-medium text-slate-700 hover:bg-slate-50 transition"
          >
            <span>VictoriaLogs</span>
            <ExternalLink size={12} className="text-slate-400" />
          </a>

          <a
            href={S3_EXPLORER_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 font-medium text-slate-700 hover:bg-slate-50 transition"
          >
            <span>S3 Cold Storage</span>
            <ExternalLink size={12} className="text-slate-400" />
          </a>

          <a
            href={currentFullTabUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 font-semibold text-white hover:bg-blue-700 transition"
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
