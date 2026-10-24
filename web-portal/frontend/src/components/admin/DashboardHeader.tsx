import { useNavigate } from 'react-router-dom';
import { colors } from './theme';

export interface HeaderFeature {
  label: string;
  /** id ของการ์ดในหน้า — กดแล้วเลื่อนไปที่การ์ดนั้น */
  target?: string;
  /** หน้าแยก — กดแล้วไปหน้านั้น (ไม่มีทั้ง target และ to = ยังไม่มี feature ปุ่มจาง) */
  to?: string;
  /** แสดงตอนเอาเมาส์ชี้ปุ่มที่ยังไม่มี feature */
  note?: string;
}

const defaultFeatures: HeaderFeature[] = [
  { label: 'Class Scheduler', to: '/admin/scheduler' },
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
  const navigate = useNavigate();
  const go = (f: HeaderFeature) => {
    if (f.to) navigate(f.to);
    else if (f.target) document.getElementById(f.target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
        {features.map((f) => {
          const enabled = Boolean(f.target || f.to);
          return (
          <button
            key={f.label}
            onClick={() => go(f)}
            disabled={!enabled}
            title={enabled ? undefined : f.note}
            style={button(enabled)}
            onMouseEnter={(e) => enabled && (e.currentTarget.style.textDecoration = 'underline')}
            onMouseLeave={(e) => (e.currentTarget.style.textDecoration = 'none')}
          >
            {f.label}
          </button>
          );
        })}
      </nav>
    </div>
  );
}
