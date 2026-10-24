/**
 * Log Explorer (/admin/logs) — UI จาก Log.zip (Pete ออกแบบ) ต่อ /api/v1/admin/logs* ข้อมูลจริง
 * ตัวกรอง: Log Type (on-prem / AWS) · Log Tags (severity) · Event / Display Fields เลือกคอลัมน์เอง (จำไว้ในเครื่อง)
 * คลิกแถว = ดู JSON เต็ม
 */
import { Fragment, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { colors } from '../components/admin/theme';
import Navbar from '../components/admin/Navbar';
import { adminLogService, type LogCategory, type LogItem, type LogQuery } from '../services/adminDashboard';

const PAGE = 20;
const border = `1px solid ${colors.border}`;
const RANGES = [
  { label: '24h', hours: 24, bucket: 1 },
  { label: '72h', hours: 72, bucket: 2 },
  { label: '7d', hours: 168, bucket: 6 },
];
const LOG_TYPES: { label: string; value: LogCategory | '' }[] = [
  { label: 'All', value: '' },
  { label: 'On-premise', value: 'CLUSTER' },
  { label: 'AWS Cloud', value: 'CLOUD' },
];
const LOG_TAGS = [
  { label: 'All', value: '' },
  { label: 'Critical', value: 'CRITICAL' },
  { label: 'Error', value: 'ERROR' },
  { label: 'Warning', value: 'WARNING' },
  { label: 'Info', value: 'INFO' },
];
const severityColor: Record<string, string> = {
  INFO: colors.muted, WARNING: colors.yellow, ERROR: colors.error, CRITICAL: colors.error,
};

/** ประเภทของต้นเรื่องจาก event type */
const entityType = (l: LogItem) =>
  ({
    NODE_NOT_READY: 'Node', NODE_READY: 'Node', POD_EVENT: 'Pod', SESSION_FAILED: 'Session',
    CLOUD_LAUNCH_FAILED: 'Session', HEALTH_DOWN: 'Service', HEALTH_RECOVERED: 'Service',
    BUDGET_ALERT: 'Budget', BURST_TOGGLED: 'Admin',
  })[l.eventType] ?? 'Other';

interface Field {
  key: string;
  label: string;
  width: string;
  render: (l: LogItem) => React.ReactNode;
}

const FIELDS: Field[] = [
  { key: 'severity', label: 'Severity', width: '96px',
    render: (l) => <span style={{ color: severityColor[l.severity] ?? colors.text, fontWeight: 600 }}>● {l.severity}</span> },
  { key: 'event', label: 'Event', width: '150px', render: (l) => l.eventType },
  { key: 'entity', label: 'Entity', width: '150px', render: (l) => l.source },
  { key: 'entityType', label: 'Entity Type', width: '96px', render: entityType },
  { key: 'source', label: 'Log Source', width: '100px', render: (l) => (l.category === 'CLOUD' ? 'AWS Cloud' : 'On-premise') },
  { key: 'room', label: 'Room', width: '80px', render: (l) => l.room ?? '-' },
  { key: 'user', label: 'User', width: '120px', render: (l) => l.anonId ?? '-' },
];
const DEFAULT_FIELDS = ['severity', 'entity', 'entityType', 'source'];
const STORE_KEY = 'vlab.logExplorer.fields';

function loadFields(): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) ?? 'null');
    if (Array.isArray(saved)) return saved.filter((k) => FIELDS.some((f) => f.key === k));
  } catch { /* ไม่มี localStorage ใช้ค่าเริ่มต้น */ }
  return DEFAULT_FIELDS;
}

const thTime = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Date(iso).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok', hour12: false, ...opts });

function niceMax(v: number): number {
  if (v <= 0) return 3;
  const p = 10 ** Math.floor(Math.log10(v));
  return ([1, 2, 5, 10].find((m) => m * p >= v) ?? 10) * p;
}

function FilterSelect({ id, label, value, options, onChange }: {
  id: string; label: string; value: string; options: { label: string; value: string }[]; onChange: (v: string) => void;
}) {
  return (
    <label htmlFor={id} style={{ display: 'flex', alignItems: 'center', height: 32, border, padding: '0 12px', gap: 4 }}>
      <span style={{ whiteSpace: 'nowrap' }}>{label} :</span>
      <select id={id} aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
        style={{ flex: 1, minWidth: 0, border: 0, outline: 'none', background: 'transparent', fontFamily: 'inherit', fontSize: 12, color: colors.text, cursor: 'pointer' }}>
        {options.map((o) => <option key={o.label} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export default function LogExplorerPage() {
  const [category, setCategory] = useState<LogCategory | ''>('');
  const [severity, setSeverity] = useState('');
  const [eventType, setEventType] = useState('');
  const [range, setRange] = useState(RANGES[1]);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [fields, setFields] = useState<string[]>(loadFields);

  const saveFields = (next: string[]) => {
    setFields(next);
    try { localStorage.setItem(STORE_KEY, JSON.stringify(next)); } catch { /* ไม่เป็นไร */ }
  };

  const q: LogQuery = { category: category || undefined, severity: severity || undefined, type: eventType || undefined };
  // จำนวนต่อ event ไม่กรอง event (ใช้เป็นตัวเลือกใน dropdown)
  const allTypes = useQuery({
    queryKey: ['logs', 'types', category, severity, range.hours],
    queryFn: () => adminLogService.histogram({ ...q, type: undefined }, range.hours, range.bucket),
  });
  const hist = useQuery({
    queryKey: ['logs', 'hist', q, range.hours],
    queryFn: () => adminLogService.histogram(q, range.hours, range.bucket),
    refetchInterval: 30_000,
  });
  const list = useQuery({
    queryKey: ['logs', 'list', q, page],
    queryFn: () => adminLogService.list(q, PAGE, page * PAGE),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });

  const shown = FIELDS.filter((f) => fields.includes(f.key));
  const hidden = FIELDS.filter((f) => !fields.includes(f.key));
  const cols = `130px ${shown.map((f) => f.width).join(' ')} minmax(0,1fr) 34px`;
  const eventOptions = useMemo(
    () => [{ label: 'All', value: '' }, ...Object.entries(allTypes.data?.byType ?? {})
      .sort((a, b) => b[1] - a[1]).map(([t, n]) => ({ label: `${t} (${n})`, value: t }))],
    [allTypes.data],
  );
  const buckets = hist.data?.buckets ?? [];
  const max = niceMax(Math.max(0, ...buckets.map((b) => b.count)));
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const filter = (set: (v: string) => void) => (v: string) => { set(v); setPage(0); };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', color: colors.text, fontFamily: "'Inter', sans-serif" }}>
      <Navbar />
      <div style={{ background: colors.headerBlue, display: 'flex', alignItems: 'center', padding: '0 24px', color: '#fff' }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 200, letterSpacing: -0.2, padding: '18px 0' }}>Log Explorer</h1>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0, background: colors.pageBg }}>
        <aside style={{ width: 236, flexShrink: 0, background: '#fff', borderRight: border, display: 'flex', flexDirection: 'column', fontSize: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '14px 16px', borderBottom: border, fontWeight: 600 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="1.8"><path d="M3 4h18l-7 8.5V19l-4 2v-8.5z" /></svg>
            Log filter
          </div>
          <div style={{ padding: '20px 16px', borderBottom: border, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <FilterSelect id="log-type" label="Log Type" value={category} options={LOG_TYPES} onChange={filter((v) => setCategory(v as LogCategory | ''))} />
            <FilterSelect id="log-tags" label="Log Tags" value={severity} options={LOG_TAGS} onChange={filter(setSeverity)} />
            <FilterSelect id="log-event" label="Event" value={eventType} options={eventOptions} onChange={filter(setEventType)} />
          </div>
          <div style={{ padding: '20px 16px', display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
            <span style={{ fontWeight: 600 }}>Display Fields</span>
            <div style={{ border, background: '#F7F9FA', padding: 6, display: 'flex', flexDirection: 'column', gap: 6, minHeight: 160 }}>
              {shown.map((f) => (
                <div key={f.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, minHeight: 26, padding: '0 10px', background: '#E6E7EA', border: '1px solid #d0d2d6' }}>
                  <span>{f.label}</span>
                  <button aria-label={`Remove ${f.label}`} onClick={() => saveFields(fields.filter((k) => k !== f.key))}
                    style={{ border: 0, background: 'none', padding: 2, cursor: 'pointer', display: 'flex' }}>
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="2.4"><path d="M6 6l12 12M18 6L6 18" /></svg>
                  </button>
                </div>
              ))}
              {hidden.length > 0 && (
                <select id="add-field" aria-label="Add field" value="" onChange={(e) => e.target.value && saveFields([...fields, e.target.value])}
                  style={{ height: 26, border: '1px dashed #c4c6ca', background: 'none', fontFamily: 'inherit', fontSize: 11, color: colors.muted, cursor: 'pointer' }}>
                  <option value="">+ เพิ่ม field</option>
                  {hidden.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                </select>
              )}
            </div>
          </div>
        </aside>

        <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', background: '#fff' }}>
          <div style={{ padding: '24px 48px 20px', borderBottom: border }}>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, marginBottom: 12 }}>
              {RANGES.map((r) => (
                <button key={r.label} onClick={() => setRange(r)} aria-pressed={r === range}
                  style={{ border, background: r === range ? '#f2f2f2' : '#fff', borderRadius: 6, padding: '4px 12px', fontFamily: 'inherit', fontSize: 11, cursor: 'pointer' }}>
                  {r.label}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', height: 150 }}>
              <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: 9, lineHeight: 0, color: '#aaa', paddingRight: 10, textAlign: 'right', minWidth: 28 }}>
                {[max, (max * 2) / 3, max / 3, 0].map((t, i) => <span key={i}>{Number.isInteger(t) ? t : t.toFixed(1)}</span>)}
              </div>
              <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: 3, padding: '0 6px', borderBottom: '1px solid #e2e2e2' }}>
                {buckets.map((b) => (
                  <div key={b.t} title={`${thTime(b.t, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}: ${b.count}`}
                    style={{ flex: 1, height: `${(b.count / max) * 100}%`, minHeight: b.count ? 2 : 0, background: colors.logBar }} />
                ))}
              </div>
            </div>
            <div style={{ display: 'flex', fontSize: 9, color: colors.muted, paddingLeft: 38, marginTop: 6 }}>
              {buckets.map((b, i) => (
                <span key={b.t} style={{ flex: 1, whiteSpace: 'nowrap' }}>
                  {i % Math.ceil(buckets.length / 6) === 0 ? thTime(b.t, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
                </span>
              ))}
            </div>
          </div>

          <div style={{ padding: '22px 20px 32px', background: colors.pageBg, flex: 1, overflowX: 'auto' }}>
            <div style={{ background: '#fff', border, fontSize: 12, minWidth: 640 }}>
              <div style={{ display: 'grid', gridTemplateColumns: cols, borderBottom: border, fontWeight: 600 }}>
                <span style={{ padding: '9px 12px', borderRight: border }}>Time (GMT +7)</span>
                {shown.map((f) => <span key={f.key} style={{ padding: '9px 10px', borderRight: border }}>{f.label}</span>)}
                <span style={{ padding: '9px 16px', borderRight: border }}>Log Content</span>
                <span />
              </div>
              {list.data && list.data.items.length === 0 && (
                <div style={{ padding: 24, textAlign: 'center', color: colors.muted }}>ไม่มี log ตามตัวกรองนี้</div>
              )}
              {(list.data?.items ?? []).map((l) => (
                <Fragment key={l.id}>
                  <div role="button" tabIndex={0} aria-expanded={open === l.id} onClick={() => setOpen(open === l.id ? null : l.id)}
                    onKeyDown={(e) => e.key === 'Enter' && setOpen(open === l.id ? null : l.id)}
                    style={{ display: 'grid', gridTemplateColumns: cols, borderBottom: border, cursor: 'pointer' }}>
                    <div style={{ padding: '12px', borderRight: border, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 }}>
                      <span>{thTime(l.timestamp, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                      <span style={{ color: colors.muted }}>{thTime(l.timestamp, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                    </div>
                    {shown.map((f) => (
                      <div key={f.key} style={{ padding: '12px 10px', borderRight: border, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.render(l)}</div>
                    ))}
                    <div style={{ padding: '12px 16px', borderRight: border, wordBreak: 'break-word', lineHeight: 1.5 }}>{l.message}</div>
                    <div style={{ padding: '12px 0', textAlign: 'center', color: colors.muted }}>{open === l.id ? '▾' : '▸'}</div>
                  </div>
                  {open === l.id && (
                    <pre style={{ margin: 0, padding: '12px 16px', background: '#F7F9FA', borderBottom: border, fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {JSON.stringify(l, null, 2)}
                    </pre>
                  )}
                </Fragment>
              ))}
              <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 10, padding: '10px 12px', fontSize: 11, color: colors.muted }}>
                <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} style={{ border, background: '#fff', padding: '2px 10px', cursor: 'pointer' }}>‹</button>
                <span>{page + 1} / {pages} · {total} รายการ</span>
                <button disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)} style={{ border, background: '#fff', padding: '2px 10px', cursor: 'pointer' }}>›</button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
