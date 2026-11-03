import { describe, expect, it, vi } from 'vitest';

// LabDocViewer import react-pdf (worker / canvas) ซึ่ง jsdom ไม่มี — เทสแค่ตัวทำสำเนา
vi.mock('react-pdf', () => ({ Document: () => null, Page: () => null, pdfjs: { GlobalWorkerOptions: {} } }));
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '' }));

import { copyPdfBytes } from '../components/LabDocViewer';

describe('copyPdfBytes', () => {
  it('pdf.js transfer สำเนาไปแล้ว buffer ใน cache ยังใช้ซ้ำได้', () => {
    const cached = new Uint8Array([37, 80, 68, 70]).buffer; // "%PDF"

    // จำลอง pdf.js: transfer bytes ที่ได้รับไปที่ worker → ตัวที่ส่งไปกลายเป็น detached
    const first = copyPdfBytes(cached);
    structuredClone(first.buffer, { transfer: [first.buffer] });
    expect(first.buffer.byteLength).toBe(0);

    // mount ครั้งที่สอง (กด Instruction ซ้ำ / ปิด lab แล้วกลับมา) ต้องไม่ throw
    const second = copyPdfBytes(cached);
    expect(Array.from(second)).toEqual([37, 80, 68, 70]);
    expect(cached.byteLength).toBe(4);
  });
});
