import type { CSSProperties, ReactNode } from 'react';
import { colors, toneColor, type StatusTone } from './theme';

export function Card({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        background: '#fff',
        border: `1px solid ${colors.border}`,
        borderRadius: '0 0 14px 14px',
        fontSize: 12,
        color: colors.text,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function StatusDot({ tone, label }: { tone: StatusTone; label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: toneColor[tone] }} />
      {label}
    </span>
  );
}

export function ExternalIcon({ color = colors.muted }: { color?: string }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
      <path d="M14 4h6v6" />
      <path d="M20 4l-9 9" />
      <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </svg>
  );
}

export const cellBorder = `1px solid ${colors.border}`;
