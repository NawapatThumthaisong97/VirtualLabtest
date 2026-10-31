import { colors, eventColors } from './theme';
import type { ClassEvent } from './types';
import { MONTHS, WEEKDAYS_SHORT, monthGrid, sameDay, to12h } from './date';
import { ChevronLeft, ChevronRight } from './icons';
import PrimaryButton from './PrimaryButton';

interface Props {
  year: number;
  month: number;
  selected: Date;
  today: Date;
  selectedEvents: ClassEvent[];
  unread: number;
  onPrev: () => void;
  onNext: () => void;
  onSelect: (d: Date) => void;
  onCreate: () => void;
  onRequests: () => void;
}

const card = { background: '#fff', borderRadius: '0 0 14px 14px', fontSize: 11 } as const;

export default function Sidebar({ year, month, selected, today, selectedEvents, unread, onPrev, onNext, onSelect, onCreate, onRequests }: Props) {
  const dates = monthGrid(year, month);
  const title = sameDay(selected, today) ? "Today's Events" : `${selected.getDate()} ${MONTHS[selected.getMonth()]} ${selected.getFullYear()}`;

  return (
    <aside style={{ width: 236, flexShrink: 0, background: colors.pageBg, padding: '28px 20px', display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <PrimaryButton onClick={onCreate}>+ Create new event</PrimaryButton>
        <PrimaryButton onClick={onRequests} style={{ position: 'relative' }}>
          Class Request
          {unread > 0 && (
            <span style={{ position: 'absolute', top: -7, right: -7, minWidth: 18, height: 18, padding: '0 4px', borderRadius: 9, background: colors.danger, color: '#fff', fontSize: 11, fontWeight: 500, lineHeight: '18px', textAlign: 'center', border: `2px solid ${colors.pageBg}` }}>
              {unread}
            </span>
          )}
        </PrimaryButton>
      </div>

      <div style={{ ...card, padding: '16px 14px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 600 }}>{MONTHS[month]} {year}</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={onPrev} aria-label="Previous month" style={iconBtn}><ChevronLeft size={12} /></button>
            <button onClick={onNext} aria-label="Next month" style={iconBtn}><ChevronRight size={12} /></button>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', rowGap: 4, textAlign: 'center' }}>
          {WEEKDAYS_SHORT.map((w) => (
            <span key={w} style={{ color: '#555', paddingBottom: 6 }}>{w}</span>
          ))}
          {dates.map((d) => {
            const inMonth = d.getMonth() === month;
            const isSel = sameDay(d, selected);
            return (
              <button key={d.toISOString()} onClick={() => onSelect(d)} style={{ border: 0, background: 'none', padding: 0, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11 }}>
                <span style={{ minWidth: 20, height: 20, lineHeight: '20px', borderRadius: 4, background: isSel ? colors.selected : 'transparent', color: isSel ? '#fff' : inMonth ? '#333' : '#ccc' }}>
                  {d.getDate()}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ ...card, padding: '16px 14px 18px' }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 12 }}>{title}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {selectedEvents.length === 0 && <span style={{ color: colors.muted }}>No classes scheduled</span>}
          {selectedEvents.map((e) => (
            <div key={e.id} style={{ display: 'flex', gap: 8 }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', marginTop: 5, flexShrink: 0, background: eventColors[e.color].color }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                <span style={{ fontWeight: 600, fontSize: 11 }}>{e.title}</span>
                <span style={{ color: '#666', fontSize: 10 }}>{to12h(e.start)} - {to12h(e.end)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}

const iconBtn = { border: 0, background: 'none', padding: 2, cursor: 'pointer', display: 'flex' } as const;
