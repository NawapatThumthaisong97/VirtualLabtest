import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// labImageService คุยกับ backend / R2 จริง แทนด้วยของปลอมที่คุมผลได้
const uploadArchive = vi.fn();
const createUpload = vi.fn();
vi.mock('../services/labImage', () => ({
  labImageService: {
    uploadArchive: (...args: unknown[]) => uploadArchive(...args),
    createUpload: (...args: unknown[]) => createUpload(...args),
  },
  apiErrorMessage: (e: any) => e?.message ?? 'error',
}));

import {
  cancelUpload,
  dismissUpload,
  resetUploads,
  retryUpload,
  startUpload,
  useUploadStore,
} from '../services/labImageUploads';
import { useToastStore } from '../hooks/useToast';

const upload = (overrides = {}) => ({
  imageId: 'img-1',
  courseId: 'course-1',
  repository: 'vlab/web',
  tag: 'v1',
  status: 'pending' as const,
  archiveKey: 'k',
  uploadUrl: 'https://r2.example/put',
  method: 'PUT',
  headers: {},
  expiresAt: '2026-11-18T00:00:00Z',
  ...overrides,
});
const payload = { courseId: 'course-1', repository: 'vlab/web', tag: 'v1', fileSizeBytes: 3, cpuRequirement: '2+', memoryRequirement: '4+', diskSize: 50, lifespanMinutes: 60 };
const file = () => new File(['tar'], 'web.tar');
const items = () => useUploadStore.getState().uploads;
const httpError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { response: { status } });

/** PUT ที่ค้างอยู่จนกว่าเทสจะสั่งให้จบ (จำลองไฟล์ใหญ่ที่อัปหลายนาที) */
function pendingPut() {
  let resolve!: () => void;
  let reject!: (e: unknown) => void;
  let progress!: (p: number) => void;
  uploadArchive.mockImplementationOnce((_u, _f, onProgress, signal: AbortSignal) => {
    progress = onProgress;
    return new Promise<void>((res, rej) => {
      resolve = res;
      reject = rej;
      signal.addEventListener('abort', () => rej(Object.assign(new Error('canceled'), { name: 'CanceledError' })));
    });
  });
  return { resolve: () => resolve(), reject: (e: unknown) => reject(e), progress: (p: number) => progress(p) };
}

beforeEach(() => {
  resetUploads();
  useToastStore.setState({ toasts: [] });
  uploadArchive.mockReset();
  createUpload.mockReset();
});
afterEach(() => vi.useRealTimers());

describe('labImageUploads: upload that survives page changes', () => {
  it('shows progress in the store while the PUT runs, then marks it done', async () => {
    const put = pendingPut();
    const finished = startUpload(upload(), file(), payload);

    expect(items()).toMatchObject([{ id: 'img-1', label: 'vlab/web:v1', status: 'uploading', percent: 0 }]);
    put.progress(42);
    expect(items()[0].percent).toBe(42);

    put.resolve();
    await finished;
    expect(items()[0]).toMatchObject({ status: 'done', percent: 100 });
    expect(useToastStore.getState().toasts.map((t) => t.type)).toEqual(['success']);
  });

  it('done uploads leave the tray by themselves', async () => {
    vi.useFakeTimers();
    uploadArchive.mockResolvedValueOnce(undefined);
    await startUpload(upload(), file(), payload);
    expect(items()).toHaveLength(1);
    vi.runAllTimers();
    expect(items()).toHaveLength(0);
  });

  it('cancel aborts the PUT and does not raise an error toast', async () => {
    pendingPut();
    const finished = startUpload(upload(), file(), payload);
    cancelUpload('img-1');
    await finished;
    expect(items()[0].status).toBe('canceled');
    expect(useToastStore.getState().toasts).toEqual([]);
  });

  it('412 (file already uploaded) fails without a retry button', async () => {
    uploadArchive.mockRejectedValueOnce(httpError(412));
    await startUpload(upload(), file(), payload);
    expect(items()[0]).toMatchObject({ status: 'failed', retryable: false });
    expect(items()[0].error).toMatch(/already uploaded/);
  });

  it('retry asks for a new presigned URL (old one may have expired) and PUTs the same file again', async () => {
    const original = file();
    uploadArchive.mockRejectedValueOnce(httpError(403));
    await startUpload(upload(), original, payload);
    expect(items()[0]).toMatchObject({ status: 'failed', retryable: true });

    createUpload.mockResolvedValueOnce(upload({ uploadUrl: 'https://r2.example/put-2' }));
    uploadArchive.mockResolvedValueOnce(undefined);
    await retryUpload('img-1');

    expect(createUpload).toHaveBeenCalledWith(payload);
    const [newUpload, sentFile] = uploadArchive.mock.calls[1];
    expect(newUpload.uploadUrl).toBe('https://r2.example/put-2');
    expect(sentFile).toBe(original);
    expect(items()[0].status).toBe('done');
  });

  it('retry that gets 409 (file already reached R2) stops offering retry', async () => {
    uploadArchive.mockRejectedValueOnce(new Error('network'));
    await startUpload(upload(), file(), payload);
    createUpload.mockRejectedValueOnce(httpError(409));
    await retryUpload('img-1');
    expect(items()[0]).toMatchObject({ status: 'failed', retryable: false });
    expect(uploadArchive).toHaveBeenCalledTimes(1);
  });

  it('uploading the same image again replaces the running upload instead of adding a second row', async () => {
    const first = pendingPut();
    const firstDone = startUpload(upload(), file(), payload);
    uploadArchive.mockResolvedValueOnce(undefined);
    await startUpload(upload(), file(), payload);
    first.reject(new Error('should be ignored'));
    await firstDone;

    expect(items()).toHaveLength(1);
    expect(items()[0].status).toBe('done');
    expect(useToastStore.getState().toasts.filter((t) => t.type === 'error')).toEqual([]);
  });

  it('a running upload cannot be dismissed (cancel first)', () => {
    pendingPut();
    void startUpload(upload(), file(), payload);
    dismissUpload('img-1');
    expect(items()).toHaveLength(1);
  });
});
