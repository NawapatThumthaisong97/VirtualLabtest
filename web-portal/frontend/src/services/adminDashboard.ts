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

export interface LogQuery {
  category?: LogCategory;
  severity?: string;
  type?: string;
}

const logParams = (q: LogQuery) =>
  Object.entries(q)
    .filter(([, v]) => v)
    .map(([k, v]) => `&${k}=${encodeURIComponent(String(v))}`)
    .join('');

export const adminLogService = {
  getHistogram: (category: LogCategory) =>
    getData<LogHistogram>(`/v1/admin/logs/histogram?category=${category}&hours=72&bucketHours=2`),
  getLogs: (category: LogCategory, limit = 10) => getData<LogList>(`/v1/admin/logs?category=${category}&limit=${limit}`),
  /** หน้า Log Explorer (/admin/logs): กรองได้ทุกแบบ */
  histogram: (q: LogQuery, hours: number, bucketHours: number) =>
    getData<LogHistogram>(`/v1/admin/logs/histogram?hours=${hours}&bucketHours=${bucketHours}${logParams(q)}`),
  list: (q: LogQuery, limit: number, offset: number) =>
    getData<LogList>(`/v1/admin/logs?limit=${limit}&offset=${offset}${logParams(q)}`),
};

// ---------- จองห้อง (หน้า /admin/scheduler) ----------

export interface BookingItem {
  id: string;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  requesterName: string;
  requesterEmail: string;
  courseId: string;
  courseName: string;
  labId: string;
  labTitle: string;
  weekday: number;
  startTime: string;
  endTime: string;
  validFrom: string;
  validUntil: string;
  machines: number;
  room: string | null;
  note: string | null;
  decisionNote: string | null;
  classScheduleId: string | null;
  slotsCreated: number | null;
  mailStatus: string | null;
  createdAt: string;
}

export interface CalendarEventItem {
  id: string;
  title: string;
  date: string;
  start: string;
  end: string;
  room: string | null;
  courseId: string;
  courseName: string;
  machines: number;
  status: string;
}

export interface SchedulerOptions {
  courses: { id: string; code: string; name: string; instructors: string[] }[];
  labs: { id: string; courseId: string; title: string; hasImage: boolean }[];
  rooms: { room: string; pcsTotal: number }[];
}

export interface ScheduleFormBody {
  courseId?: string;
  labId: string;
  room: string;
  machines: number;
  firstDate: string;
  startTime: string;
  endTime: string;
  until: string;
  note?: string;
}

async function postData<T>(url: string, body: unknown): Promise<T> {
  const res = (await apiClient.post(url, body)) as unknown as ApiResponse<T>;
  return res.data;
}

export const bookingService = {
  getCalendar: (month: string) =>
    getData<{ month: string; events: CalendarEventItem[] }>(`/v1/admin/calendar?month=${month}`),
  getPending: () => getData<{ items: BookingItem[]; pendingCount: number }>('/v1/admin/bookings?status=pending'),
  getOptions: () => getData<SchedulerOptions>('/v1/admin/scheduler/options'),
  approve: (id: string, body: ScheduleFormBody) => postData<BookingItem>(`/v1/admin/bookings/${id}/approve`, body),
  reject: (id: string, reason: string) => postData<BookingItem>(`/v1/admin/bookings/${id}/reject`, { reason }),
  create: (body: ScheduleFormBody) => postData<BookingItem>('/v1/admin/schedules', body),
};
