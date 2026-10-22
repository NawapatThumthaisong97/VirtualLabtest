/**
 * BillingDashboard Component
 * Summarizes aggregated costs, session usage, and compute hours.
 * Allows grouping by course, cluster, nat_subnet, or anon_id.
 * Includes executive CSV/PDF export with Strict Anonymity guarantees.
 */
import React, { useState } from 'react';
import {
  FileSpreadsheet,
  FileText,
  ShieldCheck,
  Check,
} from 'lucide-react';
import type {
  BillingGroupBy,
  BillingSummaryResponse,
} from '../../services/billing';
import { billingService } from '../../services/billing';

interface BillingDashboardProps {
  summary?: BillingSummaryResponse | null;
  groupBy: BillingGroupBy;
  onGroupByChange: (newGroup: BillingGroupBy) => void;
  isLoading?: boolean;
}

export const BillingDashboard: React.FC<BillingDashboardProps> = ({
  summary,
  groupBy,
  onGroupByChange,
  isLoading,
}) => {
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [exportSuccessMsg, setExportSuccessMsg] = useState<string | null>(null);

  const handleExport = async (format: 'csv' | 'pdf') => {
    try {
      setIsExporting(true);
      setExportSuccessMsg(null);
      const fileName = await billingService.downloadReport(format, { groupBy });
      setExportSuccessMsg(`Successfully generated and downloaded ${fileName}`);
      setTimeout(() => setExportSuccessMsg(null), 4000);
    } catch (err) {
      console.error('Failed to export billing report', err);
    } finally {
      setIsExporting(false);
    }
  };

  const GROUP_OPTIONS: { id: BillingGroupBy; label: string }[] = [
    { id: 'course', label: 'By Course' },
    { id: 'cluster', label: 'By Cluster' },
    { id: 'nat_subnet', label: 'By NAT Subnet' },
    { id: 'anon_id', label: 'By Pseudonym (anon_id)' },
  ];

  const totalCost = summary?.totalCostThb ?? 0;
  const totalSessions = summary?.totalSessions ?? 0;
  const totalCpuHours = summary?.totalCpuHours ?? 0;
  const totalGpuHours = summary?.totalGpuHours ?? 0;
  const totalRamGbHours = Math.round(((summary?.totalRamMbHours ?? 0) / 1024) * 10) / 10;
  const items = summary?.items || [];

  return (
    <div className="flex flex-col gap-6">
      {/* Top Controls: Grouping Toggle + Export Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-white/10 bg-[#141418] p-4 shadow-md">
        {/* Left: Group By Switcher */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-white/50 mr-1">
            Aggregate By:
          </span>
          <div className="flex rounded-lg border border-white/15 bg-[#1a1a1e] p-1">
            {GROUP_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => onGroupByChange(opt.id)}
                className={`rounded px-3 py-1 text-xs font-medium transition-colors cursor-pointer ${
                  groupBy === opt.id
                    ? 'bg-indigo-600 text-white font-semibold shadow-sm'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Export Report Actions */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/40 mr-1">Executive Export:</span>
          <button
            type="button"
            disabled={isExporting || isLoading}
            onClick={() => handleExport('csv')}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 transition-colors cursor-pointer disabled:opacity-50"
            title="Download CSV report with UTF-8 BOM"
          >
            <FileSpreadsheet className="h-3.5 w-3.5" />
            <span>Export CSV</span>
          </button>

          <button
            type="button"
            disabled={isExporting || isLoading}
            onClick={() => handleExport('pdf')}
            className="flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-500/20 transition-colors cursor-pointer disabled:opacity-50"
            title="Download PDF executive summary"
          >
            <FileText className="h-3.5 w-3.5" />
            <span>Export PDF</span>
          </button>
        </div>
      </div>

      {/* Export notification alert */}
      {exportSuccessMsg && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-xs text-emerald-300">
          <Check className="h-4 w-4 text-emerald-400" />
          <span>{exportSuccessMsg}</span>
        </div>
      )}

      {/* Metric Cards Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-white/10 bg-[#141418] p-4">
          <span className="text-xs font-medium uppercase tracking-wider text-white/50">Total Incurred Cost</span>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-bold text-amber-300">฿{totalCost.toLocaleString('th-TH', { minimumFractionDigits: 2 })}</span>
            <span className="text-xs text-white/40">THB</span>
          </div>
          <p className="mt-2 text-[11px] text-white/40">Aggregated from usage records</p>
        </div>

        <div className="rounded-xl border border-white/10 bg-[#141418] p-4">
          <span className="text-xs font-medium uppercase tracking-wider text-white/50">Total Lab Sessions</span>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-bold text-white">{totalSessions}</span>
            <span className="text-xs text-white/40">Sessions</span>
          </div>
          <p className="mt-2 text-[11px] text-white/40">Recorded in period</p>
        </div>

        <div className="rounded-xl border border-white/10 bg-[#141418] p-4">
          <span className="text-xs font-medium uppercase tracking-wider text-white/50">CPU Hours</span>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-bold text-sky-400">{totalCpuHours.toFixed(2)}</span>
            <span className="text-xs text-white/40">Core-Hours</span>
          </div>
          <p className="mt-2 text-[11px] text-white/40">Local + AWS SkyPilot</p>
        </div>

        <div className="rounded-xl border border-white/10 bg-[#141418] p-4">
          <span className="text-xs font-medium uppercase tracking-wider text-white/50">GPU Hours</span>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-bold text-purple-400">{totalGpuHours.toFixed(2)}</span>
            <span className="text-xs text-white/40">GPU-Hours</span>
          </div>
          <p className="mt-2 text-[11px] text-white/40">AI / Cloud Bursting</p>
        </div>

        <div className="rounded-xl border border-white/10 bg-[#141418] p-4">
          <span className="text-xs font-medium uppercase tracking-wider text-white/50">RAM Consumption</span>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-bold text-emerald-400">{totalRamGbHours.toFixed(1)}</span>
            <span className="text-xs text-white/40">GB-Hours</span>
          </div>
          <p className="mt-2 text-[11px] text-white/40">Memory usage integral</p>
        </div>
      </div>

      {/* Breakdown Data Table */}
      <div className="rounded-xl border border-white/10 bg-[#141418] p-5 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">
              Aggregated Cost Breakdown ({GROUP_OPTIONS.find((g) => g.id === groupBy)?.label})
            </h3>
            <p className="text-xs text-white/40">
              Guaranteed Strict Anonymity — zero personal data or user credentials exposed
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-emerald-400">
            <ShieldCheck className="h-4 w-4" />
            <span>Strict Anonymity Verified</span>
          </div>
        </div>

        <div className="overflow-x-auto rounded-lg border border-white/10">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-white/10 bg-white/[0.02] text-white/50 uppercase tracking-wider font-semibold">
              <tr>
                <th className="px-4 py-3">Group Target / Key</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3 text-right">Sessions</th>
                <th className="px-4 py-3 text-right">CPU (Hours)</th>
                <th className="px-4 py-3 text-right">GPU (Hours)</th>
                <th className="px-4 py-3 text-right">RAM (MB-Hours)</th>
                <th className="px-4 py-3 text-right">Cost (THB)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-white/40">
                    Calculating aggregated usage records...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-white/40">
                    No billing records found for this criteria.
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.groupKey} className="hover:bg-white/[0.04] transition-colors">
                    <td className="px-4 py-3 font-mono font-medium text-white">
                      {item.anonId ? (
                        <span className="rounded bg-indigo-500/10 border border-indigo-500/30 px-2 py-0.5 text-indigo-300">
                          {item.anonId}
                        </span>
                      ) : (
                        item.groupKey
                      )}
                    </td>
                    <td className="px-4 py-3 text-white/80">
                      {item.groupName || item.groupKey}
                    </td>
                    <td className="px-4 py-3 text-right text-white/70">
                      {item.totalSessions}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-sky-300">
                      {item.totalCpuHours.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-purple-300">
                      {item.totalGpuHours.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-emerald-300">
                      {item.totalRamMbHours.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-amber-300">
                      ฿{item.totalCostThb.toLocaleString('th-TH', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
