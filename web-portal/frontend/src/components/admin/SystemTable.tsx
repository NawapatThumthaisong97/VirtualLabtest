import { colors, type StatusTone } from './theme';
import { Card, StatusDot, cellBorder } from './ui';
import type { HourlyHealth, ServiceHealth, SystemStatus } from '../../services/adminDashboard';

const tone: Record<ServiceHealth, StatusTone> = { ok: 'success', degraded: 'warning', down: 'error' };
const label: Record<ServiceHealth, string> = { ok: 'Ok', degraded: 'Degraded', down: 'Down' };
const hourColor: Record<HourlyHealth, string> = {
  ok: colors.success,
  degraded: colors.yellow,
  down: colors.error,
  nodata: '#e2e2e2',
};
const rank: Record<HourlyHealth, number> = { nodata: -1, ok: 0, degraded: 1, down: 2 };

/** latency ปกติของ service (ms) — ตรงนี้น้ำเงินกับเหลืองเท่ากัน AWS ออกเน็ตไปต่างประเทศ ช้ากว่าเป็นปกติ */
const TYPICAL_MS: Record<string, number> = { aws: 1000 };
const DEFAULT_TYPICAL_MS = 250;

/** สีน้ำเงิน = ความเร็ว: เร็วมาก (1 ms) เกือบเต็มแถบ, ช้าเท่าค่าปกติ = ครึ่ง, ยิ่งช้ายิ่งเหลือน้อย */
export function speedPct(key: string, ms: number): number {
  const typical = TYPICAL_MS[key] ?? DEFAULT_TYPICAL_MS;
  return (typical / (ms + typical)) * 100;
}

const th = { padding: '8px 10px', fontWeight: 600, borderRight: cellBorder } as const;
const td = { padding: 10, borderRight: cellBorder } as const;

export function formatThaiTime(iso: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok', hour12: false });
}

export default function SystemTable({ data }: { data: SystemStatus | undefined }) {
  const services = data?.services ?? [];
  // Overall = ช่องละชั่วโมง เอา status แย่สุดของทุก service
  const overall: HourlyHealth[] = Array.from({ length: 24 }, (_, i) =>
    services.reduce<HourlyHealth>((worst, s) => (rank[s.hourly[i]] > rank[worst] ? s.hourly[i] : worst), 'nodata'),
  );

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 12px', borderBottom: cellBorder }}>
        <span style={{ color: colors.blue }}>System Table</span>
        <span style={{ color: colors.muted, fontSize: 11 }}>Showing {services.length}</span>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
        <thead>
          <tr style={{ height: 56, verticalAlign: 'bottom' }}>
            <td style={{ ...th, width: '22%', padding: '8px 12px', verticalAlign: 'top' }}>ServiceName</td>
            <td style={{ ...th, width: '16%' }}>Version</td>
            <td style={{ ...th, width: '15%' }}>TraceStatus</td>
            <td style={{ ...th, borderRight: 'none' }}>Latency</td>
          </tr>
        </thead>
        <tbody>
          {services.length === 0 && (
            <tr style={{ borderTop: cellBorder }}>
              <td colSpan={4} style={{ padding: '18px 12px', color: colors.muted, textAlign: 'center' }}>
                ยังไม่มีผลตรวจ (backend ตรวจทุก 5 นาที)
              </td>
            </tr>
          )}
          {services.map((s) => (
            <tr key={s.key} style={{ borderTop: cellBorder }} title={s.detail ?? undefined}>
              <td style={{ ...td, padding: '10px 12px' }}>{s.name}</td>
              <td style={{ ...td, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.version ?? '-'}</td>
              <td style={td}>
                <StatusDot tone={tone[s.status]} label={label[s.status]} />
              </td>
              <td style={{ ...td, borderRight: 'none' }}>
                {s.latencyMs === null ? (
                  <span style={{ color: colors.error }}>{s.detail ?? 'unreachable'}</span>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ whiteSpace: 'nowrap', minWidth: 52 }}>{s.latencyMs} ms</span>
                    <div style={{ flex: 1, height: 9, display: 'flex', background: '#eee' }}>
                      <div style={{ width: `${speedPct(s.key, s.latencyMs)}%`, background: colors.blue }} />
                      <div style={{ flex: 1, background: colors.yellow }} />
                    </div>
                  </div>
                )}
                {s.latencyMs !== null && s.detail && (
                  <div style={{ color: s.status === 'ok' ? colors.muted : colors.error, fontSize: 10, marginTop: 4 }}>{s.detail}</div>
                )}
              </td>
            </tr>
          ))}

          <tr style={{ borderTop: cellBorder }}>
            <td colSpan={3} style={{ padding: '14px 12px', verticalAlign: 'top', borderRight: cellBorder }}>
              <div style={{ fontWeight: 600, marginBottom: 12 }}>
                Overall Status
                <br />
                Checker
              </div>
              <div style={{ display: 'flex', gap: 2, height: 34 }}>
                {overall.map((h, i) => (
                  <div key={i} title={`${24 - i} ชม.ก่อน: ${h}`} style={{ flex: 1, background: hourColor[h] }} />
                ))}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, color: '#aaa', fontSize: 9 }}>
                <div style={{ flex: 1, height: 1, background: '#ccc' }} />
                <span style={{ whiteSpace: 'nowrap' }}>24 hour range</span>
                <div style={{ flex: 1, height: 1, background: '#ccc' }} />
              </div>
            </td>
            <td style={{ padding: '14px 12px', verticalAlign: 'middle', color: '#555', fontSize: 10, lineHeight: 1.6 }}>
              Last check by <span style={{ color: colors.blue }}>health checker</span>
              <br />
              TimeStamp : {formatThaiTime(data?.checkedAt ?? null)}
            </td>
          </tr>
        </tbody>
      </table>
    </Card>
  );
}
