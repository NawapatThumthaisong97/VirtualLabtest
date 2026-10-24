import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { colors } from './theme';
import { Card, ExternalIcon, cellBorder } from './ui';
import { adminLogService, type LogCategory } from '../../services/adminDashboard';

const REFRESH_MS = 30_000;
const severityColor: Record<string, string> = {
  INFO: colors.muted,
  WARNING: colors.yellow,
  ERROR: colors.error,
  CRITICAL: colors.error,
};

const btn = (active: boolean) =>
  ({
    border: '1px solid #e2e2e2',
    background: active ? '#f7f7f7' : '#fff',
    borderRadius: 6,
    padding: '7px 16px',
    fontSize: 12,
    fontFamily: 'inherit',
    color: colors.text,
    boxShadow: '0 1px 3px rgba(0,0,0,0.18)',
    cursor: 'pointer',
  }) as const;

const thTime = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Date(iso).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok', hour12: false, ...opts });

/** แกน Y ปัดขึ้นเป็นเลขสวย ๆ (1, 2, 5 × 10^n) */
function niceMax(v: number): number {
  if (v <= 0) return 3;
  const p = 10 ** Math.floor(Math.log10(v));
  return ([1, 2, 5, 10].find((m) => m * p >= v) ?? 10) * p;
}

/** จำนวน log 72 ชม. ล่าสุด (ช่องละ 2 ชม.) แยก cluster / cloud + Log detail = 10 รายการล่าสุด */
export default function LogExplorer() {
  const [category, setCategory] = useState<LogCategory>('CLUSTER');
  const [detail, setDetail] = useState(false);
  const navigate = useNavigate();
  const hist = useQuery({
    queryKey: ['admin', 'logs-histogram', category],
    queryFn: () => adminLogService.getHistogram(category),
    refetchInterval: REFRESH_MS,
  });
  const list = useQuery({
    queryKey: ['admin', 'logs', category],
    queryFn: () => adminLogService.getLogs(category),
    refetchInterval: REFRESH_MS,
    enabled: detail,
  });

  const buckets = hist.data?.buckets ?? [];
  const max = niceMax(Math.max(0, ...buckets.map((b) => b.count)));
  const labelEvery = 6; // ทุก 12 ชม.
  const byType = Object.entries(hist.data?.byType ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px' }}>
        <span style={{ color: colors.logTitle, fontSize: 16, flex: 1 }}>Log Explorer</span>
        <button style={btn(category === 'CLUSTER')} onClick={() => setCategory('CLUSTER')}>
          Cluster Usage
        </button>
        <button style={btn(category === 'CLOUD')} onClick={() => setCategory('CLOUD')}>
          Cloud Usage
        </button>
        <button
          onClick={() => setDetail((d) => !d)}
          style={{ fontSize: 12, cursor: 'pointer', background: 'none', border: 0, color: colors.text, fontFamily: 'inherit' }}
        >
          {detail ? 'ซ่อน' : 'ล่าสุด'}
        </button>
        <button
          onClick={() => navigate('/admin/logs')}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, cursor: 'pointer', background: 'none', border: 0, color: colors.text, fontFamily: 'inherit' }}
        >
          Log detail
          <ExternalIcon color={colors.text} />
        </button>
      </div>

      <div style={{ padding: '0 16px 12px' }}>
        <div style={{ display: 'flex', height: 150 }}>
          {/* lineHeight 0: ป้ายบนสุดอยู่ขอบบน ป้าย 0 อยู่ที่เส้นฐานพอดี */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: 9, lineHeight: 0, color: '#aaa', paddingRight: 8, textAlign: 'right', minWidth: 26 }}>
            {[max, (max * 2) / 3, max / 3, 0].map((t, i) => (
              <span key={i}>{Number.isInteger(t) ? t : t.toFixed(1)}</span>
            ))}
          </div>
          <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: 3, borderBottom: '1px solid #e2e2e2' }}>
            {buckets.map((b) => (
              <div
                key={b.t}
                title={`${thTime(b.t, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}: ${b.count} logs`}
                style={{ flex: 1, height: `${(b.count / max) * 100}%`, minHeight: b.count > 0 ? 2 : 0, background: colors.logBar }}
              />
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', fontSize: 9, color: colors.muted, paddingLeft: 34, marginTop: 6 }}>
          {buckets.map((b, i) => (
            <span key={b.t} style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'visible' }}>
              {i % labelEvery === 0 ? thTime(b.t, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, fontSize: 10, color: '#555', marginTop: 10 }}>
          {byType.length === 0 ? (
            <span style={{ color: colors.muted }}>ไม่มี log ใน 72 ชม. ที่ผ่านมา</span>
          ) : (
            byType.map(([type, n]) => (
              <span key={type} style={{ border: cellBorder, borderRadius: 4, padding: '2px 6px' }}>
                {type} · {n}
              </span>
            ))
          )}
        </div>
      </div>

      {detail && (
        <div style={{ borderTop: cellBorder, fontSize: 11 }}>
          {(list.data?.items ?? []).length === 0 && (
            <div style={{ padding: 14, textAlign: 'center', color: colors.muted }}>ไม่มี log</div>
          )}
          {(list.data?.items ?? []).map((l) => (
            <div key={l.id} style={{ display: 'grid', gridTemplateColumns: '92px 70px 140px 1fr', gap: 8, padding: '7px 16px', borderBottom: cellBorder }}>
              <span style={{ color: colors.muted }}>{thTime(l.timestamp, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
              <span style={{ color: severityColor[l.severity] ?? colors.text, fontWeight: 600 }}>{l.severity}</span>
              <span>{l.eventType}</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={l.message}>
                <span style={{ color: colors.blue }}>{l.source}</span> — {l.message}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
