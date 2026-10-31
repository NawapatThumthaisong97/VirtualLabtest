/**
 * เอกสาร lab (PDF) วาดด้วย pdf.js ลงในคอลัมน์ตรง ๆ ไม่ใช้ PDF viewer ของเบราว์เซอร์
 *
 * รับ ArrayBuffer ที่ react-query cache ไว้ — ห้ามส่ง buffer ตัวนั้นให้ pdf.js ตรง ๆ
 * เพราะ pdf.js transfer buffer ไปที่ worker แล้ว buffer ใน cache จะกลายเป็น detached
 * mount ครั้งถัดไป (กลับมาหน้าเดิม / ปิด lab แล้วกลับมาแท็บ Instruction) จะพังด้วย
 * "Cannot perform Construct on a detached ArrayBuffer" — เลยทำสำเนาทุกครั้งที่ mount
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

// pdf.js parses the file off the main thread; Vite resolves the bundled worker via ?url.
// ?mime=js: ไฟล์ worker เคยถูก nginx ส่งเป็น application/octet-stream พร้อม Cache-Control immutable 1 ปี
// เบราว์เซอร์ที่ cache ตัวเสียไว้จะไม่ขอใหม่เอง (Ctrl+Shift+R ไม่ช่วยเพราะ worker ถูกโหลดจากใน JS) — เปลี่ยน URL บังคับโหลดใหม่
pdfjs.GlobalWorkerOptions.workerSrc = `${workerSrc}?mime=js`;

/** สำเนา bytes ให้ pdf.js เอาไป transfer ได้ โดย buffer ต้นฉบับใน cache ยังใช้ซ้ำได้ */
export function copyPdfBytes(buffer: ArrayBuffer): Uint8Array {
  return new Uint8Array(buffer.slice(0));
}

export function DocMessage({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-80 items-center justify-center rounded-xl bg-[#F5F4EF] p-4 text-center text-[13px] text-[#9B9A93]">
      {children}
    </div>
  );
}

export default function LabDocViewer({ buffer }: { buffer: ArrayBuffer }) {
  // react-pdf จะโหลดไฟล์ใหม่ทุกครั้งที่ prop `file` เปลี่ยน reference
  // ถ้าสร้าง object ใหม่ทุก render มันจะวนโหลดไม่จบ — memo ต่อ mount
  const file = useMemo(() => ({ data: copyPdfBytes(buffer) }), [buffer]);

  const docRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(0);
  const [pageCount, setPageCount] = useState(0);

  // pdf.js rasterises each page at a fixed pixel width, so the width has to be
  // measured from the column and re-measured whenever the window resizes.
  useEffect(() => {
    const el = docRef.current;
    if (!el) return;

    const observer = new ResizeObserver(([entry]) => {
      setPageWidth(entry.contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={docRef}>
      <Document
        file={file}
        onLoadSuccess={({ numPages }) => setPageCount(numPages)}
        externalLinkTarget="_blank"
        loading={<DocMessage>กำลังโหลดเอกสาร...</DocMessage>}
        error={<DocMessage>เปิดเอกสารไม่สำเร็จ ลองรีเฟรชหน้าอีกครั้ง</DocMessage>}
        noData={<DocMessage>ยังไม่มีเอกสารสำหรับ lab นี้</DocMessage>}
        className="flex flex-col"
      >
        {pageWidth > 0 &&
          Array.from({ length: pageCount }, (_, i) => (
            <div key={i} className={i > 0 ? 'mt-7 border-t border-[#F0EEE7] pt-7' : ''}>
              <Page
                pageNumber={i + 1}
                width={pageWidth}
                loading=""
                renderAnnotationLayer={false}
                renderTextLayer={false}
              />
            </div>
          ))}
      </Document>
    </div>
  );
}
