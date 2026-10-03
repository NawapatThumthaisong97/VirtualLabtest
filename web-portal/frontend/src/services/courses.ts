/** Course API Service */
import apiClient from './api';
import type { BackgroundKey, IconKey } from '../constants/coursePresets';

export interface Courses {
  id: string;
  code: string;
  name: string;
  lecturerName: string;
  imageUrl: string | null;
  backgroundKey: BackgroundKey | null;
  iconKey: IconKey | null;
}

export interface Announcement {
  id: string;
  message: string;
  createdAt: string;
  authorName: string;
}

export interface CreateAnnouncementPayload {
  message: string;
}

export interface UpdateAnnouncementPayload {
  message: string;
}

export interface CourseDetail extends Courses {
  announcementIds: string[] | null;
  announcements: Announcement[];
}

export interface CreateCoursePayload {
  code: string;
  name: string;
  lecturerName: string;
  imageUrl?: string | null;
  backgroundKey?: BackgroundKey | null;
  iconKey?: IconKey | null;
  // createdBy จะถูกดึงจาก JWT token ใน backend แทน
}

interface CoursesApiResponse {
  id: string;
  code: string;
  name: string;
  lecturer_name?: string;
  image_url?: string | null;
  lecturerName?: string;
  imageUrl?: string | null;
  background_key?: BackgroundKey | null;
  icon_key?: IconKey | null;
  backgroundKey?: BackgroundKey | null;
  iconKey?: IconKey | null;
  announcement_ids?: string[] | null;
  announcementIds?: string[] | null;
  announcements?: {
    id: string;
    message: string;
    created_at?: string;
    createdAt?: string;
    author_name?: string;
    authorName?: string;
  }[];
}

export const coursesService = {
  getAll: async (): Promise<Courses[]> => {
    const response = await apiClient.get<CoursesApiResponse[]>('/courses');
    return (response as unknown as CoursesApiResponse[]).map((course) => ({
      id: course.id,
      code: course.code,
      name: course.name,
      lecturerName: course.lecturerName ?? course.lecturer_name ?? '',
      imageUrl: course.imageUrl ?? course.image_url ?? null,
      backgroundKey: course.backgroundKey ?? course.background_key ?? null,
      iconKey: course.iconKey ?? course.icon_key ?? null,
    }));
  },

  getById: async (id: string): Promise<CourseDetail> => {
    const response = await apiClient.get<CoursesApiResponse>(`/courses/${id}`);
    const course = response as unknown as CoursesApiResponse;
    
    return {
      id: course.id,
      code: course.code,
      name: course.name,
      lecturerName: course.lecturerName ?? course.lecturer_name ?? '',
      imageUrl: course.imageUrl ?? course.image_url ?? null,
      backgroundKey: course.backgroundKey ?? course.background_key ?? null,
      iconKey: course.iconKey ?? course.icon_key ?? null,
      announcementIds: course.announcementIds ?? course.announcement_ids ?? null,
      announcements: (course.announcements || []).map((ann) => ({
        id: ann.id,
        message: ann.message,
        createdAt: ann.createdAt ?? ann.created_at ?? '',
        authorName: ann.authorName ?? ann.author_name ?? '',
      })),
    };
  },

  create: async (payload: CreateCoursePayload): Promise<Courses> => {
    // Transform camelCase to snake_case for API
    const apiPayload = {
      code: payload.code,
      name: payload.name,
      lecturer_name: payload.lecturerName,
      image_url: payload.imageUrl || null,
      background_key: payload.backgroundKey || null,
      icon_key: payload.iconKey || null,
      // created_by will be set from JWT token in backend
    };

    console.log('📤 Creating course with payload:', apiPayload);

    const response = await apiClient.post<CoursesApiResponse>('/courses', apiPayload);
    const course = response as unknown as CoursesApiResponse;
    
    console.log('✅ Course created:', course);
    
    return {
      id: course.id,
      code: course.code,
      name: course.name,
      lecturerName: course.lecturerName ?? course.lecturer_name ?? '',
      imageUrl: course.imageUrl ?? course.image_url ?? null,
      backgroundKey: course.backgroundKey ?? course.background_key ?? null,
      iconKey: course.iconKey ?? course.icon_key ?? null,
    };
  },

  update: async (id: string, payload: Partial<CreateCoursePayload>): Promise<CourseDetail> => {
    // Transform camelCase to snake_case for API
    const apiPayload: Record<string, any> = {};
    if (payload.code !== undefined) apiPayload.code = payload.code;
    if (payload.name !== undefined) apiPayload.name = payload.name;
    if (payload.lecturerName !== undefined) apiPayload.lecturer_name = payload.lecturerName;
    if (payload.imageUrl !== undefined) apiPayload.image_url = payload.imageUrl;
    if (payload.backgroundKey !== undefined) apiPayload.background_key = payload.backgroundKey;
    if (payload.iconKey !== undefined) apiPayload.icon_key = payload.iconKey;

    const response = await apiClient.patch<CoursesApiResponse>(`/courses/${id}`, apiPayload);
    const course = response as unknown as CoursesApiResponse;
    
    return {
      id: course.id,
      code: course.code,
      name: course.name,
      lecturerName: course.lecturerName ?? course.lecturer_name ?? '',
      imageUrl: course.imageUrl ?? course.image_url ?? null,
      backgroundKey: course.backgroundKey ?? course.background_key ?? null,
      iconKey: course.iconKey ?? course.icon_key ?? null,
      announcementIds: course.announcementIds ?? course.announcement_ids ?? null,
      announcements: (course.announcements || []).map((ann) => ({
        id: ann.id,
        message: ann.message,
        createdAt: ann.createdAt ?? ann.created_at ?? '',
        authorName: ann.authorName ?? ann.author_name ?? '',
      })),
    };
  },

  // Announcement APIs
  createAnnouncement: async (courseId: string, payload: CreateAnnouncementPayload): Promise<Announcement> => {
    const response = await apiClient.post<any>(`/courses/${courseId}/announcements`, {
      message: payload.message,
    });
    const announcement = response as any;
    
    return {
      id: announcement.id,
      message: announcement.message,
      createdAt: announcement.createdAt ?? announcement.created_at ?? '',
      authorName: announcement.authorName ?? announcement.author_name ?? '',
    };
  },

  updateAnnouncement: async (courseId: string, announcementId: string, payload: UpdateAnnouncementPayload): Promise<Announcement> => {
    const response = await apiClient.patch<any>(`/courses/${courseId}/announcements/${announcementId}`, {
      message: payload.message,
    });
    const announcement = response as any;
    
    return {
      id: announcement.id,
      message: announcement.message,
      createdAt: announcement.createdAt ?? announcement.created_at ?? '',
      authorName: announcement.authorName ?? announcement.author_name ?? '',
    };
  },

  deleteAnnouncement: async (courseId: string, announcementId: string): Promise<void> => {
    await apiClient.delete(`/courses/${courseId}/announcements/${announcementId}`);
  },

  // Delete course
  deleteCourse: async (courseId: string): Promise<void> => {
    await apiClient.delete(`/courses/${courseId}`);
  },
};