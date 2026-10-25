/** Lab API Service */
import apiClient, { API_URL } from './api';

export type LabStatus = 'draft' | 'published' | 'archived';
/** kubernetes = เครื่องในแลป, aws = EC2, auto = เลือกตามเครื่องที่กด Start */
export type RunTarget = 'kubernetes' | 'aws' | 'auto';

export interface Lab {
  id: string;
  courseId: string;
  title: string;
  orderNo: number;
  description: string | null;
  docUrl: string | null;
  imageId: string | null;
  dueAt: string | null;
  status: LabStatus;
  runTarget: RunTarget;
  createdAt: string;
  updatedAt: string | null;
}

export interface CreateLabPayload {
  courseId: string;
  title: string;
  orderNo: number;
  description?: string | null;
  docUrl?: string | null;
  imageId?: string | null;
  dueAt?: string | null;
  status?: LabStatus;
  runTarget?: RunTarget;
}

export interface UpdateLabPayload {
  title?: string;
  orderNo?: number;
  description?: string | null;
  docUrl?: string | null;
  imageId?: string | null;
  dueAt?: string | null;
  status?: LabStatus;
  runTarget?: RunTarget;
}

export interface CourseBrief {
  id: string;
  code: string;
  name: string;
}

/** `GET /api/labs/:labId` — matches LabDetailResponse on the backend (หน้า lab ของนักศึกษา) */
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

// response interceptor (api.ts) แกะ `.data` ของ axios ออกให้แล้ว ที่ได้คือ envelope ด้านบน
const unwrap = <T>(response: unknown): T => (response as ApiResponse<T>).data;

interface LabApiResponse {
  id: string;
  course_id?: string;
  courseId?: string;
  title: string;
  order_no?: number;
  orderNo?: number;
  description: string | null;
  doc_url?: string | null;
  docUrl?: string | null;
  image_id?: string | null;
  imageId?: string | null;
  due_at?: string | null;
  dueAt?: string | null;
  status: LabStatus;
  run_target?: RunTarget | null;
  runTarget?: RunTarget | null;
  created_at?: string;
  createdAt?: string;
  updated_at?: string | null;
  updatedAt?: string | null;
}

const transformToLab = (lab: LabApiResponse): Lab => ({
  id: lab.id,
  courseId: lab.courseId ?? lab.course_id ?? '',
  title: lab.title,
  orderNo: lab.orderNo ?? lab.order_no ?? 0,
  description: lab.description,
  docUrl: lab.docUrl ?? lab.doc_url ?? null,
  imageId: lab.imageId ?? lab.image_id ?? null,
  dueAt: lab.dueAt ?? lab.due_at ?? null,
  status: lab.status,
  runTarget: lab.runTarget ?? lab.run_target ?? 'kubernetes',
  createdAt: lab.createdAt ?? lab.created_at ?? '',
  updatedAt: lab.updatedAt ?? lab.updated_at ?? null,
});

export const labService = {
  getByCourse: async (courseId: string, status?: LabStatus): Promise<Lab[]> => {
    const params: Record<string, string> = { courseId };
    if (status) params.status = status;
    
    const response = await apiClient.get('/labs', { params });
    return unwrap<LabApiResponse[]>(response).map(transformToLab);
  },

  getById: async (labId: string): Promise<Lab> => {
    const response = await apiClient.get(`/labs/${labId}`);
    return transformToLab(unwrap<LabApiResponse>(response));
  },

  create: async (payload: CreateLabPayload): Promise<Lab> => {
    const apiPayload = {
      course_id: payload.courseId,
      title: payload.title,
      order_no: payload.orderNo,
      description: payload.description || null,
      doc_url: payload.docUrl || null,
      image_id: payload.imageId || null,
      due_at: payload.dueAt || null,
      status: payload.status || 'draft',
      run_target: payload.runTarget || 'kubernetes',
    };

    const response = await apiClient.post('/labs', apiPayload);
    return transformToLab(unwrap<LabApiResponse>(response));
  },

  update: async (labId: string, payload: UpdateLabPayload): Promise<Lab> => {
    const apiPayload: Record<string, any> = {};
    if (payload.title !== undefined) apiPayload.title = payload.title;
    if (payload.orderNo !== undefined) apiPayload.order_no = payload.orderNo;
    if (payload.description !== undefined) apiPayload.description = payload.description;
    if (payload.docUrl !== undefined) apiPayload.doc_url = payload.docUrl;
    if (payload.imageId !== undefined) apiPayload.image_id = payload.imageId;
    if (payload.dueAt !== undefined) apiPayload.due_at = payload.dueAt;
    if (payload.status !== undefined) apiPayload.status = payload.status;
    if (payload.runTarget !== undefined) apiPayload.run_target = payload.runTarget;

    const response = await apiClient.patch(`/labs/${labId}`, apiPayload);
    return transformToLab(unwrap<LabApiResponse>(response));
  },

  delete: async (labId: string): Promise<void> => {
    await apiClient.delete(`/labs/${labId}`);
  },

  // ---------- หน้านักศึกษา (CourseDetail / LabDetail) ----------

  listByCourse: async (courseId: string): Promise<LabSummary[]> => {
    const response = await apiClient.get('/labs', { params: { courseId } });
    return unwrap<LabSummary[]>(response) ?? [];
  },

  /** รายละเอียด lab พร้อม course — getById ข้างบนคืน Lab แบบที่หน้าอาจารย์ใช้ */
  getDetail: async (labId: string): Promise<LabDetail> => {
    const response = await apiClient.get(`/labs/${labId}`);
    return unwrap<LabDetail>(response);
  },

  /**
   * URL ดิบของเอกสาร — เบราว์เซอร์เปิดเองได้เพราะ cookie access_token ติดไปเอง
   * (react-pdf ใช้ fetchDoc ข้างล่างแทน)
   */
  docUrl: (labId: string): string => `${API_URL}/labs/${labId}/doc`,

  /** ดึงไฟล์เอกสารมาเป็น ArrayBuffer ผ่าน apiClient แล้วส่งเข้า <Document file={{ data }} /> */
  fetchDoc: async (labId: string): Promise<ArrayBuffer> => {
    const response = await apiClient.get(`/labs/${labId}/doc`, { responseType: 'arraybuffer' });
    return response as unknown as ArrayBuffer;
  },
};
