import { colors } from './theme';

export interface HeaderFeature {
  label: string;
  /** id ของการ์ดในหน้า — กดแล้วเลื่อนไปที่การ์ดนั้น ไม่มี = ยังไม่มี feature (ปุ่มจาง) */
  target?: string;
  /** แสดงตอนเอาเมาส์ชี้ปุ่มที่ยังไม่มี feature */
  note?: string;
}

const defaultFeatures: HeaderFeature[] = [
  { label: 'Class Scheduler', note: 'เร็ว ๆ นี้ — ระบบจองห้อง' },
  { label: 'Bill Explorer', target: 'billing' },
  { label: 'Logs', target: 'logs' },
  { label: 'Class System', note: 'เร็ว ๆ นี้' },
];

const button = (enabled: boolean) =>
  ({
    background: 'none',
    border: 0,
    padding: '6px 2px',
    color: '#fff',
    opacity: enabled ? 1 : 0.55,
    fontFamily: 'inherit',
    fontSize: 17,
    fontWeight: 300,
    cursor: enabled ? 'pointer' : 'default',
    whiteSpace: 'nowrap',
  }) as const;

/** แถบหัวหน้า admin: ชื่อหน้า + ปุ่มเลือก feature */
export default function DashboardHeader({
  title = 'My Dashboard',
  features = defaultFeatures,
}: {
  title?: string;
  features?: HeaderFeature[];
}) {
  const go = (target?: string) => {
    if (target) document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div
      style={{
        background: colors.headerBlue,
        display: 'flex',
        alignItems: 'center',
        padding: '0 32px',
        gap: 40,
        fontWeight: 200,
        color: '#fff',
        minHeight: 82,
      }}
    >
      <h1 style={{ flex: 1, margin: 0, fontSize: 28, fontWeight: 200, letterSpacing: -0.2 }}>{title}</h1>

      <nav style={{ display: 'flex', alignItems: 'center', gap: 40 }}>
        {features.map((f) => (
          <button
            key={f.label}
            onClick={() => go(f.target)}
            disabled={!f.target}
            title={f.target ? undefined : f.note}
            style={button(Boolean(f.target))}
            onMouseEnter={(e) => f.target && (e.currentTarget.style.textDecoration = 'underline')}
            onMouseLeave={(e) => (e.currentTarget.style.textDecoration = 'none')}
          >
            {f.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
