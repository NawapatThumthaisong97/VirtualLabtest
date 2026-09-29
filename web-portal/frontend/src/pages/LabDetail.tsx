/**
 * Lab Detail Page
 * Route: /labs/:labId
 *
 * Title + description + the lab document rendered inline with pdf.js, so the
 * pages flow with the page instead of sitting inside the browser's PDF viewer.
 * Pressing "Start Lab work" hands the whole page over to the provisioning loader.
 * Navbar/Footer come from RootLayout, so this file renders page content only.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Document, Page, pdfjs } from 'react-pdf';
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import LabLoader from '../components/LabLoader.tsx';
import { labService } from '../services/lab';
import { authService } from '../services/auth';
import { sessionService } from '../services/session';
import type { LabSession } from '../services/session';

/** ชื่อที่คนอ่านรู้เรื่องของแต่ละพอร์ตที่ image ของ lab เปิดไว้ */
const PORT_LABELS: Record<string, string> = {
  '8443': 'Code Editor',
  '5173': 'หน้าเว็บของ lab',
  '8080': 'Server API',
};

/** ดึงข้อความ error ที่ backend ส่งมา ไม่ใช่ข้อความดิบของ axios */
function readError(err: unknown): string {
  const data = (err as { response?: { data?: { message?: string; detail?: string } } })
    ?.response?.data;
  return data?.message ?? data?.detail ?? 'เปิด lab ไม่สำเร็จ ลองใหม่อีกครั้ง';
}

// pdf.js parses the file off the main thread; Vite resolves the bundled worker via ?url.
pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;

function DocMessage({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-80 items-center justify-center rounded-xl bg-[#F5F4EF] p-4 text-center text-[13px] text-[#9B9A93]">
      {children}
    </div>
  );
}

function PageMessage({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-[1200px] p-6">
      <div className="rounded-xl border border-[#E5E3DC] bg-white p-8 text-[15px] text-[#6B6A66]">
        {children}
      </div>
    </div>
  );
}

export default function LabDetailPage() {
  const { labId = '' } = useParams<{ labId: string }>();

  const {
    data: lab,
    isPending,
    isError,
  } = useQuery({
    queryKey: ['lab', labId],
    queryFn: () => labService.getById(labId),
    enabled: Boolean(labId),
  });

  const [isLaunching, setIsLaunching] = useState(false);
  const [session, setSession] = useState<LabSession | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [isClosing, setIsClosing] = useState(false);

  // โหลดไฟล์เอกสารผ่าน apiClient เพื่อให้ token ติดไปด้วย ถ้าปล่อยให้ react-pdf
  // ไปโหลด URL เองจะโดน 401 เพราะมันไม่ผ่าน interceptor ของ axios
  const { data: docBuffer, isError: isDocError } = useQuery({
    queryKey: ['lab-doc', labId],
    queryFn: () => labService.fetchDoc(labId),
    enabled: Boolean(lab?.docUrl),
  });

  // react-pdf จะโหลดไฟล์ใหม่ทุกครั้งที่ prop `file` เปลี่ยน reference
  // ถ้าสร้าง object ใหม่ทุก render มันจะวนโหลดไม่จบ
  const docFile = useMemo(
    () => (docBuffer ? { data: new Uint8Array(docBuffer) } : null),
    [docBuffer]
  );

  const docRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(0);
  const [pageCount, setPageCount] = useState(0);

  // pdf.js rasterises each page at a fixed pixel width, so the width has to be
  // measured from the column and re-measured whenever the window resizes.
  // The column only exists once the lab has loaded and while not launching,
  // so both are dependencies — otherwise the observer watches a dead element
  // and pageWidth stays 0, which renders nothing at all.
  useEffect(() => {
    const el = docRef.current;
    if (!el) return;

    const observer = new ResizeObserver(([entry]) => {
      setPageWidth(entry.contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [isLaunching, lab]);

  // สร้าง session = SkyPilot ไป schedule pod แล้ว pull image ใช้เวลาราว 1-2 นาที
  // backend รอจน pod พร้อมก่อนถึงจะตอบกลับ ไม่ได้ตอบทันทีแล้วให้ poll เอา
  // ฉะนั้นตรงนี้แค่ await ยาว ๆ โดยมี loader คั่นไว้ก็พอ
  const handleStartLab = async () => {
    setIsLaunching(true);
    setLaunchError(null);
    try {
      const me = await authService.me();
      setSession(await sessionService.create(labId, me.id));
    } catch (err) {
      setLaunchError(readError(err));
    } finally {
      setIsLaunching(false);
    }
  };

  const handleCloseLab = async () => {
    if (!session) return;
    setIsClosing(true);
    try {
      await sessionService.remove(session.session_id);
      setSession(null);
    } catch (err) {
      setLaunchError(readError(err));
    } finally {
      setIsClosing(false);
    }
  };

  if (isPending) return <PageMessage>กำลังโหลด...</PageMessage>;
  if (isError || !lab) return <PageMessage>ไม่พบ lab นี้ หรือโหลดข้อมูลไม่สำเร็จ</PageMessage>;

  const labHeading = `Lab ${lab.orderNo} : ${lab.title}`;

  // The column fills the viewport below the h-14 navbar so the loader can
  // centre itself in whatever space is left under the sub-header.
  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col bg-white font-sans text-[#2C2C2A]">
      {/* Sub-header: course title + tabs + primary action */}
      <div className="flex flex-shrink-0 flex-wrap items-center justify-between gap-4 border-b border-[#E5E3DC] bg-white px-6 py-4">
        <h2 className="text-xl font-bold">
          {lab.course.code} : {lab.course.name}
        </h2>

        <div className="flex items-center gap-7">
          <nav className="flex items-center gap-[22px] text-[15px]">
            <span className="border-b-2 border-[#185FA5] pb-1.5 font-semibold text-[#2C2C2A]">
              Instruction
            </span>
            <span className="border-b-2 border-transparent pb-1.5 text-[#6B6A66]">
              Dashboard
            </span>
          </nav>

          {/* ช่องเดียว สามสถานะ — ยังไม่เปิด / กำลังเตรียม / เปิดอยู่
              ตอนกำลังเตรียมใช้ disabled ไม่ใช่ปุ่ม "ยกเลิก" เพราะกดยกเลิกได้แค่
              ฝั่งหน้าจอ ส่วน pod ที่ SkyPilot สั่งสร้างไปแล้วยังเดินหน้าต่ออยู่ดี
              ปุ่มที่ทำให้เข้าใจผิดแบบนั้นแย่กว่าปุ่มที่กดไม่ได้ */}
          {session ? (
            <button
              type="button"
              onClick={handleCloseLab}
              disabled={isClosing}
              className="cursor-pointer rounded-lg border border-[#E5E3DC] bg-white px-5 py-2.5 text-sm font-medium text-[#2C2C2A] transition hover:border-[#C9C7C0] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isClosing ? 'กำลังปิด...' : 'ปิด lab'}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleStartLab}
              disabled={isLaunching}
              className="cursor-pointer rounded-lg bg-[#185FA5] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0C447C] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLaunching ? 'กำลังเตรียม...' : 'Start Lab work'}
            </button>
          )}
        </div>
      </div>

      {isLaunching ? (
        // heavier bottom padding lifts the block above true centre, where a
        // lone element reads as "centred" to the eye
        <div className="flex flex-1 items-center justify-center px-6 pt-10 pb-28">
          <LabLoader size={48} label="Preparing your lab environment" />
        </div>
      ) : session ? (
        <div className="mx-auto w-full max-w-[1200px] px-8 pt-8 pb-10">
          <h1 className="mb-2 text-[22px] font-semibold">{labHeading}</h1>
          <p className="mb-6 text-[15px] text-[#6B6A66]">
            สภาพแวดล้อมพร้อมใช้งานแล้ว — เปิดลิงก์ด้านล่างในแท็บใหม่
          </p>

          <div className="flex flex-col gap-3">
            {Object.entries(session.endpoints).map(([port, url]) => (
              <a
                key={port}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-xl border border-[#E5E3DC] px-5 py-4 transition hover:border-[#185FA5]"
              >
                <span className="text-[15px] font-medium">
                  {PORT_LABELS[port] ?? `พอร์ต ${port}`}
                </span>
                <span className="text-[13px] text-[#6B6A66]">{url}</span>
              </a>
            ))}
          </div>

          <p className="mt-6 text-[13px] text-[#9B9A93]">
            cluster: {session.cluster_name} · image: {session.image_repository}:
            {session.image_tag}
          </p>
        </div>
      ) : (
        // คุมความกว้างคอลัมน์เท่าเดิมเพื่อให้ขนาดตัวหนังสือใน PDF อ่านสบาย
        // (pdf.js วาดหน้าเท่าความกว้างคอลัมน์ ปล่อยเต็มจอแล้วตัวโตเกินไป)
        // ต่างจากเดิมตรงที่พื้นหน้าเป็นสีขาว ไม่มีกล่องขาวลอยบนพื้นเทาแล้ว
        <div className="mx-auto w-full max-w-[1200px] px-8 pt-6 pb-10">
          <article>
            <h1 className="mb-4 text-[22px] font-semibold">{labHeading}</h1>

            {lab.description && (
              <p className="mb-6 text-[15px] leading-[1.7] text-[#6B6A66]">
                {lab.description}
              </p>
            )}

            {launchError && (
              <div className="mb-6 rounded-xl border border-[#E8C4C4] bg-[#FDF5F5] px-5 py-4 text-[14px] text-[#A33] ">
                {launchError}
              </div>
            )}

            {/* Lab document — pdf.js draws each page straight into the article */}
            <div ref={docRef}>
              {!lab.docUrl ? (
                <DocMessage>ยังไม่มีเอกสารสำหรับ lab นี้</DocMessage>
              ) : isDocError ? (
                <DocMessage>เปิดเอกสารไม่สำเร็จ ลองรีเฟรชหน้าอีกครั้ง</DocMessage>
              ) : !docFile ? (
                <DocMessage>กำลังโหลดเอกสาร...</DocMessage>
              ) : (
                <Document
                  file={docFile}
                  onLoadSuccess={({ numPages }) => setPageCount(numPages)}
                  externalLinkTarget="_blank"
                  loading={<DocMessage>กำลังโหลดเอกสาร...</DocMessage>}
                  error={<DocMessage>เปิดเอกสารไม่สำเร็จ ลองรีเฟรชหน้าอีกครั้ง</DocMessage>}
                  noData={<DocMessage>ยังไม่มีเอกสารสำหรับ lab นี้</DocMessage>}
                  className="flex flex-col"
                >
                  {pageWidth > 0 &&
                    Array.from({ length: pageCount }, (_, i) => (
                      <div
                        key={i}
                        className={i > 0 ? 'mt-7 border-t border-[#F0EEE7] pt-7' : ''}
                      >
                        <Page pageNumber={i + 1} width={pageWidth} loading="" />
                      </div>
                    ))}
                </Document>
              )}
            </div>
          </article>
        </div>
      )}
    </div>
  );
}
