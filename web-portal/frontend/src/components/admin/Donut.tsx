import type { ReactNode } from 'react';

export interface DonutSegment {
  value: number; // percent, segments should sum to ≤ 100
  color: string;
}

/** SVG ring chart. r=15.9 gives a circumference of ~100 so dash values = percentages. */
export default function Donut({
  segments,
  track,
  size = 150,
  thickness = 3.5,
  children,
}: {
  segments: DonutSegment[];
  track?: string;
  size?: number;
  thickness?: number;
  children?: ReactNode;
}) {
  let offset = 0;
  return (
    <div style={{ position: 'relative', width: size, height: size, margin: '0 auto' }}>
      <svg viewBox="0 0 42 42" style={{ width: '100%', height: '100%', transform: 'rotate(-90deg)' }}>
        {track && <circle cx="21" cy="21" r="15.9" fill="none" stroke={track} strokeWidth={thickness} />}
        {segments.map((s, i) => {
          const el = (
            <circle
              key={i}
              cx="21"
              cy="21"
              r="15.9"
              fill="none"
              stroke={s.color}
              strokeWidth={thickness}
              strokeDasharray={`${s.value} ${100 - s.value}`}
              strokeDashoffset={-offset}
            />
          );
          offset += s.value;
          return el;
        })}
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        {children}
      </div>
    </div>
  );
}
