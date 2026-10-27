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

describe('Full-Screen Grafana SIEM Dashboard UI', () => {
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

  it('defaults to Threat Analytics & Charts first and switches to SIEM Command Center on tab click', () => {
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

    const iframe = screen.getByTestId('grafana-siem-fullscreen-iframe') as HTMLIFrameElement;
    expect(iframe.src).toContain('/d/vlab-siem-analytics');

    const commandBtn = screen.getByRole('button', { name: /SIEM Command Center/i });
    fireEvent.click(commandBtn);

    const updatedIframe = screen.getByTestId('grafana-siem-fullscreen-iframe') as HTMLIFrameElement;
    expect(updatedIframe.src).toContain('/d/vlab-siem-5layer');
  });

  it('provides direct launch links to VictoriaLogs, S3 Cold Storage, and Open in Grafana', () => {
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

    expect(screen.getByText('VictoriaLogs')).toBeDefined();
    expect(screen.getByText('S3 Cold Storage')).toBeDefined();
    expect(screen.getByText('Open in Grafana')).toBeDefined();
  });
});
