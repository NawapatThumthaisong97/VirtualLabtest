import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ProtectedRoute from '../components/ProtectedRoute';
import AdminMonitorPage from '../pages/AdminMonitor';
import * as AuthContextModule from '../contexts/AuthContext';
import { monitorService } from '../services/monitor';
import { billingService } from '../services/billing';
import type { CurrentUser } from '../services/auth';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  AreaChart: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Area: () => <div />,
  BarChart: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  CartesianGrid: () => <div />,
  defs: () => <div />,
  linearGradient: () => <div />,
  stop: () => <div />,
}));

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

const mockAdminUser: CurrentUser = {
  id: 'usr-admin',
  email: 'admin@tu.ac.th',
  name: 'Admin VirtualLab',
  studentId: null,
  role: 'admin',
};

const mockStudentUser: CurrentUser = {
  id: 'usr-student',
  email: 'student_6709616001@dome.tu.ac.th',
  name: 'Student Somchai',
  studentId: '6709616001',
  role: 'student',
};

const mockMetrics = {
  summary: {
    totalCpuAllocated: 24.5,
    totalCpuLimit: 64.0,
    totalRamAllocatedMb: 32768.0,
    totalRamLimitMb: 65536.0,
    activeSessions: 12,
    clusterCount: 3,
  },
  byProvider: [
    {
      provider: 'AWS SkyPilot',
      isCloud: true,
      natSubnet: '10.0.0.0/16',
      cpuAllocated: 16.0,
      cpuLimit: 32.0,
      ramAllocatedMb: 16384.0,
      ramLimitMb: 32768.0,
      activeSessions: 8,
    },
    {
      provider: 'Local K3s (Room 1 NAT)',
      isCloud: false,
      natSubnet: '192.168.1.0/24',
      cpuAllocated: 8.5,
      cpuLimit: 32.0,
      ramAllocatedMb: 16384.0,
      ramLimitMb: 32768.0,
      activeSessions: 4,
    },
  ],
  timeSeries: [
    {
      timestamp: '2026-10-18T10:00:00Z',
      cpuAllocated: 20.0,
      ramAllocatedMb: 24576.0,
      activeSessions: 10,
      violationsCount: 3,
    },
  ],
};

const mockSecurityCounters = {
  squidEgressDrops: 142,
  squidEgressAllowed: 3420,
  kyvernoBlocks: 18,
  tailscaleDenies: 25,
  totalViolations: 185,
};

const mockLogs = {
  logs: [
    {
      id: 'log-001',
      timestamp: '2026-10-18T11:30:00Z',
      severity: 'CRITICAL' as const,
      category: 'EGRESS_DROP',
      eventType: 'SQUID_EGRESS_DENY',
      source: 'squid-proxy-pod',
      message: 'TCP_DENIED to http://crypto-miner.xyz on port 8080 from 192.168.1.45',
      anonId: 'anon_8f92a1b7',
      metadata: { domain: 'crypto-miner.xyz', port: 8080 },
    },
    {
      id: 'log-002',
      timestamp: '2026-10-18T11:25:00Z',
      severity: 'ERROR' as const,
      category: 'KYVERNO_BLOCK',
      eventType: 'DISALLOW_PRIVILEGED_POD',
      source: 'kyverno-controller',
      message: 'Blocked privileged container requested by pod lab-runner-x9',
      anonId: 'anon_3c21e5f8',
      metadata: { rule: 'disallow-privileged-containers' },
    },
  ],
  total: 2,
};

const mockBilling = {
  groupBy: 'course' as const,
  totalCostThb: 431.25,
  totalSessions: 3,
  totalCpuHours: 7.0,
  totalGpuHours: 3.0,
  totalRamMbHours: 28672.0,
  items: [
    {
      groupKey: 'CS101',
      groupName: 'CS101 - Intro to CS',
      totalSessions: 1,
      totalCpuHours: 2.0,
      totalGpuHours: 0.0,
      totalRamMbHours: 4096.0,
      totalCostThb: 30.5,
      isCloud: false,
      natSubnet: '192.168.1.0/24',
      anonId: null,
    },
    {
      groupKey: 'CS202',
      groupName: 'CS202 - Algorithms',
      totalSessions: 2,
      totalCpuHours: 5.0,
      totalGpuHours: 3.0,
      totalRamMbHours: 24576.0,
      totalCostThb: 400.75,
      isCloud: true,
      natSubnet: '10.0.0.0/16',
      anonId: null,
    },
  ],
};

describe('Issue #75: Read-Only Monitor, Security Overview & Billing Dashboard UI', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.spyOn(monitorService, 'getMetrics').mockResolvedValue(mockMetrics);
    vi.spyOn(monitorService, 'getSecurityCounters').mockResolvedValue(mockSecurityCounters);
    vi.spyOn(monitorService, 'getLogs').mockResolvedValue(mockLogs);
    vi.spyOn(billingService, 'getSummary').mockResolvedValue(mockBilling);
    vi.spyOn(billingService, 'downloadReport').mockResolvedValue('test_report.csv');
  });

  it('enforces Admin-only route protection and blocks Student with Access Restricted', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: mockStudentUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/monitor']}>
          <Routes>
            <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
              <Route path="/admin/monitor" element={<AdminMonitorPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText('Access Restricted')).toBeDefined();
    expect(screen.queryByText('Admin Monitor & SIEM Dashboard')).toBeNull();
  });

  it('renders [🔒 READ-ONLY MODE] prominently and guarantees no destructive buttons exist', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: mockAdminUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/monitor']}>
          <Routes>
            <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
              <Route path="/admin/monitor" element={<AdminMonitorPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Read-Only badge check
    expect(screen.getAllByText(/\[🔒 READ-ONLY MODE\]/i).length).toBeGreaterThan(0);

    // Strict No-Destructive-Actions Check
    const destructiveLabels = [
      /terminate/i,
      /delete session/i,
      /kill pod/i,
      /ban ip/i,
      /block user/i,
      /stop cluster/i,
    ];
    destructiveLabels.forEach((pattern) => {
      expect(screen.queryByRole('button', { name: pattern })).toBeNull();
    });
  });

  it('renders Cluster Resource and Security Boundary Overview cards', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: mockAdminUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/monitor?tab=overview']}>
          <Routes>
            <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
              <Route path="/admin/monitor" element={<AdminMonitorPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('AWS SkyPilot')).toBeDefined();
      expect(screen.getByText('Local K3s (Room 1 NAT)')).toBeDefined();
      expect(screen.getAllByText('185').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/Squid: 142/i)).toBeDefined();
    });
  });

  it('supports Click-to-Correlate and opens Side Drawer with Bastion Runbook on row click', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: mockAdminUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/monitor?tab=logs']}>
          <Routes>
            <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
              <Route path="/admin/monitor" element={<AdminMonitorPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('anon_8f92a1b7')).toBeDefined();
    });

    // Click on anonId badge to correlate
    const anonBadge = screen.getByText('anon_8f92a1b7');
    fireEvent.click(anonBadge);

    // Verify correlation message appears in GlobalFilterBar
    await waitFor(() => {
      expect(screen.getByText(/Correlating events for user pseudonym:/i)).toBeDefined();
    });

    // Wait for log row to be re-rendered after correlation
    await waitFor(() => {
      expect(screen.getByText(/TCP_DENIED to http:\/\/crypto-miner.xyz/i)).toBeDefined();
    });

    // Click on the log row to open Side Drawer
    const logRow = screen.getByText(/TCP_DENIED to http:\/\/crypto-miner.xyz/i);
    fireEvent.click(logRow);

    // Verify Side Drawer opened
    await waitFor(() => {
      expect(screen.getByText('Event Detail & Bastion Runbook')).toBeDefined();
      expect(screen.getByText('Bastion Host Diagnostic Runbook (Copy-Only)')).toBeDefined();
      expect(screen.getByText(/Inspect Squid Proxy Access Logs/i)).toBeDefined();
      expect(screen.getByText(/Standardized JSON Schema \(CamelCase\)/i)).toBeDefined();
    });
  });

  it('renders Billing Summary and triggers Executive CSV & PDF Export downloads', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: mockAdminUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/monitor?tab=billing']}>
          <Routes>
            <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
              <Route path="/admin/monitor" element={<AdminMonitorPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('CS101 - Intro to CS')).toBeDefined();
      expect(screen.getByText('CS202 - Algorithms')).toBeDefined();
      expect(screen.getByText('Strict Anonymity Verified')).toBeDefined();
    });

    // Test Export buttons
    const exportCsvBtn = screen.getByRole('button', { name: /Export CSV/i });
    fireEvent.click(exportCsvBtn);

    await waitFor(() => {
      expect(billingService.downloadReport).toHaveBeenCalledWith('csv', expect.anything());
    });

    const exportPdfBtn = screen.getByRole('button', { name: /Export PDF/i });
    fireEvent.click(exportPdfBtn);

    await waitFor(() => {
      expect(billingService.downloadReport).toHaveBeenCalledWith('pdf', expect.anything());
    });
  });
});
