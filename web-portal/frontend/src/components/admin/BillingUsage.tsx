import { colors } from './theme';
import { Card, cellBorder } from './ui';
import Donut from './Donut';
import type { BillingMonthly, BillingSummary } from '../../services/adminDashboard';

const legend = [
  { label: 'On-premise', color: colors.chartBlue },
  { label: 'AWS Cloud', color: colors.chartGreen },
];

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const monthName = (ym: string) => MONTH_NAMES[Number(ym.slice(5, 7)) - 1] ?? ym;

/** แกน Y ปัดขึ้นเป็นเลขสวย ๆ (1, 2, 5 × 10^n) */
function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return ([1, 2, 5, 10].find((m) => m * p >= v) ?? 10) * p;
}

/** ชั่วโมงการใช้งาน on-premise / AWS รายเดือน (ไม่คิดค่าไฟ) + สัดส่วนเดือนนี้ */
export default function BillingUsage({ monthly, summary }: { monthly: BillingMonthly | undefined; summary: BillingSummary | undefined }) {
  const months = monthly?.months ?? [];
  const max = niceMax(Math.max(0, ...months.map((m) => m.onPremHours + m.awsHours)));
  const ticks = [max, (max * 2) / 3, max / 3, 0];
  const fmt = (n: number) => (n >= 10 ? n.toFixed(0) : n.toFixed(1));

  return (
    <Card style={{ paddingBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderBottom: cellBorder }}>
        <span style={{ color: colors.blue, fontSize: 14 }}>Billing | by usage</span>
        <span style={{ color: colors.muted, fontSize: 10 }}>hours</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, padding: '16px 14px 4px', alignItems: 'center' }}>
        <div>
          <div style={{ display: 'flex', height: 150 }}>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: 9, color: '#aaa', paddingRight: 6, textAlign: 'right', paddingBottom: 16 }}>
              {ticks.map((t, i) => (
                <span key={i}>{fmt(t)}</span>
              ))}
            </div>
            <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-around', borderLeft: '1px solid #e2e2e2', borderBottom: '1px solid #e2e2e2', padding: '0 4px' }}>
              {months.map((m) => {
                const total = m.onPremHours + m.awsHours;
                return (
                  <div
                    key={m.month}
                    title={`${m.month}: on-prem ${m.onPremHours} h, AWS ${m.awsHours} h ($${m.awsUsd})`}
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '12%', height: '100%', justifyContent: 'flex-end' }}
                  >
                    <div style={{ width: 14, display: 'flex', flexDirection: 'column-reverse', height: `${(total / max) * 100}%` }}>
                      <div style={{ background: colors.chartBlue, height: total ? `${(m.onPremHours / total) * 100}%` : 0 }} />
                      <div style={{ background: colors.chartGreen, height: total ? `${(m.awsHours / total) * 100}%` : 0 }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-around', fontSize: 9, color: colors.muted, paddingLeft: 24, marginTop: 4 }}>
            {months.map((m) => (
              <span key={m.month}>{monthName(m.month)}</span>
            ))}
          </div>
        </div>

        <Donut
          track="#E8E8E8"
          segments={[
            { value: summary?.share.onPremPct ?? 0, color: colors.chartBlue },
            { value: summary?.share.awsPct ?? 0, color: colors.chartGreen },
          ]}
        >
          <span style={{ fontSize: 11, color: '#555' }}>Total Usage</span>
          <span style={{ fontSize: 11, color: colors.blue }}>{summary ? monthName(summary.month) : '-'}</span>
          <span style={{ fontSize: 9, color: colors.muted }}>
            {summary ? `${(summary.onPrem.sessionHours + summary.aws.sessionHours).toFixed(1)} h` : ''}
          </span>
        </Donut>
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', gap: 16, fontSize: 9, color: '#666', paddingTop: 8 }}>
        {legend.map((l) => (
          <span key={l.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: l.color }} />
            {l.label}
          </span>
        ))}
      </div>
    </Card>
  );
}
