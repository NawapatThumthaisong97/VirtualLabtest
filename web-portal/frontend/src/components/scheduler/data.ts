import type { ClassEvent, ClassRequest } from './types';
import type { EventColor } from './theme';
import { toISO } from './date';

/** Sample classes placed relative to the 1st of the current month. */
const seed: { offset: number; title: string; start: string; end: string; color: EventColor }[] = [
  { offset: 2, title: 'Brainstorming Session Test', start: '08:30', end: '09:00', color: 'purple' },
  { offset: 2, title: 'Team Collaboration Meeting', start: '12:00', end: '14:22', color: 'orange' },
  { offset: 2, title: 'Ux Lift On Calender', start: '11:15', end: '12:00', color: 'cyan' },
  { offset: 2, title: 'Igniting Creativity Meeting', start: '11:15', end: '12:00', color: 'green' },
  { offset: 4, title: 'Ux Lift On Calender', start: '11:15', end: '12:00', color: 'cyan' },
  { offset: 14, title: 'Igniting Creativity Meeting', start: '11:15', end: '12:00', color: 'green' },
  { offset: 16, title: 'Annual Report of Marketing & Strategy', start: '00:15', end: '01:00', color: 'blue' },
  { offset: 23, title: 'Software Engineer Lab', start: '13:00', end: '16:00', color: 'purple' },
  { offset: 23, title: 'Web Development Lab', start: '13:00', end: '16:00', color: 'orange' },
  { offset: 27, title: 'Networking System Lab', start: '13:00', end: '16:00', color: 'cyan' },
];

export function seedEvents(today = new Date()): ClassEvent[] {
  return seed.map((s, i) => ({
    id: `seed-${i}`,
    title: s.title,
    date: toISO(new Date(today.getFullYear(), today.getMonth(), 1 + s.offset)),
    start: s.start,
    end: s.end,
    color: s.color,
  }));
}

export const seedRequests: ClassRequest[] = [
  { id: 1, requester: 'Proffresor Thomas young', purpose: 'Course Software Engineer', course: 'Software Engineer', lab: 'Sprint Boots for Java Development', room: 'LC-213', max: 'Max 60 Machines', date: '13:00-14:00 Tuesday', isNew: true },
  { id: 2, requester: 'Dr. Napat Srisuk', purpose: 'Web Development Lab', course: 'Web Development', lab: 'React Fundamentals', room: 'LC-107', max: 'Max 30 Machines', date: '09:00-12:00 Wednesday' },
  { id: 3, requester: 'Ajarn Kanokwan P.', purpose: 'Networking System Lab', course: 'Networking System', lab: 'Cisco Routing Basics', room: 'LC-307', max: 'Max 30 Machines', date: '13:00-16:00 Thursday' },
  { id: 4, requester: 'Dr. Somchai Rattana', purpose: 'Cloud Computing Workshop', course: 'Cloud Computing', lab: 'AWS EC2 Hands-on', room: 'LC-207', max: 'Max 40 Machines', date: '10:00-11:30 Friday' },
];
