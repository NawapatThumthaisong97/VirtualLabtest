/** Lab API Service */
import apiClient from './api';

export type LabStatus = 'draft' | 'published' | 'archived';

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
}

export interface UpdateLabPayload {
  title?: string;
  orderNo?: number;
  description?: string | null;
  docUrl?: string | null;
  imageId?: string | null;
  dueAt?: string | null;
  status?: LabStatus;
}

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
  createdAt: lab.createdAt ?? lab.created_at ?? '',
  updatedAt: lab.updatedAt ?? lab.updated_at ?? null,
});

export const labService = {
  getByCourse: async (courseId: string, status?: LabStatus): Promise<Lab[]> => {
    const params: Record<string, string> = { courseId };
    if (status) params.status = status;
    
    const response = await apiClient.get<{ data: LabApiResponse[] }>('/labs', { params });
    return response.data.map(transformToLab);
  },

  getById: async (labId: string): Promise<Lab> => {
    const response = await apiClient.get<{ data: LabApiResponse }>(`/labs/${labId}`);
    return transformToLab(response.data);
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
    };

    const response = await apiClient.post<{ data: LabApiResponse }>('/labs', apiPayload);
    return transformToLab(response.data);
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

    const response = await apiClient.patch<{ data: LabApiResponse }>(`/labs/${labId}`, apiPayload);
    return transformToLab(response.data);
  },

  delete: async (labId: string): Promise<void> => {
    await apiClient.delete(`/labs/${labId}`);
  },
};
