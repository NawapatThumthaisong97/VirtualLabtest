/**
 * LogSideDrawer Component
 * Displays detailed CamelCase JSON payload and Copy-Only Runbook recommendations
 * for an individual Infrastructure / Boundary Log.
 * Zero write/destructive actions exist on this UI.
 */
import React, { useState } from 'react';
import { X, Copy, Check, Terminal, AlertTriangle, FileJson, Lock } from 'lucide-react';
import type { InfrastructureLog } from '../../services/monitor';
import { getRunbookCommands } from '../../utils/runbook';

interface LogSideDrawerProps {
  log: InfrastructureLog | null;
  onClose: () => void;
  onCorrelateAnonId?: (anonId: string) => void;
}

export const LogSideDrawer: React.FC<LogSideDrawerProps> = ({
  log,
  onClose,
  onCorrelateAnonId,
}) => {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [jsonCopied, setJsonCopied] = useState<boolean>(false);

  if (!log) return null;

  const runbookCommands = getRunbookCommands(log);

  const handleCopyCommand = (cmd: string, idx: number) => {
    navigator.clipboard.writeText(cmd);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(log, null, 2));
    setJsonCopied(true);
    setTimeout(() => setJsonCopied(false), 2000);
  };

  const severityBadgeClass = (sev: string) => {
    switch (sev) {
      case 'CRITICAL':
        return 'bg-red-500/20 text-red-300 border-red-500/40';
      case 'ERROR':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
      case 'WARNING':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
      default:
        return 'bg-sky-500/20 text-sky-300 border-sky-500/40';
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity">
      {/* Drawer Container */}
      <div className="relative flex h-full w-full max-w-2xl flex-col bg-[#121215] border-l border-white/10 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <div className="flex items-center gap-2">
            <Terminal className="h-5 w-5 text-indigo-400" />
            <h3 className="text-base font-semibold text-white">Event Detail & Bastion Runbook</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-white/50 hover:bg-white/10 hover:text-white transition-colors cursor-pointer"
            aria-label="Close drawer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 gap-3 rounded-xl border border-white/10 bg-[#16161b] p-4 text-xs">
            <div>
              <span className="text-white/40 block mb-1">Timestamp</span>
              <span className="font-mono text-white/90">
                {new Date(log.timestamp).toLocaleString()}
              </span>
            </div>
            <div>
              <span className="text-white/40 block mb-1">Severity & Category</span>
              <div className="flex items-center gap-2">
                <span className={`rounded-md border px-2 py-0.5 font-semibold text-[11px] ${severityBadgeClass(log.severity)}`}>
                  {log.severity}
                </span>
                <span className="text-white/80 font-medium">{log.category}</span>
              </div>
            </div>
            <div>
              <span className="text-white/40 block mb-1">Event Type</span>
              <span className="font-mono text-indigo-300">{log.eventType}</span>
            </div>
            <div>
              <span className="text-white/40 block mb-1">Source Component</span>
              <span className="text-white/80">{log.source}</span>
            </div>
            {log.anonId && (
              <div className="col-span-2 flex items-center justify-between border-t border-white/5 pt-2">
                <div>
                  <span className="text-white/40 block mb-0.5">Correlated Pseudonym (Strict Anonymity)</span>
                  <span className="font-mono text-indigo-300 font-semibold">{log.anonId}</span>
                </div>
                {onCorrelateAnonId && (
                  <button
                    type="button"
                    onClick={() => {
                      onCorrelateAnonId(log.anonId!);
                      onClose();
                    }}
                    className="flex items-center gap-1 rounded bg-indigo-500/20 border border-indigo-500/40 px-2.5 py-1 text-[11px] font-medium text-indigo-300 hover:bg-indigo-500/30 transition-colors cursor-pointer"
                  >
                    <span>Correlate Across Dashboard</span>
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Log Message */}
          <div className="flex flex-col gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-white/60">
              Sanitized Message
            </span>
            <div className="rounded-xl border border-white/10 bg-[#18181f] p-4 font-mono text-xs text-white/90 leading-relaxed whitespace-pre-wrap">
              {log.message}
            </div>
          </div>

          {/* Copy-Only Runbook Section */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-400" />
                <span className="text-xs font-semibold uppercase tracking-wider text-amber-300">
                  Bastion Host Diagnostic Runbook (Copy-Only)
                </span>
              </div>
              <div className="flex items-center gap-1 text-[11px] text-amber-400/80">
                <Lock className="h-3 w-3" />
                <span>Read-Only Mode</span>
              </div>
            </div>

            <p className="text-xs text-white/50 leading-relaxed">
              To investigate this alert without granting this UI destructive API privileges, execute the following commands via your secure Bastion Host session:
            </p>

            <div className="flex flex-col gap-3">
              {runbookCommands.map((item, idx) => (
                <div
                  key={item.title}
                  className="rounded-xl border border-amber-500/20 bg-amber-500/[0.04] p-3.5 text-xs"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-semibold text-white/90">{item.title}</span>
                    <button
                      type="button"
                      onClick={() => handleCopyCommand(item.command, idx)}
                      className="flex items-center gap-1 rounded bg-white/10 px-2 py-1 text-[11px] font-medium text-white hover:bg-white/20 transition-colors cursor-pointer"
                    >
                      {copiedIndex === idx ? (
                        <>
                          <Check className="h-3 w-3 text-emerald-400" />
                          <span className="text-emerald-400">Copied!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3 text-white/70" />
                          <span>Copy CLI</span>
                        </>
                      )}
                    </button>
                  </div>
                  <p className="text-[11px] text-white/50 mb-2">{item.description}</p>
                  <pre className="overflow-x-auto rounded bg-black/60 p-2 font-mono text-[11px] text-amber-200">
                    {item.command}
                  </pre>
                </div>
              ))}
            </div>
          </div>

          {/* Raw JSON Payload (CamelCase) */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileJson className="h-4 w-4 text-white/60" />
                <span className="text-xs font-semibold uppercase tracking-wider text-white/60">
                  Standardized JSON Schema (CamelCase)
                </span>
              </div>
              <button
                type="button"
                onClick={handleCopyJson}
                className="flex items-center gap-1 rounded bg-white/10 px-2.5 py-1 text-[11px] font-medium text-white/80 hover:bg-white/20 transition-colors cursor-pointer"
              >
                {jsonCopied ? (
                  <>
                    <Check className="h-3 w-3 text-emerald-400" />
                    <span className="text-emerald-400">Copied JSON!</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    <span>Copy JSON</span>
                  </>
                )}
              </button>
            </div>
            <pre className="max-h-60 overflow-y-auto rounded-xl border border-white/10 bg-black/50 p-4 font-mono text-xs text-sky-300">
              {JSON.stringify(log, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};
