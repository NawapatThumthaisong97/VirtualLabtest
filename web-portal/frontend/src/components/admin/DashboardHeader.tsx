import { colors } from './theme';

export interface HeaderStat {
  label: string;
  value: number;
}

const defaultStats: HeaderStat[] = [
  { label: 'Course manage', value: 4 },
  { label: 'Report log', value: 7 },
  { label: 'Course manage', value: 2 },
];

export default function DashboardHeader({ title = 'My Dashboard', stats = defaultStats }: { title?: string; stats?: HeaderStat[] }) {
  return (
    <div
      style={{
        background: colors.headerBlue,
        display: 'flex',
        alignItems: 'center',
        padding: '0 80px 0 24px',
        gap: 64,
        fontWeight: 200,
        color: '#fff',
      }}
    >
      <h1 style={{ flex: 1, margin: 0, fontSize: 20, fontWeight: 200, letterSpacing: -0.2, padding: '18px 0' }}>{title}</h1>

      {stats.map((s, i) => (
        <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '13px 0' }}>
          <span style={{ fontSize: 13 }}>{s.label}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 26, lineHeight: 1 }}>{s.value}</span>
            <div style={{ display: 'flex', flexDirection: 'column', fontSize: 12, lineHeight: 1.4, color: 'rgba(255,255,255,0.9)' }}>
              <span>of an image</span>
              <span>is pending review</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
