/**
 * AdminMonitor Page
 * Sub-Issue 3 (Issue #75): Read-Only Monitor, Security Overview & Billing Dashboard UI
 * SIEM-Ready Observability Portal for Administrators.
 * Strictly operates in [🔒 READ-ONLY MODE] with Zero PII and No Destructive Actions.
 */
import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  CreditCard,
  Lock,
  Terminal,
} from 'lucide-react';
import {
  GlobalFilterBar,
  type GlobalFilters,
} from '../components/monitor/GlobalFilterBar';
import { ResourceSecurityOverview } from '../components/monitor/ResourceSecurityOverview';
import { LogExplorerTable } from '../components/monitor/LogExplorerTable';
import { LogSideDrawer } from '../components/monitor/LogSideDrawer';
import { BillingDashboard } from '../components/monitor/BillingDashboard';
import {
  monitorService,
  type InfrastructureLog,
} from '../services/monitor';
import {
  billingService,
  type BillingGroupBy,
} from '../services/billing';

export default function AdminMonitorPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Active Tab state
  const activeTab = searchParams.get('tab') || 'overview';
  const setActiveTab = (tab: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('tab', tab);
      return next;
    });
  };

  // Extract Global Filters from URL
  const filters: GlobalFilters = useMemo(() => ({
    provider: (searchParams.get('provider') as GlobalFilters['provider']) || 'all',
    natSubnet: searchParams.get('nat_subnet') || 'all',
    timeRange: (searchParams.get('time_range') as GlobalFilters['timeRange']) || '24h',
    anonId: searchParams.get('anon_id') || '',
  }), [searchParams]);

  // Update Global Filters in URL
  const handleFilterChange = (partial: Partial<GlobalFilters>) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (partial.provider !== undefined) {
        if (partial.provider === 'all') next.delete('provider');
        else next.set('provider', partial.provider);
      }
      if (partial.natSubnet !== undefined) {
        if (partial.natSubnet === 'all') next.delete('nat_subnet');
        else next.set('nat_subnet', partial.natSubnet);
      }
      if (partial.timeRange !== undefined) {
        next.set('time_range', partial.timeRange);
      }
      if (partial.anonId !== undefined) {
        if (!partial.anonId) next.delete('anon_id');
        else next.set('anon_id', partial.anonId);
      }
      return next;
    });
  };

  // Calculate start/end date from timeRange
  const { startDate, endDate } = useMemo(() => {
    const end = new Date();
    const start = new Date();
    switch (filters.timeRange) {
      case '1h':
        start.setHours(end.getHours() - 1);
        break;
      case '6h':
        start.setHours(end.getHours() - 6);
        break;
      case '24h':
        start.setHours(end.getHours() - 24);
        break;
      case '7d':
        start.setDate(end.getDate() - 7);
        break;
      case '30d':
        start.setDate(end.getDate() - 30);
        break;
      default:
        start.setHours(end.getHours() - 24);
    }
    return {
      startDate: start.toISOString(),
      endDate: end.toISOString(),
    };
  }, [filters.timeRange]);

  // Log filter states
  const severityFilter = searchParams.get('severity') || 'ALL';
  const categoryFilter = searchParams.get('category') || 'ALL';
  const logLimit = 50;
  const [logOffset, setLogOffset] = useState<number>(0);
  const [selectedLog, setSelectedLog] = useState<InfrastructureLog | null>(null);

  const handleSeverityChange = (sev: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (sev === 'ALL') next.delete('severity');
      else next.set('severity', sev);
    });
    setLogOffset(0);
  };

  const handleCategoryChange = (cat: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (cat === 'ALL') next.delete('category');
      else next.set('category', cat);
    });
    setLogOffset(0);
  };

  // Billing Grouping State
  const billingGroupBy: BillingGroupBy = (searchParams.get('billing_group_by') as BillingGroupBy) || 'course';
  const handleBillingGroupByChange = (groupBy: BillingGroupBy) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('billing_group_by', groupBy);
      return next;
    });
  };

  // Click-to-Correlate handler: sets anon_id in URL and switches or filters seamlessly
  const handleCorrelateAnonId = (anonId: string) => {
    handleFilterChange({ anonId });
  };

  // 1. Fetch Cluster Metrics
  const {
    data: metricsData,
    isLoading: isMetricsLoading,
    refetch: refetchMetrics,
  } = useQuery({
    queryKey: ['admin-metrics', filters.provider, filters.natSubnet, startDate, endDate],
    queryFn: () =>
      monitorService.getMetrics({
        provider: filters.provider,
        natSubnet: filters.natSubnet,
        startDate,
        endDate,
      }),
  });

  // 2. Fetch Security Counters
  const {
    data: securityData,
    isLoading: isSecurityLoading,
    refetch: refetchSecurity,
  } = useQuery({
    queryKey: ['admin-security-counters', startDate, endDate],
    queryFn: () =>
      monitorService.getSecurityCounters({
        startDate,
        endDate,
      }),
  });

  // 3. Fetch Boundary Logs
  const {
    data: logsData,
    isLoading: isLogsLoading,
    refetch: refetchLogs,
  } = useQuery({
    queryKey: [
      'admin-logs',
      severityFilter,
      categoryFilter,
      filters.anonId,
      startDate,
      endDate,
      logLimit,
      logOffset,
    ],
    queryFn: () =>
      monitorService.getLogs({
        severity: severityFilter,
        category: categoryFilter,
        anonId: filters.anonId || undefined,
        startDate,
        endDate,
        limit: logLimit,
        offset: logOffset,
      }),
  });

  // 4. Fetch Billing Summary
  const {
    data: billingData,
    isLoading: isBillingLoading,
    refetch: refetchBilling,
  } = useQuery({
    queryKey: ['admin-billing', billingGroupBy, startDate, endDate],
    queryFn: () =>
      billingService.getSummary({
        groupBy: billingGroupBy,
        startDate,
        endDate,
      }),
  });

  const handleGlobalRefresh = () => {
    refetchMetrics();
    refetchSecurity();
    refetchLogs();
    refetchBilling();
  };

  const isGlobalLoading =
    isMetricsLoading || isSecurityLoading || isLogsLoading || isBillingLoading;

  return (
    <div className="min-h-screen bg-[#0a0a0d] text-white p-6 md:p-8">
      <div className="mx-auto max-w-7xl flex flex-col gap-6">
        {/* Page Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-white">
                Admin Monitor & SIEM Dashboard
              </h1>
              <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-0.5 text-xs font-semibold text-amber-300">
                [🔒 READ-ONLY MODE]
              </span>
            </div>
            <p className="mt-1 text-xs text-white/50">
              Observability for hybrid cloud resources, Zero Trust boundaries, and anonymized billing.
            </p>
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-white/60">
            <Lock className="h-3.5 w-3.5 text-amber-400" />
            <span>Strict View-Only. Remediation via Bastion Host terminal only.</span>
          </div>
        </div>

        {/* Global Filter Bar */}
        <GlobalFilterBar
          filters={filters}
          onChange={handleFilterChange}
          onRefresh={handleGlobalRefresh}
          isLoading={isGlobalLoading}
        />

        {/* Tab Navigation */}
        <div className="flex border-b border-white/10 text-sm font-medium">
          <button
            type="button"
            onClick={() => setActiveTab('overview')}
            className={`flex items-center gap-2 border-b-2 px-4 py-3 transition-colors cursor-pointer ${
              activeTab === 'overview'
                ? 'border-indigo-500 text-indigo-400 font-semibold'
                : 'border-transparent text-white/60 hover:text-white'
            }`}
          >
            <Activity className="h-4 w-4" />
            <span>Cluster & Security Overview</span>
            {securityData && securityData.totalViolations > 0 && (
              <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-[11px] font-bold text-rose-300 border border-rose-500/30">
                {securityData.totalViolations}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('logs')}
            className={`flex items-center gap-2 border-b-2 px-4 py-3 transition-colors cursor-pointer ${
              activeTab === 'logs'
                ? 'border-indigo-500 text-indigo-400 font-semibold'
                : 'border-transparent text-white/60 hover:text-white'
            }`}
          >
            <Terminal className="h-4 w-4" />
            <span>Boundary Logs Explorer</span>
            {logsData && logsData.total > 0 && (
              <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/80">
                {logsData.total}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('billing')}
            className={`flex items-center gap-2 border-b-2 px-4 py-3 transition-colors cursor-pointer ${
              activeTab === 'billing'
                ? 'border-indigo-500 text-indigo-400 font-semibold'
                : 'border-transparent text-white/60 hover:text-white'
            }`}
          >
            <CreditCard className="h-4 w-4" />
            <span>Billing & Financial Reports</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('grafana')}
            className={`flex items-center gap-2 border-b-2 px-4 py-3 transition-colors cursor-pointer ${
              activeTab === 'grafana'
                ? 'border-emerald-500 text-emerald-400 font-semibold'
                : 'border-transparent text-white/60 hover:text-white'
            }`}
          >
            <Activity className="h-4 w-4 text-emerald-400" />
            <span>Grafana 5-Layer SIEM (Live)</span>
            <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300 border border-emerald-500/30">
              Layer 5
            </span>
          </button>
        </div>

        {/* Tab Content Display */}
        {activeTab === 'overview' && (
          <ResourceSecurityOverview
            metrics={metricsData}
            securityCounters={securityData}
            isLoading={isMetricsLoading || isSecurityLoading}
          />
        )}

        {activeTab === 'logs' && (
          <LogExplorerTable
            logs={logsData?.logs || []}
            total={logsData?.total || 0}
            isLoading={isLogsLoading}
            selectedSeverity={severityFilter}
            selectedCategory={categoryFilter}
            onSeverityChange={handleSeverityChange}
            onCategoryChange={handleCategoryChange}
            onSelectLog={(log) => setSelectedLog(log)}
            onCorrelateAnonId={handleCorrelateAnonId}
            limit={logLimit}
            offset={logOffset}
            onPageChange={(newOffset) => setLogOffset(newOffset)}
          />
        )}

        {activeTab === 'billing' && (
          <BillingDashboard
            summary={billingData}
            groupBy={billingGroupBy}
            onGroupByChange={handleBillingGroupByChange}
            isLoading={isBillingLoading}
          />
        )}

        {activeTab === 'grafana' && (
          <div className="flex flex-col gap-4 rounded-xl border border-white/10 bg-white/[0.02] p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">
                  Layer 5: Grafana SIEM Command Center (Sigma Rules + LogsQL + Falco eBPF Fast-Track)
                </h2>
                <p className="text-xs text-white/60">
                  Unified 5-Layer SIEM Visualization powered by Grafana, VictoriaLogs (14d Hot Storage), and AWS S3 .parquet (90d–365d Cold Storage).
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <a
                  href="http://100.69.137.47:30300/d/vlab-siem-5layer?orgId=1"
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg bg-emerald-600/80 hover:bg-emerald-500 px-3 py-1.5 font-semibold text-white transition"
                >
                  Open Grafana Full Screen &rarr;
                </a>
                <a
                  href="http://100.69.137.47:30428/select/vmui"
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-sky-500/40 bg-sky-500/10 hover:bg-sky-500/20 px-3 py-1.5 font-semibold text-sky-300 transition"
                >
                  VictoriaLogs Hot UI (LogsQL) &rarr;
                </a>
                <a
                  href="http://100.69.137.47:30900"
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 hover:bg-indigo-500/20 px-3 py-1.5 font-semibold text-indigo-300 transition"
                >
                  AWS S3 (.parquet) Explorer &rarr;
                </a>
              </div>
            </div>
            <div className="overflow-hidden rounded-lg border border-white/10 bg-[#111217]">
              <iframe
                title="Grafana 5-Layer SIEM Command Center"
                src="http://100.69.137.47:30300/d/vlab-siem-5layer?orgId=1&kiosk"
                className="h-[780px] w-full border-0"
              />
            </div>
          </div>
        )}

        {/* Side Drawer for Log Details & Bastion Runbook */}
        <LogSideDrawer
          log={selectedLog}
          onClose={() => setSelectedLog(null)}
          onCorrelateAnonId={handleCorrelateAnonId}
        />
      </div>
    </div>
  );
}
