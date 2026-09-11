/**
 * Session API Service
 *
 * session หนึ่งตัว = pod หนึ่งตัวบน Kubernetes ที่ SkyPilot สร้างให้จาก image
 * ของ lab นั้น การสร้างจึงใช้เวลาเป็นนาที (ต้อง schedule pod + pull image)
 * ไม่ใช่ request ที่ตอบกลับทันทีเหมือน endpoint อื่น
 */
import apiClient from './api';
import type { ApiResponse } from './lab';

/** พอร์ต -> URL ที่เปิดเข้าได้จริง เช่น { "8443": "http://100.73.174.96:8443" } */
export type SessionEndpoints = Record<string, string>;

/**
 * schema ฝั่ง backend ของ session ใช้ BaseModel ธรรมดา ไม่ใช่ CamelModel
 * เหมือน endpoint อื่น ๆ คีย์ที่ส่งกลับมาจึงเป็น snake_case ทั้งหมด
 * อย่าเผลอเขียนเป็น camelCase เพราะจะได้ undefined เงียบ ๆ
 */
export interface LabSession {
  session_id: string;
  cluster_name: string;
  lab_id: string;
  lab_title: string;
  image_repository: string;
  image_tag: string;
  endpoints: SessionEndpoints;
  status: string;
  started_at: string;
}

export const sessionService = {
  /**
   * สร้าง session ใหม่ — ใช้เวลาราว 1-2 นาที เพราะรอ pod พร้อมก่อนถึงจะตอบกลับ
   * ไม่ได้ตอบทันทีแล้วให้ poll เอา ฉะนั้นฝั่ง UI ต้องมี loader คั่นไว้
   */
  create: async (labId: string, userId: string): Promise<LabSession> => {
    const response = await apiClient.post<ApiResponse<LabSession>>('/sessions', {
      lab_id: labId,
      user_id: userId,
    });
    return (response as unknown as ApiResponse<LabSession>).data;
  },

  /** ปิด session และสั่งลบ pod ทิ้ง */
  remove: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/sessions/${sessionId}`);
  },
};
