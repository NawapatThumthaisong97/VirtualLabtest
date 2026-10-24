import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { colors } from './theme';
import type { EventForm } from './types';
import GradientModal from './GradientModal';
import PrimaryButton from './PrimaryButton';
import { BookIcon, UsersIcon } from './icons';

interface Props {
  open: boolean;
  initial: EventForm;
  onClose: () => void;
  onApprove: (form: EventForm) => void;
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

export default function CreateEventModal({ open, initial, onClose, onApprove }: Props) {
  const [form, setForm] = useState<EventForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const set = (k: keyof EventForm) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <GradientModal open={open} onClose={onClose} icon="/flask.png" title="Class Scheduler">
      <div style={{ padding: '28px 64px 56px', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 48, fontSize: 14 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={labelWrap}>
            <span>Course</span>
            <IconField icon={<BookIcon />}><input value={form.course} onChange={set('course')} style={bare} /></IconField>
          </label>
          <label style={labelWrap}>
            <span>Instructor</span>
            <IconField icon={<UsersIcon />}><input value={form.instructor} onChange={set('instructor')} style={bare} /></IconField>
          </label>
          <label style={labelWrap}>
            <span>Labs</span>
            <IconField><input value={form.lab} onChange={set('lab')} style={bare} /></IconField>
          </label>
          <div style={labelWrap}>
            <span>Classroom</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 24 }}>
              <input aria-label="Room" value={form.room} onChange={set('room')} style={field} />
              <input aria-label="Capacity" value={form.max} onChange={set('max')} style={field} />
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={labelWrap}>
            <span>Date &amp; Time</span>
            <input type="date" value={form.date} onChange={set('date')} style={{ ...field, paddingLeft: 40 }} />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 30, marginTop: 6 }}>
            <input aria-label="Start time" type="time" value={form.start} onChange={set('start')} style={{ ...field, paddingLeft: 40 }} />
            <input aria-label="End time" type="time" value={form.end} onChange={set('end')} style={field} />
          </div>
          <div style={{ flex: 1 }} />
          <PrimaryButton onClick={() => onApprove(form)} style={{ alignSelf: 'flex-end', width: 200, height: 44 }}>
            Approve
          </PrimaryButton>
        </div>
      </div>
    </GradientModal>
  );
}

const labelWrap: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 6, color: colors.text };
