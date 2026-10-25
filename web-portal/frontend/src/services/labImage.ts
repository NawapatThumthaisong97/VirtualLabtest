/** Lab Image API Service: รายการ image ของวิชา + อัปโหลด .tar ขึ้น R2 ผ่าน presigned PUT */
import axios from 'axios';
import apiClient from './api';
import type { ApiResponse } from './lab';

export type ImageStatus = 'pending' | 'approved' | 'rejected';
export type ScanStatus = 'not_started' | 'queued' | 'running' | 'passed' | 'failed' | 'error';

/** ทุก repository ต้องอยู่ใต้ prefix นี้ (backend บังคับ: ECR sync มีสิทธิ์แค่ repository/vlab/*) */
export const REPOSITORY_PREFIX = 'vlab/';
/** ชื่อที่ระบบจองไว้ (image ของ scanner) */
export const RESERVED_REPOSITORIES = ['vlab/scan-runner'];
/** เพดานของ PUT ครั้งเดียว ต้องตรงกับ LAB_IMAGE_MAX_ARCHIVE_BYTES ของ backend (5 GiB - 5 MiB) */
export const MAX_ARCHIVE_BYTES = 5 * 1024 ** 3 - 5 * 1024 ** 2;

export interface ScanSummary {
  verdict?: 'PASS' | 'FAIL' | 'ERROR';
  reasons?: string[];
  warnings?: string[];
  lastError?: string;
  counts?: Record<string, number>;
  trivyVersion?: string;
  [key: string]: unknown;
}

/** `GET /api/lab-image?courseId=` — LabImageResponse */
export interface LabImage {
  id: string;
  courseId: string;
  repository: string;
  tag: string;
  imageDigest: string | null;
  sizeMb: number;
  description: string | null;
  cpuRequirement: string;
  memoryRequirement: string;
  diskSize: number;
  lifespanMinutes: number;
  exposedPorts: number[];
  entrypointScript: string;
  workdir: string | null;
  envVars: Record<string, string> | null;
  status: ImageStatus;
  scanStatus: ScanStatus;
  scanAttempts: number;
  scanSummary: ScanSummary | null;
  archiveUploadedAt: string | null;
  scanStartedAt: string | null;
  scanFinishedAt: string | null;
  createdAt: string;
}

/** `POST /api/lab-image` — LabImageUploadRequest */
export interface CreateLabImagePayload {
  courseId: string;
  repository: string;
  tag: string;
  fileSizeBytes: number;
  description?: string | null;
  cpuRequirement: string;
  memoryRequirement: string;
  diskSize: number;
  lifespanMinutes: number;
  exposedPorts: number[];
  entrypointScript: string;
  workdir?: string | null;
  envVars?: Record<string, string> | null;
}

/** LabImageUploadResponse */
export interface LabImageUpload {
  imageId: string;
  courseId: string;
  repository: string;
  tag: string;
  status: ImageStatus;
  archiveKey: string;
  uploadUrl: string;
  method: string;
  /** ถูกเซ็นไว้ใน URL ต้องส่งตามนี้ทุกตัว ไม่งั้น R2 ตอบ 403 */
  headers: Record<string, string>;
  expiresAt: string;
}

const unwrap = <T>(response: unknown): T => (response as ApiResponse<T>).data;

/** ข้อความ error จาก envelope ของ backend ({ error: { message } }) หรือจาก axios */
export const apiErrorMessage = (error: any, fallback = 'Please try again.'): string =>
  error?.response?.data?.error?.message ??
  error?.response?.data?.message ??
  error?.response?.data?.detail ??
  error?.message ??
  fallback;

/** image พร้อมใช้กับ lab ได้หรือยัง (สแกนผ่านและ approve แล้ว) */
export const isImageReady = (image: LabImage): boolean => image.status === 'approved';

export const labImageService = {
  listByCourse: async (courseId: string): Promise<LabImage[]> => {
    const response = await apiClient.get('/lab-image', { params: { courseId } });
    return unwrap<LabImage[]>(response) ?? [];
  },

  /** ลบ image (DB + R2 + ECR) และปลดออกจาก lab ที่ใช้อยู่ */
  remove: async (imageId: string): Promise<{ detachedLabs: number }> => {
    const response = await apiClient.delete(`/lab-image/${imageId}`)
    return unwrap<{ detachedLabs: number }>(response)
  },

  /** ขั้นที่ 1: สร้างแถว draft แล้วรับ presigned PUT URL */
  createUpload: async (payload: CreateLabImagePayload): Promise<LabImageUpload> => {
    const response = await apiClient.post('/lab-image', payload);
    return unwrap<LabImageUpload>(response);
  },

  /**
   * ขั้นที่ 2: PUT ไฟล์ตรงเข้า R2
   * ใช้ axios เปล่า (ไม่ใช่ apiClient): ไม่ส่ง cookie / Authorization ไปที่ R2 และไม่ผ่าน interceptor ของ backend
   */
  uploadArchive: async (
    upload: LabImageUpload,
    file: File,
    onProgress?: (percent: number) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    await axios.request({
      url: upload.uploadUrl,
      method: upload.method || 'PUT',
      data: file,
      headers: upload.headers,
      withCredentials: false,
      signal,
      onUploadProgress: (event) => {
        if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100));
      },
    });
  },
};
