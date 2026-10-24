export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
export const WEEKDAYS_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const pad = (n: number) => String(n).padStart(2, '0');

export const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export const fromISO = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
};

export const sameDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

/** Monday-first grid covering the whole month (28–31 days → 4–6 rows). */
export function monthGrid(year: number, month: number): Date[] {
  const lead = (new Date(year, month, 1).getDay() + 6) % 7;
  const count = new Date(year, month + 1, 0).getDate();
  const cells = Math.ceil((lead + count) / 7) * 7;
  return Array.from({ length: cells }, (_, i) => new Date(year, month, 1 - lead + i));
}

/** "13:00" → "1:00 PM" */
export function to12h(t: string) {
  if (!t) return '';
  const [h, m] = t.split(':').map(Number);
  return `${h % 12 || 12}:${pad(m)} ${h >= 12 ? 'PM' : 'AM'}`;
}

/** Next date (from `from`, inclusive) that falls on the given English weekday name. */
export function nextWeekday(dayName: string, from = new Date()) {
  const target = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'].indexOf(dayName);
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  if (target >= 0) d.setDate(d.getDate() + ((target - d.getDay() + 7) % 7));
  return d;
}
