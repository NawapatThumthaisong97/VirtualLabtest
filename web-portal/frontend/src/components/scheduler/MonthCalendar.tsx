import { colors, eventColors } from './theme';
import type { ClassEvent } from './types';
import { MONTHS, WEEKDAYS, monthGrid, sameDay, to12h, toISO } from './date';
import { ChevronDown, ChevronLeft, ChevronRight } from './icons';

interface Props {
  year: number;
  month: number;
  selected: Date;
  today: Date;
  eventsByDate: Record<string, ClassEvent[]>;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onSelect: (d: Date) => void;
}

const MAX_CHIPS = 2;
const line = `1px solid ${colors.border}`;

export default function MonthCalendar({ year, month, selected, today, eventsByDate, onPrev, onNext, onToday, onSelect }: Props) {
  const dates = monthGrid(year, month);

  return (
    <main style={{ flex: 1, minWidth: 0, background: '#fff', padding: '28px 48px 40px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', marginBottom: 22 }}>
        <button style={{ justifySelf: 'start', display: 'flex', alignItems: 'center', gap: 8, border: 0, background: colors.pageBg, borderRadius: 6, padding: '6px 10px', fontFamily: 'inherit', fontSize: 11, fontWeight: 600, color: colors.text, cursor: 'pointer' }}>
          Month <ChevronDown />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={onPrev} aria-label="Previous month" style={navBtn}><ChevronLeft /></button>
          <span style={{ fontSize: 15, fontWeight: 600, minWidth: 140, textAlign: 'center' }}>{MONTHS[month]} {year}</span>
          <button onClick={onNext} aria-label="Next month" style={navBtn}><ChevronRight /></button>
        </div>
        <button onClick={onToday} style={{ justifySelf: 'end', border: line, background: '#fff', borderRadius: 6, padding: '6px 12px', fontFamily: 'inherit', fontSize: 11, color: colors.text, cursor: 'pointer' }}>
          Today
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,minmax(0,1fr))' }}>
        {WEEKDAYS.map((w) => (
          <div key={w} style={{ textAlign: 'center', fontSize: 14, fontWeight: 600, paddingBottom: 14 }}>{w}</div>
        ))}
      </div>

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(7,minmax(0,1fr))', gridAutoRows: 'minmax(150px,1fr)', borderTop: line, borderLeft: line }}>
        {dates.map((d) => {
          const inMonth = d.getMonth() === month;
          const isSel = sameDay(d, selected);
          const isToday = sameDay(d, today);
          const events = eventsByDate[toISO(d)] ?? [];
          const shown = events.slice(0, MAX_CHIPS);
          const more = events.length - shown.length;
          const highlight = isSel || isToday;

          return (
            <div key={d.toISOString()} onClick={() => onSelect(d)} style={{ borderRight: line, borderBottom: line, padding: '10px 0 8px', display: 'flex', flexDirection: 'column', gap: 6, cursor: 'pointer', minWidth: 0, background: isSel ? '#FAFBFF' : '#fff' }}>
              <span style={{ alignSelf: 'flex-start', marginLeft: 10, fontSize: 13, minWidth: 26, height: 26, lineHeight: '26px', textAlign: 'center', borderRadius: 4, background: highlight ? colors.selected : 'transparent', color: highlight ? '#fff' : inMonth ? '#555' : '#ccc' }}>
                {String(d.getDate()).padStart(2, '0')}
              </span>
              {shown.map((e) => {
                const c = eventColors[e.color];
                return (
                  <div key={e.id} title={e.title} style={{ ...chip, borderLeft: `2px solid ${c.color}`, background: c.bg, color: c.color }}>
                    {to12h(e.start).replace(':00 ', ' ')} - {e.title}
                  </div>
                );
              })}
              {more > 0 && <div style={{ ...chip, background: colors.pageBg, borderLeft: line, color: colors.text }}>+ {more} More</div>}
            </div>
          );
        })}
      </div>
    </main>
  );
}

const navBtn = { border: 0, background: 'none', padding: 4, cursor: 'pointer', display: 'flex' } as const;
const chip = { fontSize: 12, fontWeight: 600, padding: '6px 8px', marginRight: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } as const;
