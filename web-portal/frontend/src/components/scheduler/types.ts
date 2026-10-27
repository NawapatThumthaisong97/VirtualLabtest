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
  id: string;
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

/** ฟอร์ม Class Scheduler — ค่าจริงส่งเข้า API (approve / create) */
export interface EventForm {
  /** มี = เปิดจากคำขออาจารย์ (Approve / Reject) ไม่มี = Create new event */
  bookingId?: string;
  courseId: string;
  labId: string;
  room: string;
  machines: number;
  /** คาบแรก yyyy-mm-dd */
  date: string;
  start: string;
  end: string;
  /** ทำซ้ำทุกสัปดาห์ถึงวันที่ yyyy-mm-dd */
  until: string;
  note: string;
}
