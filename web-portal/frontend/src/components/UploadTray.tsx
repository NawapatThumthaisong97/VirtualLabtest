/**
 * ถาดแสดงการอัปโหลด lab image ที่ยังไม่จบ มุมขวาล่างของทุกหน้า ใต้ toast (อยู่ใน ToastContainer)
 * mount ครั้งเดียวใน App.tsx ข้างนอก router จึงอยู่ตลอดไม่ว่าจะเปลี่ยนหน้าไปไหน
 * สถานะจริงอยู่ใน services/labImageUploads.ts
 */
import { useEffect } from 'react';
import { CheckCircle2, Loader2, RotateCcw, UploadCloud, X, XCircle } from 'lucide-react';
import { cn } from '../lib/utils';
import {
  cancelUpload,
  dismissUpload,
  isUploading,
  retryUpload,
  useUploadStore,
  type UploadItem,
} from '../services/labImageUploads';

/** เตือนก่อนปิด / reload แท็บ ถ้ายังอัปไม่เสร็จ (ไฟล์อยู่ในหน่วยความจำของแท็บ ปิดแล้วหายทันที) */
export function useWarnBeforeUnload(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // browser รุ่นเก่าต้องตั้ง returnValue (ข้อความจริงที่แสดง browser กำหนดเอง)
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [active]);
}

export default function UploadTray() {
  const uploads = useUploadStore((state) => state.uploads);
  const active = uploads.filter(isUploading).length;
  useWarnBeforeUnload(active > 0);

  if (uploads.length === 0) return null;

  return (
    <section
      aria-label="Image uploads"
      className="pointer-events-auto w-full max-w-sm overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg"
    >
      <header className="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700">
        <UploadCloud size={14} aria-hidden />
        {active > 0 ? `Uploading ${active} image${active > 1 ? 's' : ''}` : 'Uploads'}
        {active > 0 && <span className="ml-auto font-normal text-slate-400">Keep this tab open</span>}
      </header>
      <ul className="max-h-64 divide-y divide-slate-100 overflow-y-auto">
        {uploads.map((upload) => (
          <UploadRow key={upload.id} upload={upload} />
        ))}
      </ul>
    </section>
  );
}

function UploadRow({ upload }: { upload: UploadItem }) {
  const uploading = isUploading(upload);
  return (
    <li className="px-3 py-2.5 text-xs" aria-live="polite">
      <div className="flex items-center gap-2">
        <StatusIcon status={upload.status} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono font-semibold text-slate-800" title={upload.label}>{upload.label}</p>
          <p className="truncate text-[11px] text-slate-400">
            {upload.status === 'uploading' && `${upload.percent}% · ${upload.fileName}`}
            {upload.status === 'done' && 'Uploaded · queued for security scan'}
            {upload.status === 'canceled' && 'Canceled'}
            {upload.status === 'failed' && <span className="text-red-600">{upload.error}</span>}
          </p>
        </div>
        {upload.status === 'failed' && upload.retryable && (
          <button
            type="button"
            onClick={() => retryUpload(upload.id)}
            className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            aria-label={`Retry upload of ${upload.label}`}
            title="Retry"
          >
            <RotateCcw size={14} aria-hidden />
          </button>
        )}
        <button
          type="button"
          onClick={() => (uploading ? cancelUpload(upload.id) : dismissUpload(upload.id))}
          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
          aria-label={uploading ? `Cancel upload of ${upload.label}` : `Dismiss ${upload.label}`}
          title={uploading ? 'Cancel' : 'Dismiss'}
        >
          <X size={14} aria-hidden />
        </button>
      </div>
      {uploading && (
        <div
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-valuenow={upload.percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Upload progress of ${upload.label}`}
        >
          <div className="h-full rounded-full bg-blue-600 transition-[width]" style={{ width: `${upload.percent}%` }} />
        </div>
      )}
    </li>
  );
}

function StatusIcon({ status }: { status: UploadItem['status'] }) {
  const common = 'shrink-0';
  if (status === 'uploading') return <Loader2 size={16} className={cn(common, 'animate-spin text-blue-600')} aria-hidden />;
  if (status === 'done') return <CheckCircle2 size={16} className={cn(common, 'text-emerald-600')} aria-hidden />;
  return <XCircle size={16} className={cn(common, status === 'failed' ? 'text-red-500' : 'text-slate-400')} aria-hidden />;
}
