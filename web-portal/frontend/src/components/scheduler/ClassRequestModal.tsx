import { colors } from './theme';
import type { ClassRequest } from './types';
import GradientModal from './GradientModal';
import { ExternalIcon } from './icons';

interface Props {
  open: boolean;
  requests: ClassRequest[];
  showNew: boolean;
  onClose: () => void;
  onOpenDetail: (r: ClassRequest) => void;
}

const cols = '1.4fr 1.4fr 0.8fr 1.2fr 60px';

export default function ClassRequestModal({ open, requests, showNew, onClose, onOpenDetail }: Props) {
  return (
    <GradientModal open={open} onClose={onClose} icon="/mail.png" title="Class Request">
      <div style={{ padding: '28px 64px 48px' }}>
        <div style={{ border: `1px solid ${colors.inputBorder}`, borderRadius: 8, overflow: 'hidden', fontSize: 13 }}>
          <div style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', padding: '12px 20px', borderBottom: `1px solid ${colors.inputBorder}`, fontWeight: 500, color: '#222' }}>
            <span>Requester</span>
            <span>Purpose</span>
            <span>Classroom</span>
            <span>Date</span>
            <span style={{ textAlign: 'center' }}>Detail</span>
          </div>

          {requests.length === 0 && <div style={{ padding: '20px', color: colors.muted }}>No pending requests</div>}

          {requests.map((r) => (
            <div key={r.id} style={{ display: 'grid', gridTemplateColumns: cols, alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #eee', color: colors.text }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                {showNew && r.isNew && <span style={{ width: 6, height: 6, borderRadius: '50%', background: colors.danger, flexShrink: 0 }} />}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.requester}</span>
              </span>
              <span>{r.purpose}</span>
              <span>{r.room}</span>
              <span>{r.date}</span>
              <button onClick={() => onOpenDetail(r)} aria-label={`Open request from ${r.requester}`} style={{ justifySelf: 'center', border: 0, background: 'none', cursor: 'pointer', padding: 4, display: 'flex', borderRadius: 4 }}>
                <ExternalIcon />
              </button>
            </div>
          ))}
        </div>
      </div>
    </GradientModal>
  );
}
