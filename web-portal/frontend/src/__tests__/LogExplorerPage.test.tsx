import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import LogExplorerPage from '../pages/LogExplorerPage';
import * as AuthContextModule from '../contexts/AuthContext';
import { adminLogService, type LogList } from '../services/adminDashboard';

const logs: LogList = {
  total: 1,
  items: [{ id: 'l1', timestamp: '2026-10-24T12:12:00Z', severity: 'WARNING', category: 'CLUSTER', eventType: 'NODE_NOT_READY',
            source: 'worker-pete', message: 'Node worker-pete NotReady', anonId: null, room: 'LC-123', metadata: { node: 'worker-pete' } }],
};

describe('LogExplorerPage (/admin/logs)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    try { localStorage.clear(); } catch { /* */ }
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'u1', email: 'admin@dome.tu.ac.th', name: 'Admin', studentId: null, role: 'admin' },
      isLoading: false, isAuthenticated: true, login: vi.fn(), loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(), logout: vi.fn(), refreshUser: vi.fn(),
    });
    vi.spyOn(adminLogService, 'histogram').mockResolvedValue({
      start: '2026-10-21T12:00:00Z', end: '2026-10-24T12:00:00Z', bucketHours: 2,
      buckets: [{ t: '2026-10-24T10:00:00Z', count: 1 }], byType: { NODE_NOT_READY: 1, POD_EVENT: 5 },
    });
    vi.spyOn(adminLogService, 'list').mockResolvedValue(logs);
  });

  const renderPage = () => render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><LogExplorerPage /></MemoryRouter>
    </QueryClientProvider>,
  );

  it('shows logs with default fields; event filter lists counts and refetches', async () => {
    renderPage();
    expect(await screen.findByText('Node worker-pete NotReady')).toBeDefined();
    expect(screen.getAllByText('Entity Type')).toHaveLength(2);   // chip + หัวคอลัมน์
    expect(screen.getByText('Node')).toBeDefined();
    fireEvent.change(screen.getByLabelText('Event'), { target: { value: 'POD_EVENT' } });
    await waitFor(() => expect(adminLogService.list).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: 'POD_EVENT' }), 20, 0));
    expect(screen.getByText('POD_EVENT (5)')).toBeDefined();
  });

  it('fields can be removed / added; row expands to full JSON', async () => {
    renderPage();
    await screen.findByText('Node worker-pete NotReady');
    fireEvent.click(screen.getByLabelText('Remove Entity Type'));
    expect(screen.queryByText('Node')).toBeNull();
    fireEvent.change(screen.getByLabelText('Add field'), { target: { value: 'room' } });
    expect(screen.getByText('LC-123')).toBeDefined();
    fireEvent.click(screen.getByText('Node worker-pete NotReady'));
    expect(screen.getByText(/"node": "worker-pete"/)).toBeDefined();
  });
});
