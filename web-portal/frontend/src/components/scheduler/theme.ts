export const colors = {
  navBg: '#0B0B0B',
  primary: '#039AD9',
  primaryHover: '#0289C2',
  pageBg: '#F2F2F2',
  border: '#d9d9d9',
  inputBorder: '#e2e2e2',
  text: '#333',
  muted: '#888',
  selected: '#6C6FC4',
  danger: '#E63529',
} as const;

export type EventColor = 'purple' | 'orange' | 'cyan' | 'green' | 'blue';

export const eventColors: Record<EventColor, { color: string; bg: string }> = {
  purple: { color: '#7B5CC4', bg: '#F1ECFB' },
  orange: { color: '#D9822B', bg: '#FDF1E3' },
  cyan: { color: '#2A9FD0', bg: '#E6F5FB' },
  green: { color: '#5E9A2E', bg: '#EEF5E6' },
  blue: { color: '#5E81AC', bg: '#E7EDF5' },
};

/** หัว modal ใช้ mesh ฟ้าตัวเดียวกับ modal ของอาจารย์ (lab-builder) — Pete ขอให้ทุก modal โทนเดียวกัน */
export { blueMesh as pastelMesh } from '../lab-builder/theme';
