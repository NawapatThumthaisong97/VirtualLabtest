export const colors = {
  navBg: '#0B0B0B',
  headerBlue: '#039AD9',
  pageBg: '#F2F2F2',
  border: '#d9d9d9',
  text: '#333',
  muted: '#888',
  blue: '#217AB2',
  yellow: '#FEB449',
  success: '#537F2E',
  error: '#E63529',
  cellRed: '#EFC2BD',
  cellGreen: '#C9D7BE',
  cellYellow: '#EFD7BD',
  chartGreen: '#A3BE8C',
  chartPurple: '#B48EAD',
  chartBlue: '#5E81AC',
  money: '#567839',
  logBar: '#8ED0E5',
  logTitle: '#3AAEE0',
} as const;

export type StatusTone = 'success' | 'error' | 'warning';

export const toneColor: Record<StatusTone, string> = {
  success: colors.success,
  error: colors.error,
  warning: colors.yellow,
};
