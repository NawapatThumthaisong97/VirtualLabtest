import { colors } from './theme';
import GradientModal from './GradientModal';
import { WEEKDAYS } from './date';
import type { BookingItem } from '../../services/adminDashboard';

const STATUS: Record<BookingItem['status'], { label: string; color: string }> = {
  pending: { label: 'รออนุมัติ', color: '#D9822B' },
  approved: { label: 'อนุมัติแล้ว', color: '#5E9A2E' },
  rejected: { label: 'ไม่อนุมัติ', color: colors.danger },
  cancelled: { label: 'ยกเลิก', color: colors.muted },
};

const cols = '1.5fr 1.4fr 0.8fr 0.9fr 1.4fr';
const hhmm = (t: string) => t.slice(0, 5);

/** คำขอจองของอาจารย์ในวิชานี้ + สถานะ (rejected มีเหตุผลจาก admin) */
export default function MyRequestsModal({ open, items, onClose }: { open: boolean; items: BookingItem[]; onClose: () => void }) {
  return (
    <GradientModal open={open} onClose={onClose} icon="/mail.png" title="My requests">
      <div style={{ padding: '28px 64px 48px' }}>
        <div style={{ border: `1px solid ${colors.inputBorder}`, borderRadius: 8, overflow: 'hidden', fontSize: 13 }}>
          <div style={{ display: 'grid', gridTemplateColumns: cols, padding: '12px 20px', borderBottom: `1px solid ${colors.inputBorder}`, fontWeight: 500, color: '#222' }}>
            <span>Lab</span>
            <span>Time</span>
            <span>Classroom</span>
            <span>Status</span>
            <span>Note</span>
          </div>
          {items.length === 0 && <div style={{ padding: 20, color: colors.muted }}>ยังไม่มีคำขอ</div>}
          {items.map((b) => (
            <div key={b.id} style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid #eee', color: colors.text }}>
              <span>{b.labTitle}</span>
              <span>
                {WEEKDAYS[b.weekday]} {hhmm(b.startTime)}–{hhmm(b.endTime)}
                <span style={{ display: 'block', fontSize: 11, color: colors.muted }}>{b.validFrom} → {b.validUntil}</span>
              </span>
              <span>{b.mode === 'online' ? 'Online' : b.room ?? '-'}</span>
              <span style={{ color: STATUS[b.status].color, fontWeight: 500 }}>{STATUS[b.status].label}</span>
              <span style={{ fontSize: 12, color: colors.muted }}>{b.decisionNote ?? b.note ?? '-'}</span>
            </div>
          ))}
        </div>
      </div>
    </GradientModal>
  );
}
