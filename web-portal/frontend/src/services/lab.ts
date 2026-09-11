/**
 * Lab API Service
 * All API calls related to labs
 */
import apiClient, { API_URL } from './api';

export interface CourseBrief {
  id: string;
  code: string;
  name: string;
}

export type LabStatus = 'draft' | 'published';

/** `GET /api/labs/:labId` — matches LabDetailResponse on the backend */
export interface LabDetail {
  id: string;
  title: string;
  description: string | null;
  /** internal storage key, NOT a browser URL — use labService.docUrl() instead */
  docUrl: string | null;
  orderNo: number;
  dueAt: string | null;
  status: LabStatus;
  course: CourseBrief;
}

/** ความคืบหน้าของผู้ใช้ที่ล็อกอิน — null คือยังไม่เคยเปิดทำ lab นี้ */
export type ProgressStatus = 'not_started' | 'in_progress' | 'finished';

/** `GET /api/labs?courseId=` — LabResponse (ไม่มี course ติดมาเหมือน detail) */
export interface LabSummary {
  id: string;
  title: string;
  description: string | null;
  docUrl: string | null;
  orderNo: number;
  dueAt: string | null;
  status: LabStatus;
  progressStatus: ProgressStatus | null;
}

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
  error?: { code: string; message: string };
}

export const labService = {
  listByCourse: async (courseId: string): Promise<LabSummary[]> => {
    const response = await apiClient.get<ApiResponse<LabSummary[]>>('/labs', {
      params: { courseId },
    });
    return (response as unknown as ApiResponse<LabSummary[]>).data ?? [];
  },

  getById: async (labId: string): Promise<LabDetail> => {
    // the response interceptor already unwrapped axios' own `.data`,
    // so what lands here is the envelope — `.data` on it is the payload
    const response = await apiClient.get<ApiResponse<LabDetail>>(`/labs/${labId}`);
    return (response as unknown as ApiResponse<LabDetail>).data;
  },

  /**
   * URL ดิบของเอกสาร
   *
   * ⚠️ ใช้ได้เฉพาะกรณีที่ไม่ต้องแนบ token — เบราว์เซอร์จะยิงเองโดยไม่มี
   * Authorization header ตอนนี้ GET /labs/:id/doc ต้องใช้ token จึงตอบ 401
   * ถ้าจะเปิดเอกสารจริงให้ใช้ fetchDoc() ข้างล่างแทน
   *
   * ยังไม่ลบทิ้งเพราะ CourseDetail ใช้เป็น href อยู่ — ซึ่งก็เจอปัญหาเดียวกัน
   * และต้องแก้ตามมาในภายหลัง
   */
  docUrl: (labId: string): string => `${API_URL}/labs/${labId}/doc`,

  /**
   * ดึงไฟล์เอกสารมาเป็น ArrayBuffer ผ่าน apiClient
   *
   * ห้ามส่ง URL ดิบให้ react-pdf โหลดเอง เพราะมันยิง fetch ของตัวเองซึ่งไม่ผ่าน
   * interceptor ของ axios เลยไม่มี Authorization header ติดไป endpoint นี้ต้องใช้
   * token จึงตอบ 401 แล้วหน้าเว็บขึ้น "เปิดเอกสารไม่สำเร็จ" ทั้งที่ยิงด้วย curl
   * พร้อม token ได้ 200 ปกติ
   *
   * ดึงมาเป็น buffer แล้วส่งเข้า <Document file={{ data }} /> แทน
   */
  fetchDoc: async (labId: string): Promise<ArrayBuffer> => {
    const response = await apiClient.get(`/labs/${labId}/doc`, {
      responseType: 'arraybuffer',
    });
    return response as unknown as ArrayBuffer;
  },
};
