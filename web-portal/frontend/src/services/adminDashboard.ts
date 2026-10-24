/**
 * Admin Dashboard Service
 * API ของหน้า /admin (docs/ADMIN_MONITOR.md) — ข้อมูลจริงจาก cluster / health check ไม่มีค่าตัวอย่าง
 */
import apiClient from './api';

interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

export type ServiceHealth = 'ok' | 'degraded' | 'down';
export type HourlyHealth = ServiceHealth | 'nodata';

export interface ServiceStatus {
  key: string;
  name: string;
  version: string | null;
  status: ServiceHealth;
  latencyMs: number | null;
  detail: string | null;
  checkedAt: string;
  /** 24 ช่อง เก่า → ใหม่ ช่องละ 1 ชม. */
  hourly: HourlyHealth[];
}

export interface SystemStatus {
  checkedAt: string | null;
  services: ServiceStatus[];
}

export type RoomStatus = 'ok' | 'warn' | 'down';

export interface RoomMapItem {
  room: string;
  status: RoomStatus;
  pcsTotal: number;
  pcsReady: number;
  pcsInUse: number;
  nodes: string[];
}

export interface ClusterMapItem {
  id: string;
  type: 'k3s' | 'cloud';
  status: RoomStatus | 'unknown';
  controlPlane: { node: string | null; ready: boolean } | null;
  rooms: RoomMapItem[] | null;
  region: string | null;
  instancesRunning: number | null;
}

export interface InfraMap {
  clusters: ClusterMapItem[];
}

export interface RoomUsageItem {
  room: string;
  pcsInUse: number;
  pcsTotal: number;
  state: 'launched' | 'idle';
  slot: { course: string; startsAt: string; endsAt: string; status: string } | null;
}

export interface RoomUsage {
  rooms: RoomUsageItem[];
}

/** apiClient มี interceptor คืน body (response.data) ให้แล้ว — ตัวที่ได้คือ ApiResponse ไม่ใช่ AxiosResponse */
async function getData<T>(url: string): Promise<T> {
  const body = (await apiClient.get(url)) as unknown as ApiResponse<T>;
  return body.data;
}

export const adminDashboardService = {
  getSystemStatus: () => getData<SystemStatus>('/v1/admin/system/status'),
  getInfraMap: () => getData<InfraMap>('/v1/admin/infra/map'),
  getRoomUsage: () => getData<RoomUsage>('/v1/admin/rooms/usage'),
};

export interface BillingSummary {
  month: string;
  aws: {
    budgetUsd: number;
    usedUsd: number;
    forecastUsd: number;
    usedPct: number;
    alert: 'none' | 'warn' | 'over';
    source: 'estimate' | 'mixed' | 'cost-explorer';
    reconciledAt: string | null;
    hourlyPriceUsd: number;
    instancesRunning: number;
    sessionHours: number;
  };
  onPrem: { sessionHours: number };
  share: { onPremPct: number; awsPct: number };
  daysRemaining: number;
  daysTotal: number;
  burstEnabled: boolean;
}

export interface BillingMonthly {
  months: { month: string; onPremHours: number; awsHours: number; awsUsd: number }[];
}

export const adminBillingService = {
  getSummary: () => getData<BillingSummary>('/v1/admin/billing/summary'),
  getMonthly: () => getData<BillingMonthly>('/v1/admin/billing/monthly?months=6'),
};

export type LogCategory = 'CLUSTER' | 'CLOUD';

export interface LogItem {
  id: string;
  timestamp: string;
  severity: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | string;
  category: LogCategory | string;
  eventType: string;
  source: string;
  message: string;
  anonId: string | null;
  room: string | null;
  metadata: Record<string, unknown>;
}

export interface LogList {
  total: number;
  items: LogItem[];
}

export interface LogHistogram {
  start: string;
  end: string;
  bucketHours: number;
  buckets: { t: string; count: number }[];
  byType: Record<string, number>;
}

export const adminLogService = {
  getHistogram: (category: LogCategory) =>
    getData<LogHistogram>(`/v1/admin/logs/histogram?category=${category}&hours=72&bucketHours=2`),
  getLogs: (category: LogCategory, limit = 10) => getData<LogList>(`/v1/admin/logs?category=${category}&limit=${limit}`),
};
