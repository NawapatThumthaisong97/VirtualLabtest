import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ProtectedRoute from '../components/ProtectedRoute';
import AdminMonitorPage from '../pages/AdminMonitor';
import * as AuthContextModule from '../contexts/AuthContext';
import type { CurrentUser } from '../services/auth';

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

describe('Full-Screen Grafana 5-Layer SIEM Command Center UI', () => {
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
      <MemoryRouter initialEntries={['/admin/monitor']}>
        <Routes>
          <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
            <Route path="/admin/monitor" element={<AdminMonitorPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Access Restricted')).toBeDefined();
    expect(screen.queryByText('Admin Monitor & SIEM Dashboard')).toBeNull();
  });

  it('renders [🔒 READ-ONLY MODE] prominently and guarantees no destructive buttons exist', () => {
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
      <MemoryRouter initialEntries={['/admin/monitor']}>
        <Routes>
          <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
            <Route path="/admin/monitor" element={<AdminMonitorPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getAllByText(/\[🔒 READ-ONLY MODE\]/i).length).toBeGreaterThan(0);

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

  it('renders Full-Screen Grafana 5-Layer SIEM iframe and Layer 1-5 architecture badges', () => {
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
      <MemoryRouter initialEntries={['/admin/monitor']}>
        <Routes>
          <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
            <Route path="/admin/monitor" element={<AdminMonitorPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('L1: Vector + Falco eBPF')).toBeDefined();
    expect(screen.getByText('L2: NATS JetStream + KV')).toBeDefined();
    expect(screen.getByText('L3: ECS + GeoIP + Threat Intel')).toBeDefined();
    expect(screen.getByText('L4: VictoriaLogs + AWS S3 (.parquet)')).toBeDefined();
    expect(screen.getByText('L5: Grafana + Sigma + Fast-Track')).toBeDefined();

    const iframe = screen.getByTestId('grafana-siem-fullscreen-iframe') as HTMLIFrameElement;
    expect(iframe).toBeDefined();
    expect(iframe.src).toContain('/d/vlab-siem-5layer');
  });

  it('provides direct launch links to VictoriaLogs (LogsQL), AWS S3 (.parquet), and Grafana Full Tab', () => {
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
      <MemoryRouter initialEntries={['/admin/monitor']}>
        <Routes>
          <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
            <Route path="/admin/monitor" element={<AdminMonitorPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('VictoriaLogs (LogsQL)')).toBeDefined();
    expect(screen.getByText('AWS S3 (.parquet)')).toBeDefined();
    expect(screen.getByText('Open Grafana Tab')).toBeDefined();

    const refreshBtn = screen.getByRole('button', { name: /Refresh SIEM/i });
    fireEvent.click(refreshBtn);
    expect(screen.getByTestId('grafana-siem-fullscreen-iframe')).toBeDefined();
  });
});
