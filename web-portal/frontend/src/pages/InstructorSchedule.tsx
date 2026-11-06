/**
 * Schedule ของอาจารย์ (/instructor/courses/:courseId/schedule) — docs/INSTRUCTOR_SCHEDULE.md
 * ปฏิทินทุกห้อง (วิชาอื่นแสดงแค่ "ไม่ว่าง") + คำขอที่รออนุมัติของวิชานี้ + Send new request → admin อนุมัติ
 * ใช้ Sidebar / MonthCalendar / CreateEventModal ชุดเดียวกับหน้า admin (/admin/scheduler)
 */
import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { colors } from '../components/scheduler/theme';
import type { ClassEvent, EventForm } from '../components/scheduler/types';
import { fromISO, toISO } from '../components/scheduler/date';
import DashboardHeader from '../components/admin/DashboardHeader';
import Sidebar from '../components/scheduler/Sidebar';
import MonthCalendar from '../components/scheduler/MonthCalendar';
import CreateEventModal from '../components/scheduler/CreateEventModal';
import MyRequestsModal from '../components/scheduler/MyRequestsModal';
import { courseService } from '../services/course';
import { bookingService, type BookingRequestBody } from '../services/adminDashboard';

const monthKey = (y: number, m: number) => `${y}-${String(m + 1).padStart(2, '0')}`;

const blankForm = (courseId: string, date: Date): EventForm => {
  const until = new Date(date);
  until.setDate(until.getDate() + 7 * 15);
  return { courseId, labId: '', mode: 'onsite', room: '', machines: 0, date: toISO(date), start: '13:00', end: '16:00', until: toISO(until), note: '' };
};

/** ฟอร์ม → คำขอ: ทุกสัปดาห์วันเดียวกับคาบแรก ตั้งแต่คาบแรกถึง until */
const toRequestBody = (f: EventForm): BookingRequestBody => ({
  courseId: f.courseId, labId: f.labId, mode: f.mode,
  weekday: (fromISO(f.date).getDay() + 6) % 7,
  startTime: f.start, endTime: f.end, validFrom: f.date, validUntil: f.until,
  ...(f.mode === 'onsite' ? { room: f.room, machines: f.machines } : {}),
  note: f.note || undefined,
});

const apiError = (e: unknown) =>
  (e as { response?: { data?: { message?: string } } }).response?.data?.message ?? 'ส่งคำขอไม่สำเร็จ';

export default function InstructorSchedulePage() {
  const { courseId = '' } = useParams<{ courseId: string }>();
  const today = useMemo(() => new Date(), []);
  const qc = useQueryClient();
  const [view, setView] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [selected, setSelected] = useState(today);
  const [formOpen, setFormOpen] = useState(false);
  const [requestsOpen, setRequestsOpen] = useState(false);
  const [form, setForm] = useState<EventForm>(() => blankForm(courseId, today));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const course = useQuery({ queryKey: ['course', courseId], queryFn: () => courseService.getById(courseId), enabled: Boolean(courseId) });
  const calendar = useQuery({
    queryKey: ['course-schedule', courseId, 'calendar', monthKey(view.year, view.month)],
    queryFn: () => bookingService.courseCalendar(courseId, monthKey(view.year, view.month)),
    enabled: Boolean(courseId),
  });
  const options = useQuery({ queryKey: ['course-schedule', courseId, 'options'], queryFn: () => bookingService.courseOptions(courseId), enabled: Boolean(courseId) });
  const mine = useQuery({ queryKey: ['course-schedule', courseId, 'mine'], queryFn: () => bookingService.myRequests(courseId), enabled: Boolean(courseId) });

  const events: ClassEvent[] = useMemo(
    () => (calendar.data?.events ?? []).map((e) => {
      const busy = e.mine === false;
      const where = e.mode === 'online' ? 'Online' : e.room ?? '';
      const title = busy ? `ไม่ว่าง · ${where}` : `${e.title}${where ? ` · ${where}` : ''}${e.pending ? ' · Pending' : ''}`;
      return {
        id: `${e.id}-${e.date}`, title, date: e.date, start: e.start, end: e.end, color: 'cyan' as const,
        courseId: e.courseId, labId: e.labId, mode: e.mode, room: e.room, machines: e.machines,
        busy, pending: e.pending,
      };
    }),
    [calendar.data],
  );
  const eventsByDate = useMemo(() => {
    const map: Record<string, ClassEvent[]> = {};
    for (const e of events) (map[e.date] ??= []).push(e);
    return map;
  }, [events]);

  const send = useMutation({
    mutationFn: (f: EventForm) => bookingService.sendRequest(toRequestBody(f)),
    onSuccess: (_b, f) => {
      setFormOpen(false);
      setError(null);
      setNotice('ส่งคำขอแล้ว — รอ admin อนุมัติ (ดูสถานะได้ที่ My requests)');
      qc.invalidateQueries({ queryKey: ['course-schedule', courseId] });
      const d = fromISO(f.date);
      setSelected(d);
      setView({ year: d.getFullYear(), month: d.getMonth() });
    },
    onError: (e) => setError(apiError(e)),
  });

  const shift = (n: number) =>
    setView((v) => {
      const d = new Date(v.year, v.month + n, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  const select = (d: Date) => {
    setSelected(d);
    if (d.getMonth() !== view.month || d.getFullYear() !== view.year) setView({ year: d.getFullYear(), month: d.getMonth() });
  };
  const openForm = () => {
    setError(null);
    setForm(blankForm(courseId, selected));
    setFormOpen(true);
  };

  const pendingCount = (mine.data ?? []).filter((b) => b.status === 'pending').length;
  const c = course.data;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 'calc(100vh - 3.5rem)', fontFamily: "'Inter', sans-serif", color: colors.text }}>
      <DashboardHeader
        title={c ? `${c.code} : ${c.name} · Schedule` : 'Schedule'}
        features={[{ label: 'Back to course', to: `/instructor/courses/${courseId}` }]}
      />

      {(notice || calendar.isError || options.isError) && (
        <div style={{ background: notice ? '#EEF5E6' : '#EFC2BD', color: colors.text, padding: '8px 24px', fontSize: 13 }}>
          {notice ?? 'ดึงข้อมูลไม่สำเร็จ'}
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <Sidebar
          year={view.year}
          month={view.month}
          selected={selected}
          today={today}
          selectedEvents={eventsByDate[toISO(selected)] ?? []}
          unread={pendingCount}
          onPrev={() => shift(-1)}
          onNext={() => shift(1)}
          onSelect={select}
          onCreate={openForm}
          onRequests={() => setRequestsOpen(true)}
          createLabel="+ Send new request"
          requestsLabel="My requests"
        />
        <MonthCalendar
          year={view.year}
          month={view.month}
          selected={selected}
          today={today}
          eventsByDate={eventsByDate}
          onPrev={() => shift(-1)}
          onNext={() => shift(1)}
          onToday={() => select(today)}
          onSelect={select}
        />
      </div>

      <CreateEventModal
        open={formOpen}
        initial={form}
        options={options.data}
        error={error}
        busy={send.isPending}
        onClose={() => setFormOpen(false)}
        onApprove={(f) => send.mutate(f)}
        submitLabel="Send request"
        lockCourse
      />
      <MyRequestsModal open={requestsOpen} items={mine.data ?? []} onClose={() => setRequestsOpen(false)} />
    </div>
  );
}
