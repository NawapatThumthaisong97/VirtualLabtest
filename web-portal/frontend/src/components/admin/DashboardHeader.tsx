import type { CSSProperties, ReactNode } from 'react';
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
  /** แท็บของหน้าที่เปิดอยู่ — ขีดเส้นใต้ กดไม่ได้ */
  active?: boolean;
}

const defaultFeatures: HeaderFeature[] = [
  { label: 'Class Scheduler', to: '/admin/scheduler' },
  { label: 'Bill Explorer', target: 'billing' },
  { label: 'Logs', to: '/admin/logs' },
  { label: 'Class System', note: 'เร็ว ๆ นี้' },
];

const button = (enabled: boolean, active: boolean) =>
  ({
    background: 'none',
    border: 0,
    borderBottom: `2px solid ${active ? '#fff' : 'transparent'}`,
    padding: '4px 2px',
    color: '#fff',
    opacity: enabled || active ? 1 : 0.55,
    fontFamily: 'inherit',
    fontSize: 15,
    fontWeight: active ? 400 : 300,
    cursor: enabled ? 'pointer' : 'default',
    whiteSpace: 'nowrap',
  }) as const;

/**
 * แถบหัวหน้า admin: ชื่อหน้า + ปุ่มเลือก feature
 * หน้านักศึกษาใช้ตัวเดียวกัน ส่ง inner มากำหนดความกว้าง ชื่อหน้าจะได้ตรงระนาบกับการ์ดด้านล่าง
 * children = ปุ่มหลักของหน้า (เช่น Start Lab work) ต่อท้ายแท็บ
 */
export default function DashboardHeader({
  title = 'My Dashboard',
  features = defaultFeatures,
  inner,
  children,
}: {
  title?: string;
  features?: HeaderFeature[];
  inner?: CSSProperties;
  children?: ReactNode;
}) {
  const navigate = useNavigate();
  const go = (f: HeaderFeature) => {
    if (f.to) navigate(f.to);
    else if (f.target) document.getElementById(f.target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div style={{ background: colors.headerBlue, fontWeight: 200, color: '#fff' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '0 32px',
          gap: 32,
          minHeight: 60,
          ...inner,
        }}
      >
        <h1 style={{ flex: 1, margin: 0, fontSize: 22, fontWeight: 200, letterSpacing: -0.2 }}>{title}</h1>

        <nav style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
          {features.map((f) => {
            const active = Boolean(f.active);
            const enabled = !active && Boolean(f.target || f.to);
            return (
              <button
                key={f.label}
                onClick={() => go(f)}
                disabled={!enabled}
                aria-current={active ? 'page' : undefined}
                title={enabled || active ? undefined : f.note}
                style={button(enabled, active)}
                onMouseEnter={(e) => enabled && (e.currentTarget.style.textDecoration = 'underline')}
                onMouseLeave={(e) => (e.currentTarget.style.textDecoration = 'none')}
              >
                {f.label}
              </button>
            );
          })}
        </nav>

        {children}
      </div>
    </div>
  );
}
