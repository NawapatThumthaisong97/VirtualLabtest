/**
 * อัปโหลด .tar ของ lab image แบบเบื้องหลัง (docs/LAB_IMAGE_UPLOAD_PLAN.md ข้อ 3.4)
 *
 * เดิมสถานะการอัปโหลดอยู่ใน component (LabImageTab / CreateLabModal) พอเปลี่ยนหน้า component ถูกถอด
 * การอัปโหลดก็ถูกยกเลิกตาม ไฟล์ทั้งก้อนต้องส่งจาก browser ขึ้น R2 เอง (presigned PUT) server ส่งแทนไม่ได้
 *
 * ที่นี่ย้ายสถานะไปไว้ใน zustand store ระดับโมดูล ซึ่งอยู่ตลอดอายุของแท็บ ไม่ผูกกับหน้าไหน
 * - เปลี่ยนหน้าในเว็บ (client-side routing) = อัปโหลดต่อ
 * - reload / ปิดแท็บ = หาย (ไฟล์อยู่ในหน่วยความจำของแท็บ) UploadTray จึงเตือนก่อนด้วย beforeunload
 */
import { create } from 'zustand';
import { useToastStore } from '../hooks/useToast';
import {
  apiErrorMessage,
  labImageService,
  type CreateLabImagePayload,
  type LabImageUpload,
} from './labImage';

export type UploadStatus = 'uploading' | 'done' | 'failed' | 'canceled';

/** สิ่งที่ UI แสดง (ค่าธรรมดาทั้งหมด เปลี่ยนแล้ว component ที่ subscribe อยู่ render ใหม่) */
export interface UploadItem {
  /** = imageId ของแถว draft (อัปซ้ำด้วยชื่อ / tag เดิม backend คืนแถวเดิม จึงได้ id เดิม) */
  id: string;
  courseId: string;
  /** vlab/<name>:<tag> */
  label: string;
  fileName: string;
  percent: number;
  status: UploadStatus;
  error?: string;
  /** false = ลองใหม่ไม่มีประโยชน์ (เช่น ไฟล์ถูกอัปไปแล้ว) */
  retryable?: boolean;
}

/** ของที่ UI ไม่ต้องเห็นและไม่ควรอยู่ใน store (File / AbortController ไม่ใช่ข้อมูลธรรมดา) */
interface Job {
  file: File;
  payload: CreateLabImagePayload;
  controller: AbortController | null;
}

/** การอัปโหลดที่เสร็จแล้วหายจากถาดเองหลังเวลานี้ (ที่ล้มค้างไว้จนกว่าจะกดปิด) */
export const DONE_DISMISS_MS = 8_000;

interface UploadState {
  uploads: UploadItem[];
}

export const useUploadStore = create<UploadState>(() => ({ uploads: [] }));

const jobs = new Map<string, Job>();

const patch = (id: string, changes: Partial<UploadItem>) =>
  useUploadStore.setState((state) => ({
    uploads: state.uploads.map((u) => (u.id === id ? { ...u, ...changes } : u)),
  }));

/** ข้อความเมื่อ PUT ไป R2 ล้ม (ย้ายมาจาก LabImageTab เดิม) */
const describeFailure = (error: any): { message: string; retryable: boolean } => {
  const status = error?.response?.status;
  if (status === 412) {
    // R2 ตอบ 412 เพราะ URL เซ็น If-None-Match ไว้ = มีไฟล์ของ image นี้อยู่แล้ว อัปทับไม่ได้
    return { message: 'A file was already uploaded for this image. Use a new tag to upload again.', retryable: false };
  }
  if (status === 403) {
    return { message: 'The upload link expired. Retry to get a new one.', retryable: true };
  }
  return { message: 'Check your connection and retry.', retryable: true };
};

const isCanceled = (error: any) => error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED';

async function runPut(id: string, upload: LabImageUpload): Promise<void> {
  const job = jobs.get(id);
  if (!job) return;
  const controller = new AbortController();
  job.controller = controller;
  patch(id, { status: 'uploading', percent: 0, error: undefined, retryable: undefined });

  let last = -1;
  try {
    await labImageService.uploadArchive(
      upload,
      job.file,
      (percent) => {
        // axios ยิง progress ถี่มาก อัปเดต store เฉพาะตอนเลขเปลี่ยน
        if (percent !== last) {
          last = percent;
          patch(id, { percent });
        }
      },
      controller.signal,
    );
  } catch (error) {
    // ถูกแทนที่ด้วยรอบใหม่ (อัปไฟล์เดิมซ้ำ / retry) ระหว่างรอ: ไม่ต้องรายงานอะไร
    if (jobs.get(id)?.controller !== controller) return;
    job.controller = null;
    if (isCanceled(error)) {
      patch(id, { status: 'canceled' });
      return;
    }
    const { message, retryable } = describeFailure(error);
    patch(id, { status: 'failed', error: message, retryable });
    useToastStore.getState().error('Upload failed', `${upload.repository}:${upload.tag}: ${message}`);
    return;
  }

  if (jobs.get(id)?.controller !== controller) return;
  // เสร็จแล้วไม่ต้องเก็บไฟล์ไว้ในหน่วยความจำอีก
  jobs.delete(id);
  patch(id, { status: 'done', percent: 100 });
  useToastStore.getState().success('Upload complete', `${upload.repository}:${upload.tag} is queued for a security scan.`);
  window.setTimeout(() => dismissUpload(id), DONE_DISMISS_MS);
}

/**
 * เริ่ม PUT ไฟล์ขึ้น R2 เบื้องหลัง เรียกหลัง labImageService.createUpload สำเร็จแล้ว
 * (ผู้เรียกจัดการ error ของ createUpload เอง เช่น 409 ชื่อซ้ำ จะได้แสดงในฟอร์ม)
 *
 * คืน promise ที่จบเมื่ออัปเสร็จ / ล้ม / ถูกยกเลิก ไม่ต้อง await ก็ได้ (และไม่ throw)
 */
export function startUpload(upload: LabImageUpload, file: File, payload: CreateLabImagePayload): Promise<void> {
  const id = upload.imageId;
  // อัป image เดิมซ้ำระหว่างที่รอบก่อนยังไม่จบ: ยกเลิกรอบก่อน
  const previous = jobs.get(id);
  jobs.set(id, { file, payload, controller: null });
  previous?.controller?.abort();

  const item: UploadItem = {
    id,
    courseId: upload.courseId,
    label: `${upload.repository}:${upload.tag}`,
    fileName: file.name,
    percent: 0,
    status: 'uploading',
  };
  useUploadStore.setState((state) => ({
    uploads: [...state.uploads.filter((u) => u.id !== id), item],
  }));
  return runPut(id, upload);
}

/**
 * ลองใหม่: ขอ presigned URL ใหม่ (URL เดิมอาจหมดอายุ) ด้วย payload เดิม backend คืนแถว draft เดิม
 * แล้ว PUT ไฟล์เดิมที่ยังอยู่ในหน่วยความจำ
 */
export async function retryUpload(id: string): Promise<void> {
  const job = jobs.get(id);
  if (!job) return;
  patch(id, { status: 'uploading', percent: 0, error: undefined, retryable: undefined });
  let upload: LabImageUpload;
  try {
    upload = await labImageService.createUpload(job.payload);
  } catch (error: any) {
    // 409 = แถวนี้ไม่ใช่ draft ที่ว่างแล้ว เช่น ไฟล์ขึ้น R2 ไปแล้วจริงแต่ browser เห็นเป็น error (เน็ตหลุดตอนรอคำตอบ)
    // ลองกี่รอบก็ได้ 409 เหมือนเดิม จึงไม่ให้กดซ้ำ ให้ไปดูสถานะในหน้า Lab images แทน
    const conflict = error?.response?.status === 409;
    patch(id, {
      status: 'failed',
      error: conflict ? 'This image already has a file. Check its status in Lab images.' : apiErrorMessage(error),
      retryable: !conflict,
    });
    return;
  }
  await runPut(id, upload);
}

export function cancelUpload(id: string): void {
  jobs.get(id)?.controller?.abort();
}

/** เอาออกจากถาด (และทิ้งไฟล์ที่ถืออยู่) */
export function dismissUpload(id: string): void {
  const job = jobs.get(id);
  if (job?.controller) return; // ยังอัปอยู่ ต้องยกเลิกก่อน
  jobs.delete(id);
  useUploadStore.setState((state) => ({ uploads: state.uploads.filter((u) => u.id !== id) }));
}

export const isUploading = (u: UploadItem) => u.status === 'uploading';

/** สำหรับเทส: ล้างสถานะทั้งหมด */
export function resetUploads(): void {
  jobs.forEach((job) => job.controller?.abort());
  jobs.clear();
  useUploadStore.setState({ uploads: [] });
}
