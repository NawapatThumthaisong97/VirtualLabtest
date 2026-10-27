import { colors } from './theme';
import { Card, cellBorder } from './ui';
import Donut from './Donut';
import type { BillingSummary } from '../../services/adminDashboard';

const alertColor = { none: colors.money, warn: colors.yellow, over: colors.error } as const;
const sourceLabel = {
  estimate: 'estimate (hours × price)',
  mixed: 'AWS actual + today estimate',
  'cost-explorer': 'AWS actual',
} as const;

/** ค่า AWS เดือนนี้เทียบ budget + เหลือกี่วันในเดือน */
export default function BillingEstimate({ data }: { data: BillingSummary | undefined }) {
  if (!data) {
    return (
      <Card style={{ paddingBottom: 20 }}>
        <div style={{ padding: '12px 14px', borderBottom: cellBorder, color: colors.blue, fontSize: 14 }}>Billing | Overall estimate</div>
        <div style={{ padding: 40, textAlign: 'center', color: colors.muted }}>กำลังโหลด…</div>
      </Card>
    );
  }
  const { aws } = data;
  const pct = (data.daysRemaining / data.daysTotal) * 100;
  return (
    <Card style={{ paddingBottom: 20 }}>
      <div style={{ padding: '12px 14px', borderBottom: cellBorder, color: colors.blue, fontSize: 14 }}>Billing | Overall estimate</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, alignItems: 'start', padding: '18px 16px 0' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 16, lineHeight: 1.35 }}>
            Current Billing
            <br />
            Charge
          </div>
          <div style={{ fontSize: 34, fontWeight: 500, color: alertColor[aws.alert], marginTop: 24 }}>${aws.usedUsd.toFixed(2)}</div>
          <div style={{ fontSize: 11, color: colors.muted, marginTop: 6, lineHeight: 1.6 }}>
            of ${aws.budgetUsd.toFixed(0)} budget ({aws.usedPct}%)
            <br />
            forecast ${aws.forecastUsd.toFixed(2)} · AWS {aws.sessionHours} h
            <br />
            <span title={aws.reconciledAt ? `Cost Explorer: ${new Date(aws.reconciledAt).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' })}` : undefined}>
              {sourceLabel[aws.source]}
            </span>
          </div>
          {!data.burstEnabled && (
            <div style={{ marginTop: 8, fontSize: 11, color: colors.error }}>AWS burst ปิดอยู่</div>
          )}
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 16, marginBottom: 14 }}>Day until spending</div>
          <Donut track="#E8E8E8" segments={[{ value: pct, color: colors.chartGreen }]}>
            <span style={{ color: colors.muted, fontSize: 11 }}>
              remain {data.daysRemaining}/{data.daysTotal} days
            </span>
          </Donut>
        </div>
      </div>
    </Card>
  );
}
