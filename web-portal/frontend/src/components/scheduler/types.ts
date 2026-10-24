import type { EventColor } from './theme';

export interface ClassEvent {
  id: string;
  title: string;
  /** ISO date yyyy-mm-dd */
  date: string;
  /** 24h HH:mm */
  start: string;
  end: string;
  color: EventColor;
}

export interface ClassRequest {
  id: number;
  requester: string;
  purpose: string;
  course: string;
  lab: string;
  room: string;
  max: string;
  /** e.g. "13:00-14:00 Tuesday" */
  date: string;
  isNew?: boolean;
}

export interface EventForm {
  course: string;
  instructor: string;
  lab: string;
  room: string;
  max: string;
  date: string;
  start: string;
  end: string;
}
