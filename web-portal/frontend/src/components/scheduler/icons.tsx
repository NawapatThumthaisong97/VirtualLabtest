type P = { size?: number; color?: string; width?: number };

export const ChevronLeft = ({ size = 14, color = '#333', width = 2.4 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}><path d="M15 6l-6 6 6 6" /></svg>
);
export const ChevronRight = ({ size = 14, color = '#333', width = 2.4 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}><path d="M9 6l6 6-6 6" /></svg>
);
export const ChevronDown = ({ size = 10, color = '#333', width = 2.4 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}><path d="M6 9l6 6 6-6" /></svg>
);
export const CloseIcon = ({ size = 14, color = '#555', width = 2 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
export const ExternalIcon = ({ size = 16, color = '#333', width = 1.8 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}>
    <path d="M14 4h6v6" /><path d="M20 4l-9 9" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </svg>
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
export const SearchIcon = ({ size = 15, color = 'rgba(255,255,255,0.5)', width = 2 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}><circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
);
export const UserIcon = ({ size = 17, color = 'rgba(255,255,255,0.85)', width = 2 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width}><circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.5-6 8-6s8 2 8 6" /></svg>
);
