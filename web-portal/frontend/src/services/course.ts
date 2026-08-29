/** Course API Service */
import apiClient, { API_URL } from './api';

export interface CourseDetail {
  id: string;
  code: string;
  name: string;
  lecturerName: string;
  imageUrl: string | null;
  announcements: Announcement[];
}

export interface Announcement {
  id: string;
  message: string;
  createdAt: string | null;
}

interface CourseApiResponse {
  id: string;
  code: string;
  name: string;
  lecturer_name?: string;
  lecturerName?: string;
  image_url?: string | null;
  imageUrl?: string | null;
  announcements?: Array<{
    id: string;
    message: string;
    created_at?: string | null;
    createdAt?: string | null;
  }>;
}

export const courseService = {
  getById: async (courseId: string): Promise<CourseDetail> => {
    const response = await apiClient.get<CourseApiResponse>(`/courses/${courseId}`);
    const data = response as unknown as CourseApiResponse;

    return {
      id: data.id,
      code: data.code,
      name: data.name,
      lecturerName: data.lecturerName ?? data.lecturer_name ?? '',
      imageUrl: data.imageUrl ?? data.image_url ?? null,
      announcements: (data.announcements ?? []).map((a) => ({
        id: a.id,
        message: a.message,
        createdAt: a.createdAt ?? a.created_at ?? null,
      })),
    };
  },

  getAll: async (): Promise<Array<{ id: string; code: string; name: string; lecturerName: string; imageUrl: string | null }>> => {
    const response = await apiClient.get<CourseApiResponse[]>('/courses');
    return (response as unknown as CourseApiResponse[]).map((course) => ({
      id: course.id,
      code: course.code,
      name: course.name,
      lecturerName: course.lecturerName ?? course.lecturer_name ?? '',
      imageUrl: course.imageUrl ?? course.image_url ?? null,
    }));
  },

  imageUrl: (courseId: string): string => `${API_URL}/courses/${courseId}/image`,
};
