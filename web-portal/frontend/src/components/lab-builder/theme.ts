export const colors = {
  navBg: '#0B0B0B',
  primary: '#039AD9',
  primaryHover: '#0289C2',
  pageBg: '#F2F2F2',
  border: '#d9d9d9',
  inputBorder: '#e2e2e2',
  text: '#333',
  muted: '#888',
  blue: '#217AB2',
  yellow: '#FEB449',
} as const;

/** Blue-led pastel mesh used on modal headers (CSS only). */
export const blueMesh = [
  'radial-gradient(60% 95% at 6% 0%, #A8DBF5 0%, rgba(168,219,245,0) 70%)',
  'radial-gradient(50% 85% at 40% 6%, #C4E6FA 0%, rgba(196,230,250,0) 70%)',
  'radial-gradient(45% 85% at 74% 0%, #B3D4F7 0%, rgba(179,212,247,0) 70%)',
  'radial-gradient(45% 95% at 100% 28%, #C3EFF2 0%, rgba(195,239,242,0) 70%)',
].join(',');
