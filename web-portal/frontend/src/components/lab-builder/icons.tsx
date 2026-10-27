type P = { size?: number; color?: string; width?: number };

export const CloseIcon = ({ size = 14, color = '#555', width = 2 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
export const BookIcon = ({ size = 18, color = '#333', width = 1.8 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}>
    <path d="M5 4h11a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z" /><path d="M5 18a2 2 0 0 1 2-2h11" />
  </svg>
);
export const UsersIcon = ({ size = 18, color = '#333', width = 1.8 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}>
    <circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c0-3.5 3-5.5 6.5-5.5s6.5 2 6.5 5.5" /><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8" /><path d="M18 14.8c2 .6 3.5 2.3 3.5 5.2" />
  </svg>
);
