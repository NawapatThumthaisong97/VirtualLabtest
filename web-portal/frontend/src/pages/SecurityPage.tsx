/**
 * Security (/admin/security) — Grafana SIEM ของ Nawapat (k8s/siem/layer5-detection) ฝังเต็มจอ โทนมืด
 * Grafana รันบน master (NodePort 30300, anonymous = Viewer) URL มาจาก VITE_SIEM_GRAFANA_URL ตอน build
 * เบราว์เซอร์ต้องอยู่ใน Tailscale เดียวกับ cluster ถึงจะโหลด iframe ได้
 */
import { useEffect, useState } from 'react';
import Navbar from '../components/admin/Navbar';

export const GRAFANA_URL = (import.meta.env.VITE_SIEM_GRAFANA_URL || '').replace(/\/$/, '');

const DASHBOARDS = [
  { uid: 'vlab-siem-analytics', label: 'Threat Analytics' },
  { uid: 'vlab-siem-5layer', label: 'Command Center' },
] as const;

/** สีเดียวกับ Grafana dark จะได้ไม่เห็นรอยต่อระหว่างหน้าเรากับ iframe */
const dark = { bg: '#111217', bar: '#181b1f', border: '#2c3235', text: '#ccccdc', muted: '#8e8e9e', accent: '#3AAEE0' };

export const dashboardUrl = (uid: string) => `${GRAFANA_URL}/d/${uid}?orgId=1&kiosk&theme=dark`;

type Reach = 'checking' | 'ok' | 'down';

/** iframe ข้าม origin บอกไม่ได้ว่าโหลดพังไหม → ยิง /api/health แบบ no-cors: ต่อได้ = resolve, ต่อไม่ได้ = reject */
async function probe(): Promise<Reach> {
  try {
    await fetch(`${GRAFANA_URL}/api/health`, { mode: 'no-cors', cache: 'no-store' });
    return 'ok';
  } catch {
    return 'down';
  }
}

const tab = (active: boolean) =>
  ({
    background: 'none',
    border: 0,
    borderBottom: `2px solid ${active ? dark.accent : 'transparent'}`,
    padding: '6px 2px',
    color: active ? '#fff' : dark.muted,
    fontFamily: 'inherit',
    fontSize: 14,
    cursor: active ? 'default' : 'pointer',
    whiteSpace: 'nowrap',
  }) as const;

const iconButton = {
  background: 'none',
  border: `1px solid ${dark.border}`,
  borderRadius: 4,
  color: dark.text,
  padding: '5px 10px',
  fontFamily: 'inherit',
  fontSize: 12,
  cursor: 'pointer',
  textDecoration: 'none',
  whiteSpace: 'nowrap',
} as const;

export default function SecurityPage() {
  const [uid, setUid] = useState<string>(DASHBOARDS[0].uid);
  const [reach, setReach] = useState<Reach>(GRAFANA_URL ? 'checking' : 'down');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!GRAFANA_URL) return;
    let alive = true;
    setReach('checking');
    probe().then((r) => alive && setReach(r));
    return () => {
      alive = false;
    };
  }, [reloadKey]);

  const reload = () => setReloadKey((k) => k + 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: dark.bg, color: dark.text, fontFamily: "'Inter', sans-serif" }}>
      <Navbar />
      <div style={{ background: dark.bar, borderBottom: `1px solid ${dark.border}`, display: 'flex', alignItems: 'center', gap: 32, padding: '0 24px', minHeight: 60, flexShrink: 0 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 200, color: '#fff', letterSpacing: -0.2 }}>Security</h1>
        <nav style={{ display: 'flex', gap: 24, flex: 1 }}>
          {DASHBOARDS.map((d) => (
            <button key={d.uid} style={tab(d.uid === uid)} aria-current={d.uid === uid ? 'page' : undefined} onClick={() => setUid(d.uid)}>
              {d.label}
            </button>
          ))}
        </nav>
        <button style={iconButton} onClick={reload} title="โหลด dashboard ใหม่">⟳ Reload</button>
        {GRAFANA_URL && (
          <a style={iconButton} href={dashboardUrl(uid)} target="_blank" rel="noreferrer" title="เปิดใน Grafana แท็บใหม่">
            Open in Grafana ↗
          </a>
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {reach === 'ok' ? (
          <iframe
            key={`${uid}-${reloadKey}`}
            title="Grafana SIEM"
            src={dashboardUrl(uid)}
            style={{ border: 0, width: '100%', height: '100%', display: 'block', background: dark.bg }}
          />
        ) : (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, fontSize: 13 }}>
            {reach === 'checking' ? (
              <span style={{ color: dark.muted }}>กำลังเชื่อมต่อ Grafana…</span>
            ) : (
              <>
                <span style={{ color: '#fff', fontSize: 15 }}>เปิด Grafana ไม่ได้</span>
                <span style={{ color: dark.muted, textAlign: 'center', lineHeight: 1.6 }}>
                  {GRAFANA_URL ? (
                    <>
                      ต่อ {GRAFANA_URL} ไม่ได้ — Grafana (siem-system บน master) ล่ม
                      <br />
                      หรือเครื่องนี้ไม่ได้อยู่ใน Tailscale
                    </>
                  ) : (
                    'ยังไม่ได้ตั้ง VITE_SIEM_GRAFANA_URL ตอน build frontend'
                  )}
                </span>
                {GRAFANA_URL && <button style={iconButton} onClick={reload}>ลองใหม่</button>}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
