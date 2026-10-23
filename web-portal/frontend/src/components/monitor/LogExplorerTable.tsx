/**
 * LogExplorerTable Component
 * Interactive table for Critical Infrastructure & Boundary Logs.
 * Supports filtering by severity, category, and anonId.
 * Includes Click-to-Correlate on anonId badges and opens Side Drawer on row click.
 */
import React, { useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Info,
  ChevronRight,
  Search,
  UserCheck,
} from 'lucide-react';
import type { InfrastructureLog, LogSeverity } from '../../services/monitor';

interface LogExplorerTableProps {
  logs: InfrastructureLog[];
  total: number;
  isLoading?: boolean;
  selectedSeverity: string;
  selectedCategory: string;
  onSeverityChange: (sev: string) => void;
  onCategoryChange: (cat: string) => void;
  onSelectLog: (log: InfrastructureLog) => void;
  onCorrelateAnonId: (anonId: string) => void;
  limit: number;
  offset: number;
  onPageChange: (newOffset: number) => void;
}

const SEVERITIES: { value: string; label: string }[] = [
  { value: 'ALL', label: 'All Severities' },
  { value: 'CRITICAL', label: 'Critical' },
  { value: 'ERROR', label: 'Error' },
  { value: 'WARNING', label: 'Warning' },
  { value: 'INFO', label: 'Info' },
];

const CATEGORIES: { value: string; label: string }[] = [
  { value: 'ALL', label: 'All Categories' },
  { value: 'SECURITY_VIOLATION', label: 'Security Violations' },
  { value: 'EGRESS_DROP', label: 'Squid Egress Drops' },
  { value: 'KYVERNO_BLOCK', label: 'Kyverno Policy Blocks' },
  { value: 'TAILSCALE_DENY', label: 'Tailscale Denies' },
  { value: 'INFRA_FAILURE', label: 'Infra Failures' },
  { value: 'OOM_KILL', label: 'OOM Kills' },
];

export const LogExplorerTable: React.FC<LogExplorerTableProps> = ({
  logs,
  total,
  isLoading,
  selectedSeverity,
  selectedCategory,
  onSeverityChange,
  onCategoryChange,
  onSelectLog,
  onCorrelateAnonId,
  limit,
  offset,
  onPageChange,
}) => {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredLogs = logs.filter((log) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      log.message.toLowerCase().includes(term) ||
      log.eventType.toLowerCase().includes(term) ||
      log.source.toLowerCase().includes(term) ||
      (log.anonId && log.anonId.toLowerCase().includes(term))
    );
  });

  const getSeverityBadge = (severity: LogSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center gap-1 rounded-md border border-red-500/40 bg-red-500/20 px-2 py-0.5 text-[10px] font-bold text-red-300">
            <AlertCircle className="h-3 w-3" />
            CRITICAL
          </span>
        );
      case 'ERROR':
        return (
          <span className="inline-flex items-center gap-1 rounded-md border border-rose-500/40 bg-rose-500/20 px-2 py-0.5 text-[10px] font-bold text-rose-300">
            <AlertCircle className="h-3 w-3" />
            ERROR
          </span>
        );
      case 'WARNING':
        return (
          <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300">
            <AlertTriangle className="h-3 w-3" />
            WARNING
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-md border border-sky-500/40 bg-sky-500/20 px-2 py-0.5 text-[10px] font-bold text-sky-300">
            <Info className="h-3 w-3" />
            INFO
          </span>
        );
    }
  };

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-white/10 bg-[#141418] p-5 shadow-lg">
      {/* Table Header & Local Filters */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-white">Critical Infrastructure & Security Boundary Logs</h3>
          <p className="text-xs text-white/40">
            Deterministic pseudonymization (HMAC-SHA256) with Zero PII leakage
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Severity Select */}
          <select
            value={selectedSeverity}
            onChange={(e) => onSeverityChange(e.target.value)}
            className="rounded-lg border border-white/15 bg-[#1a1a1e] px-2.5 py-1.5 text-xs text-white focus:outline-none cursor-pointer"
          >
            {SEVERITIES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>

          {/* Category Select */}
          <select
            value={selectedCategory}
            onChange={(e) => onCategoryChange(e.target.value)}
            className="rounded-lg border border-white/15 bg-[#1a1a1e] px-2.5 py-1.5 text-xs text-white focus:outline-none cursor-pointer"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>

          {/* Search in results */}
          <div className="relative">
            <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-white/40" />
            <input
              type="text"
              placeholder="Search message or type..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="rounded-lg border border-white/15 bg-[#1a1a1e] py-1.5 pl-8 pr-3 text-xs text-white placeholder-white/30 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Table Element */}
      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-white/10 bg-white/[0.02] text-white/50 uppercase tracking-wider font-semibold">
            <tr>
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">Severity</th>
              <th className="px-4 py-3">Category / Event</th>
              <th className="px-4 py-3">Message</th>
              <th className="px-4 py-3">Pseudonym (anonId)</th>
              <th className="px-4 py-3 text-right">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-white/40">
                  Loading boundary logs...
                </td>
              </tr>
            ) : filteredLogs.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-white/40">
                  No log records match current filters.
                </td>
              </tr>
            ) : (
              filteredLogs.map((log) => (
                <tr
                  key={log.id}
                  onClick={() => onSelectLog(log)}
                  className="cursor-pointer hover:bg-white/[0.04] transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-white/60 whitespace-nowrap">
                    {new Date(log.timestamp).toLocaleTimeString([], {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {getSeverityBadge(log.severity)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="font-semibold text-white/90">{log.category}</span>
                    <span className="block text-[10px] text-indigo-300 font-mono">{log.eventType}</span>
                  </td>
                  <td className="px-4 py-3 max-w-md truncate text-white/80" title={log.message}>
                    {log.message}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                    {log.anonId ? (
                      <button
                        type="button"
                        onClick={() => onCorrelateAnonId(log.anonId!)}
                        className="group inline-flex items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-0.5 text-[11px] font-mono font-medium text-indigo-300 hover:border-indigo-400 hover:bg-indigo-500/20 transition-colors cursor-pointer"
                        title="Click to Correlate: Filter entire dashboard by this pseudonym"
                      >
                        <UserCheck className="h-3 w-3 text-indigo-400 group-hover:scale-110 transition-transform" />
                        <span>{log.anonId}</span>
                      </button>
                    ) : (
                      <span className="text-white/30 text-[11px]">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      className="text-white/40 hover:text-white transition-colors"
                      aria-label="Inspect details"
                    >
                      <ChevronRight className="h-4 w-4 inline" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      <div className="flex items-center justify-between text-xs text-white/50 pt-2">
        <span>
          Showing {logs.length} of {total} total incidents
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={offset === 0 || isLoading}
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            className="rounded-lg border border-white/10 px-3 py-1 text-white hover:bg-white/5 disabled:opacity-40 cursor-pointer"
          >
            Previous
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            type="button"
            disabled={offset + limit >= total || isLoading}
            onClick={() => onPageChange(offset + limit)}
            className="rounded-lg border border-white/10 px-3 py-1 text-white hover:bg-white/5 disabled:opacity-40 cursor-pointer"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};
