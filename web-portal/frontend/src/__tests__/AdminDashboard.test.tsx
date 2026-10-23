import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdminDashboardPage from '../pages/AdminDashboard';
import * as AuthContextModule from '../contexts/AuthContext';
import { adminDashboardService } from '../services/adminDashboard';
import type { InfraMap, RoomUsage, SystemStatus } from '../services/adminDashboard';
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

  it('cards without an API say so instead of showing sample numbers', async () => {
    renderPage();
    expect(await screen.findByText('Log Explorer')).toBeDefined();
    expect(screen.getAllByText('ยังไม่มีข้อมูล')).toHaveLength(3);
    expect(screen.queryByText('$175.75')).toBeNull();
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
