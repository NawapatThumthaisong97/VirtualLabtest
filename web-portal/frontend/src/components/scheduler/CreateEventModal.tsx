import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { colors } from './theme';
import type { EventForm } from './types';
import type { SchedulerOptions } from '../../services/adminDashboard';
import GradientModal from './GradientModal';
import PrimaryButton from './PrimaryButton';
import { BookIcon, UsersIcon } from './icons';

interface Props {
  open: boolean;
  initial: EventForm;
  options: SchedulerOptions | undefined;
  /** ข้อความ error จาก API (ห้องชน / เครื่องไม่พอ ฯลฯ) */
  error: string | null;
  busy: boolean;
  onClose: () => void;
  onApprove: (form: EventForm) => void;
  /** มีเฉพาะตอนเปิดจากคำขออาจารย์ */
  onReject?: (form: EventForm, reason: string) => void;
}

const field: CSSProperties = {
  height: 44,
  border: `1px solid ${colors.inputBorder}`,
  borderRadius: 8,
  padding: '0 16px',
  outline: 'none',
  fontFamily: 'inherit',
  fontSize: 14,
  color: colors.text,
  minWidth: 0,
  width: '100%',
  background: '#fff',
};

function IconField({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 22, height: 44, border: `1px solid ${colors.inputBorder}`, borderRadius: 8, padding: icon ? '0 16px' : '0 16px 0 56px' }}>
      {icon}
      {children}
    </div>
  );
}

const bare: CSSProperties = { flex: 1, minWidth: 0, border: 0, outline: 'none', fontFamily: 'inherit', fontSize: 14, color: colors.text, background: 'transparent' };

export default function CreateEventModal({ open, initial, options, error, busy, onClose, onApprove, onReject }: Props) {
  const [form, setForm] = useState<EventForm>(initial);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  useEffect(() => {
    setForm(initial);
    setRejecting(false);
    setReason('');
  }, [initial]);

  const set = (k: keyof EventForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: k === 'machines' ? Number(e.target.value) : e.target.value }));

  const course = options?.courses.find((c) => c.id === form.courseId);
  const labs = (options?.labs ?? []).filter((l) => l.courseId === form.courseId);
  const room = options?.rooms.find((r) => r.room === form.room);
  const fromRequest = Boolean(form.bookingId);
  const ready = form.courseId && form.labId && form.room && form.machines > 0 && form.date && form.until;

  return (
    <GradientModal open={open} onClose={onClose} icon="/flask.png" title="Class Scheduler">
      <div style={{ padding: '28px 64px 40px', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 48, fontSize: 14 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={labelWrap}>
            <span>Course</span>
            <IconField icon={<BookIcon />}>
              <select
                aria-label="Course"
                value={form.courseId}
                disabled={fromRequest}
                onChange={(e) => setForm((f) => ({ ...f, courseId: e.target.value, labId: '' }))}
                style={bare}
              >
                <option value="">เลือกวิชา</option>
                {(options?.courses ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.code} · {c.name}</option>
                ))}
              </select>
            </IconField>
          </label>
          <label style={labelWrap}>
            <span>Instructor</span>
            <IconField icon={<UsersIcon />}>
              <input aria-label="Instructor" readOnly value={course?.instructors.join(', ') || '-'} style={bare} />
            </IconField>
          </label>
          <label style={labelWrap}>
            <span>Labs</span>
            <IconField>
              <select aria-label="Lab" value={form.labId} onChange={set('labId')} style={bare}>
                <option value="">เลือก lab</option>
                {labs.map((l) => (
                  <option key={l.id} value={l.id} disabled={!l.hasImage}>
                    {l.title}{l.hasImage ? '' : ' (ยังไม่มี image)'}
                  </option>
                ))}
              </select>
            </IconField>
          </label>
          <div style={labelWrap}>
            <span>Classroom</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 24 }}>
              <select aria-label="Room" value={form.room} onChange={set('room')} style={field}>
                <option value="">เลือกห้อง</option>
                {(options?.rooms ?? []).map((r) => (
                  <option key={r.room} value={r.room}>{r.room} ({r.pcsTotal} เครื่อง)</option>
                ))}
              </select>
              <input
                aria-label="Machines"
                type="number"
                min={1}
                max={room?.pcsTotal}
                value={form.machines || ''}
                onChange={set('machines')}
                placeholder={room ? `Max ${room.pcsTotal} Machines` : 'Machines'}
                style={field}
              />
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={labelWrap}>
            <span>Date &amp; Time (คาบแรก)</span>
            <input aria-label="First date" type="date" value={form.date} onChange={set('date')} style={{ ...field, paddingLeft: 40 }} />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 30, marginTop: 6 }}>
            <input aria-label="Start time" type="time" value={form.start} onChange={set('start')} style={{ ...field, paddingLeft: 40 }} />
            <input aria-label="End time" type="time" value={form.end} onChange={set('end')} style={field} />
          </div>
          <label style={labelWrap}>
            <span>ทุกสัปดาห์ถึงวันที่</span>
            <input aria-label="Repeat until" type="date" min={form.date} value={form.until} onChange={set('until')} style={{ ...field, paddingLeft: 40 }} />
          </label>
          {rejecting && (
            <input aria-label="Reject reason" autoFocus value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="เหตุผลที่ไม่อนุมัติ (ส่งในเมลถึงอาจารย์)" style={field} />
          )}
          {error && <div role="alert" style={{ color: colors.danger, fontSize: 12 }}>{error}</div>}
          <div style={{ flex: 1 }} />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            {fromRequest && onReject && (
              <button
                disabled={busy || (rejecting && !reason.trim())}
                onClick={() => (rejecting ? onReject(form, reason.trim()) : setRejecting(true))}
                style={{ height: 44, padding: '0 22px', borderRadius: 8, border: `1px solid ${colors.danger}`, background: '#fff', color: colors.danger, fontFamily: 'inherit', fontSize: 14, cursor: 'pointer' }}
              >
                {rejecting ? 'Confirm reject' : 'Reject'}
              </button>
            )}
            {!rejecting && (
              <PrimaryButton onClick={() => ready && !busy && onApprove(form)} style={{ width: 200, height: 44, opacity: ready && !busy ? 1 : 0.6 }}>
                {busy ? 'Saving…' : 'Approve'}
              </PrimaryButton>
            )}
          </div>
        </div>
      </div>
    </GradientModal>
  );
}

const labelWrap: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 6, color: colors.text };
