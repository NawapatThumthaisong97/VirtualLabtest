import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ClassSchedulePage from '../pages/ClassSchedule';
import * as AuthContextModule from '../contexts/AuthContext';
import { bookingService, type BookingItem } from '../services/adminDashboard';

const booking: BookingItem = {
  id: 'b1', status: 'pending', requesterName: 'Dr. Napat Srisuk', requesterEmail: 'napat@dome.tu.ac.th',
  courseId: 'c1', courseName: 'Web Development', labId: 'l1', labTitle: 'React Fundamentals',
  weekday: 2, startTime: '09:00:00', endTime: '12:00:00', validFrom: '2026-11-02', validUntil: '2027-02-24',
  machines: 25, room: 'LC-123', note: null, decisionNote: null, classScheduleId: null, slotsCreated: null,
  mailStatus: null, createdAt: '2026-10-24T10:00:00Z',
};

describe('ClassSchedule (/admin/scheduler)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'u1', email: 'admin@dome.tu.ac.th', name: 'Admin', studentId: null, role: 'admin' },
      isLoading: false, isAuthenticated: true, login: vi.fn(), loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(), logout: vi.fn(), refreshUser: vi.fn(),
    });
    vi.spyOn(bookingService, 'getCalendar').mockResolvedValue({ month: '2026-11', events: [] });
    vi.spyOn(bookingService, 'getPending').mockResolvedValue({ items: [booking], pendingCount: 1 });
    vi.spyOn(bookingService, 'getOptions').mockResolvedValue({
      courses: [{ id: 'c1', code: 'CN201', name: 'Web Development', instructors: ['Dr. Napat Srisuk'] }],
      labs: [{ id: 'l1', courseId: 'c1', title: 'React Fundamentals', hasImage: true },
             { id: 'l2', courseId: 'c1', title: 'Draft lab', hasImage: false }],
      rooms: [{ room: 'LC-123', pcsTotal: 30 }],
    });
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><ClassSchedulePage /></MemoryRouter>
      </QueryClientProvider>,
    );

  it('badge = pending count; Detail opens the form filled from the real request', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Class Request').closest('button')!.textContent).toContain('1'));
    fireEvent.click(screen.getByText('Class Request'));
    fireEvent.click(await screen.findByLabelText('Open request from Dr. Napat Srisuk'));
    expect((screen.getByLabelText('Room') as HTMLSelectElement).value).toBe('LC-123');
    expect((screen.getByLabelText('Repeat until') as HTMLInputElement).value).toBe('2027-02-24');
    expect((screen.getByLabelText('First date') as HTMLInputElement).value).toBe('2026-11-04');   // พุธแรกตั้งแต่ 2 พ.ย.
    expect((screen.getByLabelText('Instructor') as HTMLInputElement).value).toBe('Dr. Napat Srisuk');
    expect(screen.getByText('Draft lab (ยังไม่มี image)')).toBeDefined();
  });

  it('Approve sends the form; room conflict from API is shown', async () => {
    const approve = vi.spyOn(bookingService, 'approve').mockRejectedValue({
      response: { data: { message: 'ห้อง LC-123 มีคาบ Software Engineering อยู่แล้ว' } },
    });
    renderPage();
    fireEvent.click(await screen.findByText('Class Request'));
    fireEvent.click(await screen.findByLabelText('Open request from Dr. Napat Srisuk'));
    fireEvent.click(screen.getByText('Approve'));
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(approve).toHaveBeenCalledWith('b1', expect.objectContaining({
      room: 'LC-123', machines: 25, firstDate: '2026-11-04', startTime: '09:00', endTime: '12:00', until: '2027-02-24',
    }));
  });

  it('Reject asks for a reason then sends it', async () => {
    const reject = vi.spyOn(bookingService, 'reject').mockResolvedValue({ ...booking, status: 'rejected' });
    renderPage();
    fireEvent.click(await screen.findByText('Class Request'));
    fireEvent.click(await screen.findByLabelText('Open request from Dr. Napat Srisuk'));
    fireEvent.click(screen.getByText('Reject'));
    fireEvent.change(screen.getByLabelText('Reject reason'), { target: { value: 'ห้องเต็ม' } });
    fireEvent.click(screen.getByText('Confirm reject'));
    await waitFor(() => expect(reject).toHaveBeenCalledWith('b1', 'ห้องเต็ม'));
  });
});
