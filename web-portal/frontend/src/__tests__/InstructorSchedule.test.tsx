import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import InstructorSchedulePage from '../pages/InstructorSchedule';
import { bookingService, type BookingItem } from '../services/adminDashboard';
import { courseService } from '../services/course';
import { toISO } from '../components/scheduler/date';

const today = toISO(new Date());

const pendingReq: BookingItem = {
  id: 'b1', status: 'pending', requesterName: 'Kittipong', requesterEmail: 'k@dome.tu.ac.th',
  courseId: 'c1', courseName: 'Software Engineer', labId: 'l1', labTitle: 'OOP with Spring Boot',
  weekday: 2, startTime: '09:00:00', endTime: '12:00:00', validFrom: '2026-11-04', validUntil: '2026-12-30',
  machines: 1, room: 'LC-123', mode: 'onsite', note: null, decisionNote: null, classScheduleId: null,
  slotsCreated: null, mailStatus: null, createdAt: '2026-11-06T10:00:00Z',
};

describe('Instructor Schedule (/instructor/courses/:id/schedule)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(courseService, 'getById').mockResolvedValue({ id: 'c1', code: 'SE301', name: 'Software Engineer' } as never);
    vi.spyOn(bookingService, 'courseCalendar').mockResolvedValue({ month: today.slice(0, 7), events: [
      { id: 's1', title: 'Software Engineer – OOP', date: today, start: '09:00', end: '12:00', room: 'LC-123',
        courseId: 'c1', courseName: 'Software Engineer', labId: 'l1', machines: 1, status: 'scheduled', mode: 'onsite', mine: true },
      { id: 's2', title: 'ไม่ว่าง', date: today, start: '13:00', end: '16:00', room: 'LC-207',
        courseId: 'c9', courseName: 'ไม่ว่าง', labId: null, machines: 2, status: 'scheduled', mode: 'onsite', mine: false },
    ] });
    vi.spyOn(bookingService, 'courseOptions').mockResolvedValue({
      courses: [{ id: 'c1', code: 'SE301', name: 'Software Engineer', instructors: ['Kittipong'] }],
      labs: [{ id: 'l1', courseId: 'c1', title: 'OOP with Spring Boot', hasImage: true }],
      rooms: [{ room: 'LC-123', pcsTotal: 1 }],
    });
    vi.spyOn(bookingService, 'myRequests').mockResolvedValue([pendingReq]);
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/instructor/courses/c1/schedule']}>
          <Routes>
            <Route path="/instructor/courses/:courseId/schedule" element={<InstructorSchedulePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it('shows own classes, other courses only as "ไม่ว่าง", and the pending count on My requests', async () => {
    renderPage();
    expect(await screen.findByText('SE301 : Software Engineer · Schedule')).toBeDefined();
    expect((await screen.findAllByText(/Software Engineer – OOP · LC-123/)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/ไม่ว่าง · LC-207/)).length).toBeGreaterThan(0);
    expect(screen.getByText('My requests').closest('button')!.textContent).toContain('1');
    fireEvent.click(screen.getByText('My requests'));
    expect(await screen.findByText('รออนุมัติ')).toBeDefined();
  });

  it('Send new request: course locked, sends a weekly request', async () => {
    const send = vi.spyOn(bookingService, 'sendRequest').mockResolvedValue(pendingReq);
    renderPage();
    fireEvent.click(await screen.findByText('+ Send new request'));
    expect((await screen.findByLabelText('Course') as HTMLSelectElement).disabled).toBe(true);
    await waitFor(() => expect(screen.getByText('OOP with Spring Boot')).toBeDefined());
    fireEvent.change(screen.getByLabelText('Lab'), { target: { value: 'l1' } });
    fireEvent.change(screen.getByLabelText('Room'), { target: { value: 'LC-123' } });
    fireEvent.change(screen.getByLabelText('Machines'), { target: { value: '1' } });
    fireEvent.click(screen.getByText('Send request'));
    await waitFor(() => expect(send).toHaveBeenCalledWith(expect.objectContaining({
      courseId: 'c1', labId: 'l1', mode: 'onsite', room: 'LC-123', machines: 1, validFrom: today,
      weekday: (new Date().getDay() + 6) % 7,
    })));
    expect(await screen.findByText(/ส่งคำขอแล้ว/)).toBeDefined();
  });
});
