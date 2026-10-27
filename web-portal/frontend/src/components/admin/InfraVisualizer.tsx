import { useState } from 'react';
import { colors, type StatusTone } from './theme';
import { Card, StatusDot, cellBorder } from './ui';
import InfraMap from './InfraMap';
import { formatThaiTime } from './SystemTable';
import type { InfraMap as InfraMapData, RoomUsage, ServiceHealth, SystemStatus } from '../../services/adminDashboard';

type LatencyLevel = 'bad' | 'good' | 'warn';
const latencyBg: Record<LatencyLevel, string> = { bad: colors.cellRed, good: colors.cellGreen, warn: colors.cellYellow };
const healthTone: Record<ServiceHealth, StatusTone> = { ok: 'success', degraded: 'warning', down: 'error' };
const healthLabel: Record<ServiceHealth, string> = { ok: 'reachable', degraded: 'degraded', down: 'unreachable' };

/** service ใน health check ที่เป็นทรัพยากรของ cluster (ตาราง Cluster Resources) */
const RESOURCE_KEYS: Record<string, string> = { registry: 'Docker reg.', k8s: 'Kubernetes API', skypilot: 'SkyPilot API' };

function latencyLevel(ms: number | null): LatencyLevel {
  if (ms === null || ms >= 2000) return 'bad';
  return ms >= 500 ? 'warn' : 'good';
}

function timeRange(startsAt: string, endsAt: string): string {
  const fmt = (iso: string) =>
    new Date(iso).toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit', hour12: false });
  return `${fmt(startsAt)} – ${fmt(endsAt)}`;
}

const th = { padding: '8px 10px', fontWeight: 600, borderBottom: cellBorder, borderRight: cellBorder } as const;
const td = { padding: '11px 10px', borderBottom: cellBorder, borderRight: cellBorder } as const;
const last = { borderRight: 'none' } as const;

export default function InfraVisualizer({
  map,
  usage,
  status,
}: {
  map: InfraMapData | undefined;
  usage: RoomUsage | undefined;
  status: SystemStatus | undefined;
}) {
  const rooms = usage?.rooms ?? [];
  const [picked, setPicked] = useState<string | null>(null);
  const selected = rooms.find((r) => r.room === picked) ?? rooms[0];
  const resources = (status?.services ?? []).filter((s) => s.key in RESOURCE_KEYS);

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 12px', borderBottom: cellBorder }}>
        <span style={{ color: colors.blue }}>Infrastructure Visualizer</span>
        <span style={{ color: colors.muted, fontSize: 11 }}>คลิกห้องเพื่อดูรายละเอียด · Alt + scroll ซูม</span>
      </div>

      <InfraMap data={map} selected={selected?.room ?? null} onSelect={setPicked} />

      <div style={{ padding: '14px 0 4px' }}>
        <div style={{ fontWeight: 600, marginBottom: 10, padding: '0 14px' }}>ClusterName : {selected?.room ?? '-'}</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', borderTop: cellBorder }}>
          <thead>
            <tr>
              <td style={{ ...th, width: '17%' }}>UsageUnit</td>
              <td style={{ ...th, width: '23%' }}>Status</td>
              <td style={{ ...th, width: '26%' }}>UsedBy</td>
              <td style={{ ...th, ...last, whiteSpace: 'nowrap' }}>ScheduleTime</td>
            </tr>
          </thead>
          <tbody>
            {selected ? (
              <tr>
                <td style={{ ...td, textAlign: 'center' }}>
                  {selected.pcsInUse}/{selected.pcsTotal}
                </td>
                <td style={td}>
                  <StatusDot
                    tone={selected.state === 'launched' ? 'success' : 'warning'}
                    label={selected.state === 'launched' ? 'Launched' : 'Idle'}
                  />
                </td>
                <td style={td}>{selected.slot?.course ?? (selected.state === 'launched' ? 'นอกคาบ' : '-')}</td>
                <td style={{ ...td, ...last, whiteSpace: 'nowrap' }}>
                  {selected.slot ? timeRange(selected.slot.startsAt, selected.slot.endsAt) : '-'}
                </td>
              </tr>
            ) : (
              <tr>
                <td colSpan={4} style={{ ...td, ...last, textAlign: 'center', color: colors.muted }}>
                  ไม่มีห้อง (worker ยังไม่มี label vlab/room หรือต่อ K3s ไม่ได้)
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ padding: '14px 0 16px' }}>
        <div style={{ color: colors.blue, marginBottom: 10, padding: '0 14px' }}>Cluster Resources</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', borderTop: cellBorder }}>
          <thead>
            <tr>
              <td style={{ ...th, width: '26%' }}>NodeType</td>
              <td style={{ ...th, width: '24%' }}>Status</td>
              <td style={{ ...th, width: '30%' }}>TimeStamp</td>
              <td style={{ ...th, ...last }}>Latency (ms)</td>
            </tr>
          </thead>
          <tbody>
            {resources.length === 0 && (
              <tr>
                <td colSpan={4} style={{ ...td, ...last, textAlign: 'center', color: colors.muted }}>
                  ยังไม่มีผลตรวจ
                </td>
              </tr>
            )}
            {resources.map((r) => (
              <tr key={r.key} title={r.detail ?? undefined}>
                <td style={td}>{RESOURCE_KEYS[r.key]}</td>
                <td style={td}>
                  <StatusDot tone={healthTone[r.status]} label={healthLabel[r.status]} />
                </td>
                <td style={{ ...td, fontSize: 11 }}>{formatThaiTime(r.checkedAt)}</td>
                <td style={{ ...td, ...last, background: latencyBg[latencyLevel(r.latencyMs)] }}>{r.latencyMs ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
