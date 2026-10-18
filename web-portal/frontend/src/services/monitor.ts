/**
 * Monitor & SIEM Service
 * Interacts with backend metrics, security counters, and boundary logs APIs.
 * All operations are strictly Read-Only per Zero Trust & SIEM constraints.
 */
import apiClient from './api';

export interface ApiResponse<T> {
  success: boolean;
  message?: string;
  data: T;
}

export interface ClusterMetricsSummary {
  totalCpuAllocated: number;
  totalCpuLimit: number;
  totalRamAllocatedMb: number;
  totalRamLimitMb: number;
  activeSessions: number;
  clusterCount: number;
}

export interface ProviderMetrics {
  provider: string;
  isCloud: boolean;
  natSubnet: string;
  cpuAllocated: number;
  cpuLimit: number;
  ramAllocatedMb: number;
  ramLimitMb: number;
  activeSessions: number;
}

export interface TimeSeriesPoint {
  timestamp: string;
  cpuAllocated: number;
  ramAllocatedMb: number;
  activeSessions: number;
  violationsCount: number;
}

export interface MetricsResponseData {
  summary: ClusterMetricsSummary;
  byProvider: ProviderMetrics[];
  timeSeries: TimeSeriesPoint[];
}

export interface SecurityCountersData {
  squidEgressDrops: number;
  squidEgressAllowed: number;
  kyvernoBlocks: number;
  tailscaleDenies: number;
  totalViolations: number;
}

export type LogSeverity = 'CRITICAL' | 'ERROR' | 'WARNING' | 'INFO';

export type LogCategory =
  | 'SECURITY_VIOLATION'
  | 'INFRA_FAILURE'
  | 'EGRESS_DROP'
  | 'OOM_KILL'
  | 'KYVERNO_BLOCK'
  | 'TAILSCALE_DENY'
  | 'POLICY_VIOLATION'
  | string;

export interface InfrastructureLog {
  id: string;
  timestamp: string;
  severity: LogSeverity;
  category: LogCategory;
  eventType: string;
  source: string;
  message: string;
  anonId?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface LogsResponseData {
  logs: InfrastructureLog[];
  total: number;
}

export interface MonitorFilterParams {
  provider?: 'all' | 'aws' | 'local';
  natSubnet?: string;
  startDate?: string;
  endDate?: string;
  severity?: string;
  category?: string;
  anonId?: string;
  limit?: number;
  offset?: number;
}

export const monitorService = {
  /**
   * ดึงข้อมูลสถานะทรัพยากร CPU, RAM, Active Sessions และการจัดสรรตาม Provider
   */
  getMetrics: async (params?: MonitorFilterParams): Promise<MetricsResponseData> => {
    const query = new URLSearchParams();
    if (params?.provider && params.provider !== 'all') query.set('provider', params.provider);
    if (params?.natSubnet && params.natSubnet !== 'all') query.set('nat_subnet', params.natSubnet);
    if (params?.startDate) query.set('start_date', params.startDate);
    if (params?.endDate) query.set('end_date', params.endDate);

    const qs = query.toString() ? `?${query.toString()}` : '';
    const res = await apiClient.get<ApiResponse<MetricsResponseData>>(`/v1/metrics${qs}`);
    return (res as unknown as ApiResponse<MetricsResponseData>).data;
  },

  /**
   * ดึงสถิติตัวนับการละเมิดความปลอดภัย (Squid Egress Drops, Kyverno Blocks, Tailscale Denies)
   */
  getSecurityCounters: async (params?: MonitorFilterParams): Promise<SecurityCountersData> => {
    const query = new URLSearchParams();
    if (params?.startDate) query.set('start_date', params.startDate);
    if (params?.endDate) query.set('end_date', params.endDate);

    const qs = query.toString() ? `?${query.toString()}` : '';
    const res = await apiClient.get<ApiResponse<SecurityCountersData>>(`/v1/metrics/security-counters${qs}`);
    return (res as unknown as ApiResponse<SecurityCountersData>).data;
  },

  /**
   * ดึงรายการ Critical Infrastructure & Boundary Logs พร้อมการทำ Data Masking
   */
  getLogs: async (params?: MonitorFilterParams): Promise<LogsResponseData> => {
    const query = new URLSearchParams();
    if (params?.severity && params.severity !== 'ALL') query.set('severity', params.severity);
    if (params?.category && params.category !== 'ALL') query.set('category', params.category);
    if (params?.anonId) query.set('anon_id', params.anonId);
    if (params?.startDate) query.set('start_date', params.startDate);
    if (params?.endDate) query.set('end_date', params.endDate);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));

    const qs = query.toString() ? `?${query.toString()}` : '';
    const res = await apiClient.get<ApiResponse<LogsResponseData>>(`/v1/logs${qs}`);
    return (res as unknown as ApiResponse<LogsResponseData>).data;
  },
};

