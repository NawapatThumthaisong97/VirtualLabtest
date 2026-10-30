import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdminDashboardPage from '../pages/AdminDashboard';
import * as AuthContextModule from '../contexts/AuthContext';
import { adminBillingService, adminDashboardService, adminLogService } from '../services/adminDashboard';
import type { BillingMonthly, BillingSummary, InfraMap, LogHistogram, LogList, RoomUsage, SystemStatus } from '../services/adminDashboard';
import { homeFor } from '../utils/homePath';
import apiClient from '../services/api';

const hourly = Array.from({ length: 24 }, (_, i) => (i === 23 ? 'degraded' : 'nodata')) as SystemStatus['services'][0]['hourly'];

const status: SystemStatus = {
  checkedAt: '2026-10-23T10:03:19Z',
  services: [
    { key: 'backend', name: 'FastAPI Server', version: '1.0.0', status: 'ok', latencyMs: 15, detail: null, checkedAt: '2026-10-23T10:03:19Z', hourly },
    { key: 'k8s', name: 'Kubernetes', version: 'v1.35.5+k3s1', status: 'degraded', latencyMs: 247, detail: 'NotReady: worker-pete (worker)', checkedAt: '2026-10-23T10:03:19Z', hourly },
    { key: 'registry', name: 'Docker registry', version: null, status: 'down', latencyMs: null, detail: 'URLError: refused', checkedAt: '2026-10-23T10:03:19Z', hourly },
  ],
};

const map: InfraMap = {
  clusters: [
    {
      id: 'k3s-main', type: 'k3s', status: 'warn', controlPlane: { node: 'master', ready: true }, region: null, instancesRunning: null,
      rooms: [
        { room: 'LC-123', status: 'ok', pcsTotal: 1, pcsReady: 1, pcsInUse: 1, nodes: ['worker-pete'] },
        { room: 'LC-207', status: 'down', pcsTotal: 2, pcsReady: 0, pcsInUse: 0, nodes: ['a', 'b'] },
      ],
    },
    { id: 'aws', type: 'cloud', status: 'unknown', controlPlane: null, rooms: null, region: 'ap-southeast-1', instancesRunning: 2 },
  ],
};

const usage: RoomUsage = {
  rooms: [
    { room: 'LC-123', pcsInUse: 1, pcsTotal: 1, state: 'launched',
      slot: { course: 'Software Engineering', startsAt: '2026-10-23T06:00:00Z', endsAt: '2026-10-23T09:00:00Z', status: 'ready' } },
    { room: 'LC-207', pcsInUse: 0, pcsTotal: 2, state: 'idle', slot: null },
  ],
};

const summary: BillingSummary = {
  month: '2026-10',
  aws: { budgetUsd: 200, usedUsd: 172.4, forecastUsd: 210.5, usedPct: 86.2, alert: 'warn', source: 'mixed', reconciledAt: '2026-10-24T05:00:00Z',
         hourlyPriceUsd: 0.1236, instancesRunning: 1, sessionHours: 1394.8 },
  onPrem: { sessionHours: 812 },
  share: { onPremPct: 36.8, awsPct: 63.2 },
  daysRemaining: 8,
  daysTotal: 31,
  burstEnabled: false,
};

const monthly: BillingMonthly = {
  months: [
    { month: '2026-09', onPremHours: 100, awsHours: 20, awsUsd: 2.47 },
    { month: '2026-10', onPremHours: 812, awsHours: 1394.8, awsUsd: 172.4 },
  ],
};

const histogram: LogHistogram = {
  start: '2026-10-20T12:00:00Z',
  end: '2026-10-23T12:00:00Z',
  bucketHours: 2,
  buckets: Array.from({ length: 36 }, (_, i) => ({ t: new Date(Date.UTC(2026, 9, 20, 12 + i * 2)).toISOString(), count: i === 35 ? 4 : 0 })),
  byType: { NODE_NOT_READY: 3, POD_EVENT: 1 },
};

const logList: LogList = {
  total: 1,
  items: [{ id: 'l1', timestamp: '2026-10-23T11:00:00Z', severity: 'WARNING', category: 'CLUSTER', eventType: 'NODE_NOT_READY',
            source: 'worker-pete', message: 'Node worker-pete NotReady', anonId: null, room: null, metadata: {} }],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AdminDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AdminDashboard (/admin)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'u1', email: 'admin@dome.tu.ac.th', name: 'Admin', studentId: null, role: 'admin' },
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });
    vi.spyOn(adminDashboardService, 'getSystemStatus').mockResolvedValue(status);
    vi.spyOn(adminDashboardService, 'getInfraMap').mockResolvedValue(map);
    vi.spyOn(adminDashboardService, 'getRoomUsage').mockResolvedValue(usage);
    vi.spyOn(adminBillingService, 'getSummary').mockResolvedValue(summary);
    vi.spyOn(adminBillingService, 'getMonthly').mockResolvedValue(monthly);
    vi.spyOn(adminLogService, 'getHistogram').mockResolvedValue(histogram);
    vi.spyOn(adminLogService, 'getLogs').mockResolvedValue(logList);
  });

  it('shows real services with status and detail', async () => {
    renderPage();
    expect(await screen.findByText('FastAPI Server')).toBeDefined();
    expect(screen.getByText('v1.35.5+k3s1')).toBeDefined();
    expect(screen.getByText('Degraded')).toBeDefined();
    expect(screen.getByText('NotReady: worker-pete (worker)')).toBeDefined();
    expect(screen.getByText('Showing 3')).toBeDefined();
  });

  it('draws one box per real room and shows the class using it', async () => {
    renderPage();
    expect(await screen.findByText('ClusterName : LC-123')).toBeDefined();
    expect(screen.getByText('1/1 in use · 1 ready')).toBeDefined();
    expect(screen.getByText('Software Engineering')).toBeDefined();
    expect(screen.getByText('2 instances · ap-southeast-1')).toBeDefined();

    fireEvent.click(screen.getByText('LC-207'));
    expect(screen.getByText('ClusterName : LC-207')).toBeDefined();
    expect(screen.getByText('Idle')).toBeDefined();
  });

  it('header has feature buttons; not-yet features are disabled', async () => {
    renderPage();
    expect(await screen.findByText('Bill Explorer')).toBeDefined();
    expect((screen.getByText('Logs') as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByText('Class Scheduler') as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText('Class System')).toBeNull();
    expect((screen.getByText('Security') as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText('is pending review')).toBeNull();
  });

  it('no sample numbers from the design are left', async () => {
    renderPage();
    expect(await screen.findByText('Log Explorer')).toBeDefined();
    expect(screen.queryByText('ยังไม่มีข้อมูล')).toBeNull();
    expect(screen.queryByText('$175.75')).toBeNull();
    expect(screen.queryByText('Microsoft Azure')).toBeNull();
  });

  it('log explorer shows counts by type, detail lists latest logs, switches to cloud', async () => {
    renderPage();
    expect(await screen.findByText('NODE_NOT_READY · 3')).toBeDefined();
    fireEvent.click(screen.getByText('ล่าสุด'));
    expect(await screen.findByTitle('Node worker-pete NotReady')).toBeDefined();
    fireEvent.click(screen.getByText('Cloud Usage'));
    expect(adminLogService.getHistogram).toHaveBeenCalledWith('CLOUD');
  });

  it('billing shows AWS spend vs budget, burst off and this month share', async () => {
    renderPage();
    expect(await screen.findByText('$172.40')).toBeDefined();
    expect(screen.getByText(/of \$200 budget \(86.2%\)/)).toBeDefined();
    expect(screen.getByText('AWS burst ปิดอยู่')).toBeDefined();
    expect(screen.getByText('AWS actual + today estimate')).toBeDefined();
    expect(screen.getByText('remain 8/31 days')).toBeDefined();
    expect(screen.getByText('2206.8 h')).toBeDefined();
    expect(screen.getAllByText('Oct').length).toBeGreaterThan(0);
  });
});

describe('homeFor (redirect after login)', () => {
  it('admin goes to /admin, others to /', () => {
    expect(homeFor('admin')).toBe('/admin');
    expect(homeFor('student')).toBe('/');
    expect(homeFor('instructor', '/')).toBe('/');
  });

  it('page the user was bounced from wins', () => {
    expect(homeFor('admin', '/courses/abc')).toBe('/courses/abc');
    expect(homeFor('admin', '/login')).toBe('/admin');
  });
});

describe('adminDashboardService', () => {
  it('unwraps ApiResponse once (apiClient interceptor already returns the body)', async () => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'get').mockResolvedValue({ success: true, message: 'ok', data: status });
    expect(await adminDashboardService.getSystemStatus()).toEqual(status);
    expect(apiClient.get).toHaveBeenCalledWith('/v1/admin/system/status');
  });
});
