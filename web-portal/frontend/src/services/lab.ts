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

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
  error?: { code: string; message: string };
}

export const labService = {
  getById: async (labId: string): Promise<LabDetail> => {
    // the response interceptor already unwrapped axios' own `.data`,
    // so what lands here is the envelope — `.data` on it is the payload
    const response = await apiClient.get<ApiResponse<LabDetail>>(`/labs/${labId}`);
    return (response as unknown as ApiResponse<LabDetail>).data;
  },

  /** URL the browser fetches the document from — served as a file, not JSON */
  docUrl: (labId: string): string => `${API_URL}/labs/${labId}/doc`,
};
