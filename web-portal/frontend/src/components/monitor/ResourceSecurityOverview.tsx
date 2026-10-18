/**
 * ResourceSecurityOverview Component
 * Visualizes cluster CPU, RAM, Active Sessions alongside Security Violation Counters
 * (Squid Proxy Egress Drops, Kyverno Policy Blocks, Tailscale Denies).
 */
import React from 'react';
import {
  Cpu,
  Database,
  Activity,
  ShieldCheck,
  ShieldAlert,
  Server,
  Cloud,
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from 'recharts';
import type { MetricsResponseData, SecurityCountersData } from '../../services/monitor';

interface ResourceSecurityOverviewProps {
  metrics?: MetricsResponseData | null;
  securityCounters?: SecurityCountersData | null;
  isLoading?: boolean;
}

export const ResourceSecurityOverview: React.FC<ResourceSecurityOverviewProps> = ({
  metrics,
  securityCounters,
  isLoading,
}) => {
  const summary = metrics?.summary || {
    totalCpuAllocated: 0,
    totalCpuLimit: 1,
    totalRamAllocatedMb: 0,
    totalRamLimitMb: 1,
    activeSessions: 0,
    clusterCount: 0,
  };

  const cpuPct = Math.min(
    100,
    Math.round((summary.totalCpuAllocated / Math.max(1, summary.totalCpuLimit)) * 100)
  );
  const ramPct = Math.min(
    100,
    Math.round((summary.totalRamAllocatedMb / Math.max(1, summary.totalRamLimitMb)) * 100)
  );

  const security = securityCounters || {
    squidEgressDrops: 0,
    squidEgressAllowed: 0,
    kyvernoBlocks: 0,
    tailscaleDenies: 0,
    totalViolations: 0,
  };

  // Prepare chart data
  const timeSeries = (metrics?.timeSeries || []).map((pt) => ({
    time: pt.timestamp ? new Date(pt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '',
    cpu: pt.cpuAllocated,
    ramGb: Math.round((pt.ramAllocatedMb / 1024) * 10) / 10,
    sessions: pt.activeSessions,
    violations: pt.violationsCount,
  }));

  const securityBarData = [
    {
      category: 'Squid Egress',
      Allowed: security.squidEgressAllowed,
      Blocked: security.squidEgressDrops,
    },
    {
      category: 'Kyverno Policy',
      Allowed: 0,
      Blocked: security.kyvernoBlocks,
    },
    {
      category: 'Tailscale Mesh',
      Allowed: 0,
      Blocked: security.tailscaleDenies,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* CPU Allocation Card */}
        <div className="rounded-xl border border-white/10 bg-[#141418] p-4 shadow-md">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-white/50">CPU Allocation</span>
            <Cpu className="h-4 w-4 text-sky-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">{summary.totalCpuAllocated}</span>
            <span className="text-xs text-white/40">/ {summary.totalCpuLimit} Cores</span>
            <span className="ml-auto text-xs font-semibold text-sky-400">{cpuPct}%</span>
          </div>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                cpuPct > 85 ? 'bg-red-500' : cpuPct > 70 ? 'bg-amber-400' : 'bg-sky-400'
              }`}
              style={{ width: `${cpuPct}%` }}
            />
          </div>
        </div>

        {/* RAM Allocation Card */}
        <div className="rounded-xl border border-white/10 bg-[#141418] p-4 shadow-md">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-white/50">RAM Allocation</span>
            <Database className="h-4 w-4 text-purple-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">
              {(summary.totalRamAllocatedMb / 1024).toFixed(1)}
            </span>
            <span className="text-xs text-white/40">/ {(summary.totalRamLimitMb / 1024).toFixed(1)} GB</span>
            <span className="ml-auto text-xs font-semibold text-purple-400">{ramPct}%</span>
          </div>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                ramPct > 85 ? 'bg-red-500' : ramPct > 70 ? 'bg-amber-400' : 'bg-purple-400'
              }`}
              style={{ width: `${ramPct}%` }}
            />
          </div>
        </div>

        {/* Active Sessions Card */}
        <div className="rounded-xl border border-white/10 bg-[#141418] p-4 shadow-md">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-white/50">Active Sessions</span>
            <Activity className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">{summary.activeSessions}</span>
            <span className="text-xs text-emerald-400">Live Pods</span>
          </div>
          <p className="mt-3 text-[11px] text-white/40">
            Across {summary.clusterCount} cluster zones (AWS + K3s)
          </p>
        </div>

        {/* Security Violation Counters Card */}
        <div className="rounded-xl border border-rose-500/20 bg-[#1a1215] p-4 shadow-md">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-rose-300">
              Security Boundary Denies
            </span>
            <ShieldAlert className="h-4 w-4 text-rose-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-rose-200">{security.totalViolations}</span>
            <span className="text-xs text-rose-400">Total Dropped</span>
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-white/60">
            <span>Squid: {security.squidEgressDrops}</span>
            <span>Kyverno: {security.kyvernoBlocks}</span>
            <span>Tailscale: {security.tailscaleDenies}</span>
          </div>
        </div>
      </div>

      {/* Provider Details Row */}
      {metrics?.byProvider && metrics.byProvider.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {metrics.byProvider.map((prov) => (
            <div
              key={prov.provider}
              className="flex items-center justify-between rounded-xl border border-white/10 bg-[#141418] p-4"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/5">
                  {prov.isCloud ? (
                    <Cloud className="h-5 w-5 text-indigo-400" />
                  ) : (
                    <Server className="h-5 w-5 text-emerald-400" />
                  )}
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-white">{prov.provider}</h4>
                  <p className="text-xs text-white/50">Subnet: {prov.natSubnet || 'Default NAT'}</p>
                </div>
              </div>

              <div className="flex items-center gap-6 text-right">
                <div>
                  <p className="text-xs text-white/40">CPU / RAM</p>
                  <p className="text-xs font-semibold text-white">
                    {prov.cpuAllocated}c / {(prov.ramAllocatedMb / 1024).toFixed(1)}GB
                  </p>
                </div>
                <div>
                  <p className="text-xs text-white/40">Active</p>
                  <p className="text-xs font-semibold text-emerald-400">{prov.activeSessions} Pods</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Visual Charts Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Resource Allocation Time Series */}
        <div className="rounded-xl border border-white/10 bg-[#141418] p-5 shadow-lg">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Resource Allocation & Activity Trends</h3>
              <p className="text-xs text-white/40">CPU (Cores) and Active Sessions over selected window</p>
            </div>
            <Activity className="h-4 w-4 text-white/40" />
          </div>

          <div className="h-64 w-full">
            {isLoading ? (
              <div className="flex h-full items-center justify-center text-xs text-white/40">
                Loading time-series metrics...
              </div>
            ) : timeSeries.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={timeSeries} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.0} />
                    </linearGradient>
                    <linearGradient id="sessionGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#34d399" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#34d399" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#26262a" />
                  <XAxis dataKey="time" stroke="#71717a" fontSize={11} />
                  <YAxis stroke="#71717a" fontSize={11} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#18181b',
                      borderColor: '#3f3f46',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                  <Area
                    type="monotone"
                    dataKey="cpu"
                    name="CPU Cores"
                    stroke="#38bdf8"
                    fillOpacity={1}
                    fill="url(#cpuGradient)"
                  />
                  <Area
                    type="monotone"
                    dataKey="sessions"
                    name="Active Pods"
                    stroke="#34d399"
                    fillOpacity={1}
                    fill="url(#sessionGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-white/40">
                No time-series data available for this range
              </div>
            )}
          </div>
        </div>

        {/* Security Boundary Violation Breakdown */}
        <div className="rounded-xl border border-white/10 bg-[#141418] p-5 shadow-lg">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Security Boundary Violations (Allowed vs Dropped)</h3>
              <p className="text-xs text-white/40">Enforced by Squid Egress Proxy, OPA/Kyverno & Tailscale</p>
            </div>
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
          </div>

          <div className="h-64 w-full">
            {isLoading ? (
              <div className="flex h-full items-center justify-center text-xs text-white/40">
                Loading security telemetry...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={securityBarData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#26262a" />
                  <XAxis dataKey="category" stroke="#71717a" fontSize={11} />
                  <YAxis stroke="#71717a" fontSize={11} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#18181b',
                      borderColor: '#3f3f46',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                  <Bar dataKey="Allowed" name="Allowed Traffic" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Blocked" name="Blocked / Denied" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
