/**
 * Class Schedule (/admin/scheduler) — UI จาก ClassScheduler.zip (Pete ออกแบบ)
 * ปฏิทิน = คาบจริง (class_slots), Class Request = คำขอ pending ของอาจารย์ (badge = จำนวน pending)
 * Approve → คาบทุกสัปดาห์ถึงวันที่เลือก + เมลแจ้งอาจารย์ / Reject + เหตุผล (docs/ADMIN_MONITOR.md PR 6)
 */
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { colors, type EventColor } from '../components/scheduler/theme';
import type { ClassEvent, ClassRequest, EventForm } from '../components/scheduler/types';
import { fromISO, toISO, WEEKDAYS } from '../components/scheduler/date';
import Navbar from '../components/admin/Navbar';
import Sidebar from '../components/scheduler/Sidebar';
import MonthCalendar from '../components/scheduler/MonthCalendar';
import CreateEventModal from '../components/scheduler/CreateEventModal';
import ClassRequestModal from '../components/scheduler/ClassRequestModal';
import { bookingService, type BookingItem, type ScheduleFormBody } from '../services/adminDashboard';

const PALETTE: EventColor[] = ['purple', 'orange', 'cyan', 'green', 'blue'];
/** สีคงที่ต่อวิชา */
const colorOf = (courseId: string) =>
  PALETTE[[...courseId].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % PALETTE.length];

const hhmm = (t: string) => t.slice(0, 5);
const monthKey = (y: number, m: number) => `${y}-${String(m + 1).padStart(2, '0')}`;

const blankForm = (date: Date): EventForm => {
  const until = new Date(date);
  until.setDate(until.getDate() + 7 * 15);
  return { courseId: '', labId: '', room: '', machines: 0, date: toISO(date), start: '13:00', end: '16:00', until: toISO(until), note: '' };
};

/** คำขอ → ฟอร์ม: คาบแรก = วันในสัปดาห์ที่ขอ ตั้งแต่ validFrom */
const formFromBooking = (b: BookingItem): EventForm => {
  const first = fromISO(b.validFrom);
  first.setDate(first.getDate() + ((b.weekday - ((first.getDay() + 6) % 7) + 7) % 7));
  return {
    bookingId: b.id, courseId: b.courseId, labId: b.labId, room: b.room ?? '', machines: b.machines,
    date: toISO(first), start: hhmm(b.startTime), end: hhmm(b.endTime), until: b.validUntil, note: '',
  };
};

const toBody = (f: EventForm): ScheduleFormBody => ({
  courseId: f.courseId, labId: f.labId, room: f.room, machines: f.machines, firstDate: f.date,
  startTime: f.start, endTime: f.end, until: f.until, note: f.note || undefined,
});

const apiError = (e: unknown) =>
  (e as { response?: { data?: { message?: string } } }).response?.data?.message ?? 'บันทึกไม่สำเร็จ';

export default function ClassSchedulePage() {
  const today = useMemo(() => new Date(), []);
  const qc = useQueryClient();
  const [view, setView] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [selected, setSelected] = useState(today);
  const [createOpen, setCreateOpen] = useState(false);
  const [requestsOpen, setRequestsOpen] = useState(false);
  const [form, setForm] = useState<EventForm>(() => blankForm(today));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const calendar = useQuery({
    queryKey: ['scheduler', 'calendar', monthKey(view.year, view.month)],
    queryFn: () => bookingService.getCalendar(monthKey(view.year, view.month)),
  });
  const pending = useQuery({ queryKey: ['scheduler', 'pending'], queryFn: bookingService.getPending, refetchInterval: 30_000 });
  const options = useQuery({ queryKey: ['scheduler', 'options'], queryFn: bookingService.getOptions });

  const events: ClassEvent[] = useMemo(
    () => (calendar.data?.events ?? []).map((e) => ({
      id: e.id, title: e.room ? `${e.title} · ${e.room}` : e.title, date: e.date, start: e.start, end: e.end,
      color: colorOf(e.courseId),
    })),
    [calendar.data],
  );
  const eventsByDate = useMemo(() => {
    const map: Record<string, ClassEvent[]> = {};
    for (const e of events) (map[e.date] ??= []).push(e);
    return map;
  }, [events]);

  const bookings = pending.data?.items ?? [];
  const requests: ClassRequest[] = bookings.map((b) => ({
    id: b.id, requester: b.requesterName, purpose: `${b.courseName} – ${b.labTitle}`, course: b.courseName,
    lab: b.labTitle, room: b.room ?? '-', max: `${b.machines} Machines`,
    date: `${hhmm(b.startTime)}-${hhmm(b.endTime)} ${WEEKDAYS[b.weekday]}`, isNew: true,
  }));

  const done = (message: string, firstDate?: string) => {
    setCreateOpen(false);
    setError(null);
    setNotice(message);
    qc.invalidateQueries({ queryKey: ['scheduler'] });
    if (firstDate) select(fromISO(firstDate));
  };

  const approve = useMutation({
    mutationFn: (f: EventForm) => (f.bookingId ? bookingService.approve(f.bookingId, toBody(f)) : bookingService.create(toBody(f))),
    onSuccess: (b, f) => done(`จองแล้ว ${b.slotsCreated ?? 0} คาบ — ส่งเมลแจ้งอาจารย์`, f.date),
    onError: (e) => setError(apiError(e)),
  });
  const reject = useMutation({
    mutationFn: ({ f, reason }: { f: EventForm; reason: string }) => bookingService.reject(f.bookingId!, reason),
    onSuccess: () => done('ไม่อนุมัติแล้ว — ส่งเมลแจ้งอาจารย์พร้อมเหตุผล'),
    onError: (e) => setError(apiError(e)),
  });

  const shift = (n: number) =>
    setView((v) => {
      const d = new Date(v.year, v.month + n, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });

  const select = (d: Date) => {
    setSelected(d);
    setView({ year: d.getFullYear(), month: d.getMonth() });
  };

  const openCreate = () => {
    setError(null);
    setForm(blankForm(selected));
    setCreateOpen(true);
  };

  /** Detail → ปิดรายการคำขอ เปิดฟอร์มที่กรอกจากคำขอ */
  const openFromRequest = (r: ClassRequest) => {
    const b = bookings.find((x) => x.id === r.id);
    if (!b) return;
    setError(null);
    setForm(formFromBooking(b));
    setRequestsOpen(false);
    setCreateOpen(true);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', fontFamily: "'Inter', sans-serif", color: colors.text }}>
      <Navbar />

      <div style={{ background: colors.primary, display: 'flex', alignItems: 'center', padding: '0 24px', color: '#fff' }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 200, letterSpacing: -0.2, padding: '18px 0' }}>Class Schedule</h1>
      </div>

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
          unread={pending.data?.pendingCount ?? 0}
          onPrev={() => shift(-1)}
          onNext={() => shift(1)}
          onSelect={select}
          onCreate={openCreate}
          onRequests={() => setRequestsOpen(true)}
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
        open={createOpen}
        initial={form}
        options={options.data}
        error={error}
        busy={approve.isPending || reject.isPending}
        onClose={() => setCreateOpen(false)}
        onApprove={(f) => approve.mutate(f)}
        onReject={(f, reason) => reject.mutate({ f, reason })}
      />
      <ClassRequestModal open={requestsOpen} requests={requests} showNew onClose={() => setRequestsOpen(false)} onOpenDetail={openFromRequest} />
    </div>
  );
}
