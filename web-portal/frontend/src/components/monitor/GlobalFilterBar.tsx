/**
 * GlobalFilterBar Component
 * Global control bar synchronized with URL Query Parameters.
 * Includes Environment, NAT Zone, Time Range, and Anon ID filters,
 * plus the mandatory [🔒 READ-ONLY MODE] badge.
 */
import React from 'react';
import { Lock, RefreshCw, Search, X, ShieldAlert, Globe } from 'lucide-react';

export interface GlobalFilters {
  provider: 'all' | 'aws' | 'local';
  natSubnet: string;
  timeRange: '1h' | '6h' | '24h' | '7d' | '30d';
  anonId: string;
}

interface GlobalFilterBarProps {
  filters: GlobalFilters;
  onChange: (next: Partial<GlobalFilters>) => void;
  onRefresh: () => void;
  isLoading?: boolean;
}

const NAT_SUBNETS = [
  { value: 'all', label: 'All NAT Zones' },
  { value: '10.0.0.0/16', label: 'AWS Cloud (10.0.0.0/16)' },
  { value: '192.168.1.0/24', label: 'Room 1 (192.168.1.0/24)' },
  { value: '192.168.2.0/24', label: 'Room 2 (192.168.2.0/24)' },
  { value: '192.168.3.0/24', label: 'Room 3 (192.168.3.0/24)' },
];

export const GlobalFilterBar: React.FC<GlobalFilterBarProps> = ({
  filters,
  onChange,
  onRefresh,
  isLoading,
}) => {
  return (
    <div className="w-full rounded-xl border border-white/10 bg-[#121214] p-4 shadow-lg backdrop-blur-md">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left: Title & Read-Only Badge */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-indigo-400" />
            <span className="font-semibold text-white tracking-wide">Infrastructure & Security Observability</span>
          </div>

          <div
            className="flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.2)]"
            title="UI operates strictly in Read-Only / View-Only mode. Destructive actions must be executed via Bastion Host."
          >
            <Lock className="h-3.5 w-3.5 text-amber-400" />
            <span>[🔒 READ-ONLY MODE]</span>
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            disabled={isLoading}
            className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-medium text-white/80 hover:bg-white/10 hover:text-white transition-colors cursor-pointer disabled:opacity-50"
            title="Refresh dashboard metrics and logs"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Filter Controls Row */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Environment Filter */}
        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium uppercase tracking-wider text-white/50">
            Environment
          </label>
          <select
            value={filters.provider}
            onChange={(e) => onChange({ provider: e.target.value as GlobalFilters['provider'] })}
            className="w-full rounded-lg border border-white/15 bg-[#1a1a1e] px-3 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none cursor-pointer"
          >
            <option value="all">All Environments (Cloud + K3s)</option>
            <option value="aws">AWS SkyPilot (Cloud)</option>
            <option value="local">Local K3s (Physical Cluster)</option>
          </select>
        </div>

        {/* NAT Subnet Filter */}
        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium uppercase tracking-wider text-white/50">
            NAT Zone / Subnet
          </label>
          <select
            value={filters.natSubnet}
            onChange={(e) => onChange({ natSubnet: e.target.value })}
            className="w-full rounded-lg border border-white/15 bg-[#1a1a1e] px-3 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none cursor-pointer"
          >
            {NAT_SUBNETS.map((sub) => (
              <option key={sub.value} value={sub.value}>
                {sub.label}
              </option>
            ))}
          </select>
        </div>

        {/* Time Range */}
        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium uppercase tracking-wider text-white/50">
            Time Range
          </label>
          <div className="grid grid-cols-5 gap-1 rounded-lg border border-white/15 bg-[#1a1a1e] p-1">
            {(['1h', '6h', '24h', '7d', '30d'] as const).map((range) => (
              <button
                key={range}
                type="button"
                onClick={() => onChange({ timeRange: range })}
                className={`rounded py-1 text-center text-xs font-medium transition-colors cursor-pointer ${
                  filters.timeRange === range
                    ? 'bg-indigo-600 text-white font-semibold shadow-sm'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                {range}
              </button>
            ))}
          </div>
        </div>

        {/* Anon ID Search & Correlation */}
        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium uppercase tracking-wider text-white/50">
            Correlate Pseudonym (anonId)
          </label>
          <div className="relative flex items-center">
            <Search className="absolute left-2.5 h-3.5 w-3.5 text-white/40" />
            <input
              type="text"
              placeholder="e.g. anon_8f92a1b7"
              value={filters.anonId}
              onChange={(e) => onChange({ anonId: e.target.value.trim() })}
              className="w-full rounded-lg border border-white/15 bg-[#1a1a1e] py-1.5 pl-8 pr-7 text-xs text-white placeholder-white/30 focus:border-indigo-500 focus:outline-none"
            />
            {filters.anonId && (
              <button
                type="button"
                onClick={() => onChange({ anonId: '' })}
                className="absolute right-2 text-white/40 hover:text-white cursor-pointer"
                title="Clear anonId filter"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Active Correlation Notice */}
      {filters.anonId && (
        <div className="mt-3 flex items-center justify-between rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-1.5 text-xs text-indigo-300">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-indigo-400" />
            <span>
              Correlating events for user pseudonym: <strong>{filters.anonId}</strong>
            </span>
          </div>
          <button
            type="button"
            onClick={() => onChange({ anonId: '' })}
            className="text-[11px] font-medium text-indigo-300 hover:text-white underline cursor-pointer"
          >
            Reset Filter
          </button>
        </div>
      )}
    </div>
  );
};
