import { colors } from './theme';
import type { RoomMachine } from '../../services/adminDashboard';

/** แถวละ 9 เครื่องเหมือนห้องแลปจริง — มีเครื่องเดียวก็ยังกว้างเท่าเดิม ไม่ยืดเต็มแถว */
const PER_ROW = 9;

const tileColor = (m: RoomMachine) => (!m.ready ? '#E3E3E3' : m.inUse ? '#AFC8E8' : colors.cellGreen);
const tileLabel = (m: RoomMachine) => (!m.ready ? 'ออฟไลน์' : m.inUse ? 'มีคนใช้' : 'ว่าง');

const legend = [
  { label: 'ว่าง', color: colors.cellGreen },
  { label: 'มีคนใช้', color: '#AFC8E8' },
  { label: 'ออฟไลน์', color: '#E3E3E3' },
];

/** ผังห้องแลป 1 ห้อง (แทนแผนผัง infra ตอนกดห้อง) กดชื่อห้องเพื่อกลับ */
export default function RoomFloor({ room, machines, onBack }: { room: string; machines: RoomMachine[]; onBack: () => void }) {
  return (
    <div style={{ height: 340, borderBottom: `1px solid ${colors.border}`, padding: '18px 22px', boxSizing: 'border-box' }}>
      <div style={{ height: '100%', border: '1.4px dashed #9D9BE6', borderRadius: 4, padding: '14px 28px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button
            type="button"
            onClick={onBack}
            aria-label={`Back from ${room}`}
            style={{ border: 0, background: 'none', padding: 0, fontFamily: 'inherit', fontSize: 15, color: '#333', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <span aria-hidden="true" style={{ fontSize: 18, lineHeight: 1 }}>‹</span>
            {room}
          </button>
          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: colors.muted }}>
            {legend.map((l) => (
              <span key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: l.color }} />
                {l.label}
              </span>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${PER_ROW}, minmax(0, 1fr))`, columnGap: '2.6%', rowGap: 22, alignContent: 'start' }}>
          {machines.map((m) => (
            <div
              key={m.name}
              title={`${m.name} · ${tileLabel(m)}`}
              aria-label={`${m.name} ${tileLabel(m)}`}
              style={{ aspectRatio: '72 / 42', background: tileColor(m), boxShadow: '0 1px 2px rgba(0,0,0,0.18)' }}
            />
          ))}
        </div>
        {machines.length === 0 && <div style={{ color: colors.muted, fontSize: 12 }}>ไม่มีเครื่องในห้องนี้</div>}
      </div>
    </div>
  );
}
