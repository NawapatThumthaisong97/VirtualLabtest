/**
 * Class Schedule (/admin/scheduler) — UI จาก ClassScheduler.zip (Pete ออกแบบ)
 * ยังไม่ต่อ API: ปฏิทิน / คำขอจองเป็นข้อมูลตัวอย่าง (data.ts) — flow จองห้อง + เมลอนุมัติออกแบบใน docs/ADMIN_MONITOR.md PR 6
 */
import { useCallback, useMemo, useState } from 'react';
import { colors } from '../components/scheduler/theme';
import type { ClassEvent, ClassRequest, EventForm } from '../components/scheduler/types';
import { seedEvents, seedRequests } from '../components/scheduler/data';
import { fromISO, nextWeekday, toISO, to12h } from '../components/scheduler/date';
import Navbar from '../components/admin/Navbar';
import Sidebar from '../components/scheduler/Sidebar';
import MonthCalendar from '../components/scheduler/MonthCalendar';
import CreateEventModal from '../components/scheduler/CreateEventModal';
import ClassRequestModal from '../components/scheduler/ClassRequestModal';

const blankForm = (date: Date): EventForm => ({
  course: 'Software Engineer',
  instructor: 'Proffresor Thomas young',
  lab: 'Sprint Boots for Java Development',
  room: 'LC-213',
  max: 'Max 60 Machines',
  date: toISO(date),
  start: '08:30',
  end: '09:30',
});

export default function ClassSchedulePage() {
  const today = useMemo(() => new Date(), []);
  const [view, setView] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [selected, setSelected] = useState(today);
  const [events, setEvents] = useState<ClassEvent[]>(() => seedEvents(today));
  const [requests, setRequests] = useState<ClassRequest[]>(seedRequests);
  const [seen, setSeen] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [requestsOpen, setRequestsOpen] = useState(false);
  const [form, setForm] = useState<EventForm>(() => blankForm(today));
  const [fromRequest, setFromRequest] = useState<number | null>(null);

  const eventsByDate = useMemo(() => {
    const map: Record<string, ClassEvent[]> = {};
    for (const e of events) (map[e.date] ??= []).push(e);
    return map;
  }, [events]);

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
    setFromRequest(null);
    setForm(blankForm(selected));
    setCreateOpen(true);
  };

  const closeRequests = useCallback(() => {
    setRequestsOpen(false);
    setSeen(true);
  }, []);

  /** Detail → close requests, open Create with the teacher's data prefilled. */
  const openFromRequest = (r: ClassRequest) => {
    const [range, dayName] = r.date.split(' ');
    const [start, end] = range.split('-');
    setForm({
      course: r.course,
      instructor: r.requester,
      lab: r.lab,
      room: r.room,
      max: r.max,
      date: toISO(nextWeekday(dayName, today)),
      start,
      end,
    });
    setFromRequest(r.id);
    setRequestsOpen(false);
    setSeen(true);
    setCreateOpen(true);
  };

  const approve = (f: EventForm) => {
    if (!f.date) return;
    const title = f.lab ? `${f.course} – ${f.lab}` : f.course;
    setEvents((list) => [...list, { id: `ev-${Date.now()}`, title, date: f.date, start: f.start, end: f.end, color: 'purple' }]);
    if (fromRequest != null) setRequests((list) => list.filter((x) => x.id !== fromRequest));
    setCreateOpen(false);
    select(fromISO(f.date));
  };

  const unread = seen ? 0 : requests.filter((r) => r.isNew).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', fontFamily: "'Inter', sans-serif", color: colors.text }}>
      <Navbar />

      <div style={{ background: colors.primary, display: 'flex', alignItems: 'center', padding: '0 24px', color: '#fff' }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 200, letterSpacing: -0.2, padding: '18px 0' }}>Class Schedule</h1>
      </div>

      <div style={{ background: '#FDF1E3', color: '#8a5a1f', padding: '8px 24px', fontSize: 13 }}>
        ข้อมูลตัวอย่าง — ยังไม่ต่อระบบจองห้อง (กด Approve แล้วยังไม่บันทึก / ไม่ส่งเมล)
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <Sidebar
          year={view.year}
          month={view.month}
          selected={selected}
          today={today}
          selectedEvents={eventsByDate[toISO(selected)] ?? []}
          unread={unread}
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

      <CreateEventModal open={createOpen} initial={form} onClose={() => setCreateOpen(false)} onApprove={approve} />
      <ClassRequestModal open={requestsOpen} requests={requests} showNew={!seen} onClose={closeRequests} onOpenDetail={openFromRequest} />
    </div>
  );
}

// Re-exported for consumers that want to format times the same way.
export { to12h };
