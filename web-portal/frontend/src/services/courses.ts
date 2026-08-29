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
};