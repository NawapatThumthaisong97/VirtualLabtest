import { useEffect, type ReactNode } from 'react';
import { pastelMesh } from './theme';
import { CloseIcon } from './icons';

interface Props {
  open: boolean;
  onClose: () => void;
  icon: string;
  title: string;
  subtitle?: string;
  tab?: string;
  children: ReactNode;
}

/** Shared modal shell: rounded card, pastel mesh header fading to white, icon + title, tab strip. */
export default function GradientModal({ open, onClose, icon, title, subtitle = 'Essentials', tab = 'info', children }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(20,24,32,0.35)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        style={{ position: 'relative', width: '100%', maxWidth: 880, background: '#fff', borderRadius: 24, overflow: 'hidden', boxShadow: '0 1px 2px rgba(0,0,0,0.06), 0 12px 32px rgba(30,40,80,0.10)', border: '1px solid rgba(0,0,0,0.04)' }}
      >
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 210, pointerEvents: 'none', background: pastelMesh }} />
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 210, pointerEvents: 'none', background: 'linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.35) 55%, #fff 100%)' }} />

        <button onClick={onClose} aria-label="Close" style={{ position: 'absolute', top: 18, right: 18, width: 32, height: 32, borderRadius: '50%', border: 0, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1 }}>
          <CloseIcon />
        </button>

        <div style={{ position: 'relative', padding: '36px 72px 0', display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 64, height: 64, borderRadius: 14, background: '#fff', border: '1px solid #e6e6e6', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
            <img src={icon} alt="" style={{ width: 38, height: 38 }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: '#222' }}>{title}</span>
            <span style={{ fontSize: 10, color: '#555' }}>{subtitle}</span>
          </div>
        </div>

        <div style={{ position: 'relative', marginTop: 16, borderBottom: '1px solid #e6e6e6', padding: '0 64px', display: 'flex' }}>
          <span style={{ marginBottom: -1, padding: '6px 28px', fontSize: 14, color: '#333', background: '#fff', border: '1px solid #e6e6e6', borderBottomColor: '#fff' }}>{tab}</span>
        </div>

        <div style={{ position: 'relative' }}>{children}</div>
      </div>
    </div>
  );
}
