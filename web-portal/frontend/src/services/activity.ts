/** กิจกรรมล่าสุดของคนที่ login — GET /api/v1/me/activity (กล่อง Activity Logging หน้า home) */
import apiClient from './api';
import type { Entry } from '../components/EntryBox';

export type ActivityKind =
  | 'session_running'
  | 'session_ended'
  | 'session_failed'
  | 'lab_finished'
  | 'image_passed'
  | 'image_failed'
  | 'lab_draft'
  | 'launch_count';

export interface Activity {
  kind: ActivityKind;
  at: string | null;
  courseCode: string;
  title: string;
  labId: string | null;
  courseId: string | null;
  detail: {
    expires_at?: string | null;
    pending?: boolean;
    minutes?: number | null;
    end_reason?: string | null;
    count?: number;
  };
}

export const activityService = {
  getMine: async (limit = 3): Promise<Activity[]> => {
    const response = (await apiClient.get('/v1/me/activity', { params: { limit } })) as unknown as { data: Activity[] };
    return response.data ?? [];
  },
};

const END_REASON: Record<string, string> = {
  user_delete: 'ปิดเอง',
  expired: 'หมดเวลา',
  lost: 'เครื่องหลุด',
  launch_failed: 'เปิดไม่สำเร็จ',
  stale_pending: 'เปิดค้าง',
};

/** "28 ต.ค. 14:05" ตามเวลาเครื่องผู้ใช้ */
function when(iso: string | null | undefined): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function clock(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) : '';
}

/** แปลงกิจกรรมเป็นแถวของ EntryBox (ชื่อตัวหนา + ข้อความบรรทัดเดียว) */
export function toEntry(item: Activity): Entry {
  const name = item.kind === 'launch_count' ? item.courseCode : `${item.courseCode} · ${item.title}`;
  const d = item.detail;
  switch (item.kind) {
    case 'session_running':
      return { name, text: d.pending ? 'กำลังเตรียม lab…' : `กำลังรันอยู่ — หมดเวลา ${clock(d.expires_at)}` };
    case 'session_ended': {
      const used = d.minutes != null ? `ใช้ไป ${d.minutes} นาที` : 'ปิดแล้ว';
      const reason = d.end_reason ? ` · ${END_REASON[d.end_reason] ?? d.end_reason}` : '';
      return { name, text: `${used}${reason} — ${when(item.at)}` };
    }
    case 'session_failed':
      return { name, text: `เปิด lab ไม่สำเร็จ — ${when(item.at)}` };
    case 'lab_finished':
      return { name, text: `ทำเสร็จแล้ว — ${when(item.at)}` };
    case 'image_passed':
      return { name, text: 'image สแกนผ่านแล้ว — Publish lab ที่ใช้ image นี้ได้' };
    case 'image_failed':
      return { name, text: 'image สแกนไม่ผ่าน — ดูเหตุผลแล้วอัปโหลดใหม่' };
    case 'lab_draft':
      return { name, text: 'ยังเป็น draft — นักศึกษายังมองไม่เห็น' };
    case 'launch_count':
      return { name, text: `นักศึกษาเปิด lab วันนี้ ${d.count ?? 0} ครั้ง` };
  }
}
