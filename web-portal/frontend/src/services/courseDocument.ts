/** เอกสารของวิชาที่ไม่ผูกกับ lab — /api/courses/{courseId}/documents */
import apiClient, { API_URL } from './api';

export interface CourseDocument {
  id: string;
  title: string;
  sizeBytes: number;
  createdAt: string | null;
  uploaderName: string | null;
}

export const courseDocumentService = {
  // route ตอบเป็น list ตรง ๆ (ไม่มี envelope) interceptor ของ apiClient คืน body ให้แล้ว
  list: async (courseId: string): Promise<CourseDocument[]> => {
    const response = await apiClient.get(`/courses/${courseId}/documents`);
    return (response as unknown as CourseDocument[]) ?? [];
  },

  /** title ว่าง = ใช้ชื่อไฟล์ — ส่ง multipart เอง (apiClient ตั้ง JSON ไว้ ดู labService.uploadDoc) */
  upload: async (courseId: string, file: File, title: string): Promise<CourseDocument> => {
    const form = new FormData();
    form.append('document', file);
    form.append('title', title);
    const response = await apiClient.post(`/courses/${courseId}/documents`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response as unknown as CourseDocument;
  },

  remove: async (courseId: string, documentId: string): Promise<void> => {
    await apiClient.delete(`/courses/${courseId}/documents/${documentId}`);
  },

  /** เปิดในแท็บใหม่ได้ตรง ๆ เพราะ cookie access_token ติดไปเอง (แบบ labService.docUrl) */
  fileUrl: (courseId: string, documentId: string): string =>
    `${API_URL}/courses/${courseId}/documents/${documentId}/file`,
};

export interface DocumentRow {
  id: string;
  title: string;
  href: string;
  /** ป้ายด้านขวาในการ์ด Documents: "Course" หรือ "Lab N" */
  tag: string;
}

/** การ์ด Documents: เอกสารรวมของวิชาก่อน แล้วตามด้วยเอกสารของแต่ละ lab ตามลำดับ lab */
export function documentRows(
  courseId: string,
  courseDocs: CourseDocument[],
  labs: { id: string; title: string; orderNo: number; docUrl: string | null }[],
  labDocUrl: (labId: string) => string,
): DocumentRow[] {
  const course = courseDocs.map((doc) => ({
    id: doc.id,
    title: doc.title,
    href: courseDocumentService.fileUrl(courseId, doc.id),
    tag: 'Course',
  }));
  const lab = labs
    .filter((item) => Boolean(item.docUrl))
    .sort((a, b) => a.orderNo - b.orderNo)
    .map((item) => ({ id: item.id, title: item.title, href: labDocUrl(item.id), tag: `Lab ${item.orderNo}` }));
  return [...course, ...lab];
}
