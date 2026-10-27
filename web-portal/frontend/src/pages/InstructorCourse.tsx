/**
 * Instructor Course Page
 * Route: /instructor/courses/:courseId
 *
 * หน้าวิชาฝั่งอาจารย์ที่กดมาจาก Instructor Console — โครงเดียวกับหน้า course ของนักศึกษา
 * (Documents / Announcement / ตาราง lab) ต่างกันที่มีปุ่มเพิ่มของแต่ละการ์ด
 * และตาราง lab ไม่มี Start/Stop กดแถวแล้วค่อยกางคำอธิบาย
 * ปุ่มเพิ่มเปิด modal ของ Pete (components/lab-builder) lab ใหม่เป็น draft เสมอ
 * กด Publish ที่แถวของ lab หลัง image สแกนผ่าน (backend กันไว้อีกชั้น)
 */
import { Fragment, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { courseService } from '../services/course';
import { labService } from '../services/lab';
import type { LabStatus, LabSummary } from '../services/lab';
import { apiErrorMessage, isImageReady, labImageService } from '../services/labImage';
import DashboardHeader from '../components/admin/DashboardHeader';
import ScanStatusBadge from '../components/instructor/ScanStatusBadge';
import CreateLabModal from '../components/lab-builder/CreateLabModal';
import DocumentModal from '../components/lab-builder/DocumentModal';
import AnnouncementModal from '../components/lab-builder/AnnouncementModal';

type ModalKind = 'lab' | 'document' | 'announcement' | null;

type LabTab = 'all' | 'reviewing';

// Lab reviewing = lab ที่ยังเป็น draft นักศึกษายังมองไม่เห็น อาจารย์ต้องตรวจก่อน publish
const TABS: { id: LabTab; label: string }[] = [
  { id: 'all', label: 'All lab task' },
  { id: 'reviewing', label: 'Lab reviewing' },
];

const STATUS_CLASS: Record<LabStatus, string> = {
  published: 'bg-green-100 text-green-800',
  draft: 'bg-yellow-100 text-yellow-800',
  archived: 'bg-gray-100 text-gray-600',
};

const addButton =
  'cursor-pointer border-0 bg-transparent p-0 text-[0.92rem] font-medium text-blue-600 hover:underline';

function formatDue(dueAt: string | null) {
  return dueAt ? new Date(dueAt).toLocaleDateString('en-GB') : '-';
}

export default function InstructorCoursePage() {
  const { courseId = '' } = useParams<{ courseId: string }>();
  const [tab, setTab] = useState<LabTab>('all');
  const [openLabId, setOpenLabId] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalKind>(null);
  const queryClient = useQueryClient();

  const { data: course, isPending, isError } = useQuery({
    queryKey: ['course-detail', courseId],
    queryFn: () => courseService.getById(courseId),
    enabled: Boolean(courseId),
  });

  const { data: labs = [], isPending: labsPending } = useQuery({
    queryKey: ['course-labs', courseId],
    queryFn: () => labService.listByCourse(courseId),
    enabled: Boolean(courseId),
  });

  // สถานะสแกนของ image ที่ผูกกับ lab — รีเฟรชทุก 10 วิ ระหว่างที่ยังมีตัวที่สแกนไม่จบ
  const { data: images = [] } = useQuery({
    queryKey: ['lab-images', courseId],
    queryFn: () => labImageService.listByCourse(courseId),
    enabled: Boolean(courseId),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((image) => image.status === 'pending') ? 10_000 : false,
  });
  const imageById = useMemo(() => new Map(images.map((image) => [image.id, image])), [images]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['course-detail', courseId] });
    queryClient.invalidateQueries({ queryKey: ['course-labs', courseId] });
    queryClient.invalidateQueries({ queryKey: ['lab-images', courseId] });
  };

  const publish = useMutation({
    mutationFn: (labId: string) => labService.update(labId, { status: 'published' }),
    onSuccess: refresh,
  });

  const documents = useMemo(
    () => labs.filter((lab) => Boolean(lab.docUrl)).sort((a, b) => a.orderNo - b.orderNo),
    [labs]
  );

  if (isPending || labsPending) {
    return <div className="grid min-h-[200px] place-items-center text-gray-600">กำลังโหลดข้อมูลรายวิชา...</div>;
  }
  if (isError || !course) {
    return (
      <div className="grid min-h-[200px] place-items-center text-gray-600">
        ไม่พบวิชานี้ หรือคุณไม่ได้เป็นอาจารย์ของวิชานี้
      </div>
    );
  }

  const sortedLabs = [...labs].sort((a, b) => a.orderNo - b.orderNo);
  const labRows = sortedLabs.filter((lab) => tab === 'all' || lab.status === 'draft');

  return (
    <div className="min-h-screen w-full bg-gray-50">
      {/* แถบฟ้าแบบหน้า course ของนักศึกษา — กว้างเท่าเนื้อหาใน <main> + padding 20px เท่าหัวการ์ด
          Member / appearance ยังไม่มีหน้า เป็นปุ่มจางไว้ก่อน */}
      <DashboardHeader
        title={`${course.code} : ${course.name}`}
        features={[
          { label: 'Member', note: 'เร็ว ๆ นี้' },
          { label: 'appearance', note: 'เร็ว ๆ นี้' },
        ]}
        inner={{ width: 'calc(min(1250px, 100%) - 48px)', margin: '0 auto', padding: '0 20px' }}
      />

      <main className="mx-auto my-6 w-full max-w-[1250px] px-6 pb-14">
        <div className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-[1.2fr_1fr]">
          {/* Documents — เอกสารผูกกับ lab (doc_url) */}
          <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="flex items-center justify-between gap-4 border-b border-gray-200 px-5 py-5">
              <h2 className="m-0 text-lg font-bold text-gray-800">Documents</h2>
              <button type="button" onClick={() => setModal('document')} className={addButton}>Add new document +</button>
            </div>
            <ul className="m-0 max-h-[280px] list-none overflow-y-auto p-0 px-5">
              {documents.length > 0 ? (
                documents.map((lab) => (
                  <li
                    key={lab.id}
                    className="flex min-h-[46px] items-center justify-between gap-4 border-b border-gray-100 py-3 last:border-b-0"
                  >
                    <a
                      href={labService.docUrl(lab.id)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[0.96rem] font-medium text-blue-700 no-underline hover:text-blue-900"
                    >
                      {lab.title}
                    </a>
                    <span className="whitespace-nowrap text-[0.81rem] text-gray-500">Lab {lab.orderNo}</span>
                  </li>
                ))
              ) : (
                <li className="py-3 text-[0.93rem] text-gray-400">ยังไม่มีเอกสารสำหรับรายวิชานี้</li>
              )}
            </ul>
          </section>

          <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="flex items-center justify-between gap-4 border-b border-gray-200 px-5 py-5">
              <h2 className="m-0 text-lg font-bold text-gray-800">Announcement</h2>
              <button type="button" onClick={() => setModal('announcement')} className={addButton}>new post +</button>
            </div>
            <div className="max-h-[280px] overflow-y-auto px-5">
              {course.announcements.length > 0 ? (
                course.announcements.map((item) => (
                  <div key={item.id} className="flex flex-col gap-1 border-b border-gray-100 py-3.5 last:border-b-0">
                    <p className="m-0 text-[0.86rem] font-bold text-gray-900">
                      {item.authorName ?? course.lecturerName}
                      {item.createdAt ? ` · ${new Date(item.createdAt).toLocaleDateString('en-GB')}` : ''}
                    </p>
                    <p className="m-0 text-[0.94rem] leading-relaxed text-gray-800">{item.message}</p>
                  </div>
                ))
              ) : (
                <p className="m-0 py-3.5 text-[0.94rem] text-gray-400">ยังไม่มีประกาศสำหรับรายวิชานี้</p>
              )}
            </div>
          </section>
        </div>

        <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between gap-4 border-b border-gray-200 px-5 py-5">
            <h2 className="m-0 text-lg font-bold text-gray-800">Lab Image</h2>
            <button type="button" onClick={() => setModal('lab')} className={`inline-flex items-center gap-2 ${addButton}`}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className="text-gray-700">
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
                <path d="M17.5 14v7M14 17.5h7" />
              </svg>
              create new image
            </button>
          </div>

          <div className="flex">
            <div className="flex min-h-[300px] w-[240px] shrink-0 flex-col border-r border-gray-200 bg-white">
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`cursor-pointer appearance-none border-0 border-b border-l-[6px] border-b-gray-200 py-3 pl-[26px] pr-4 text-left text-[0.95rem] text-gray-900 transition-colors ${
                    tab === item.id ? 'border-l-[#039AD9] bg-[#F2F2F2]' : 'border-l-transparent bg-white hover:bg-gray-50'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    {['Name', 'Status', 'Expired date'].map((head) => (
                      <th key={head} className="border-b border-gray-200 px-5 py-3.5 text-left text-[0.92rem] font-medium text-gray-800">
                        {head}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {labRows.length > 0 ? (
                    labRows.map((lab: LabSummary) => {
                      const open = openLabId === lab.id;
                      return (
                        <Fragment key={lab.id}>
                          {/* กดทั้งแถวเพื่อกาง / หุบคำอธิบาย */}
                          <tr
                            onClick={() => setOpenLabId(open ? null : lab.id)}
                            aria-expanded={open}
                            className={`cursor-pointer transition-colors ${open ? 'bg-gray-50' : 'hover:bg-gray-50'}`}
                          >
                            <td className="border-b border-gray-100 px-5 py-3.5 text-[0.92rem] text-gray-900">{lab.title}</td>
                            <td className="border-b border-gray-100 px-5 py-3.5 text-[0.92rem]">
                              <span className={`inline-flex rounded-full px-3 py-1 text-[0.73rem] font-bold capitalize ${STATUS_CLASS[lab.status]}`}>
                                {lab.status}
                              </span>
                            </td>
                            <td className="border-b border-gray-100 px-5 py-3.5 text-[0.92rem] text-gray-800">{formatDue(lab.dueAt)}</td>
                          </tr>
                          {open && (
                            <tr>
                              <td colSpan={3} className="border-b border-gray-200 px-8 py-4">
                                <div className="flex items-end justify-between gap-6">
                                  <div className="flex flex-col gap-2">
                                    <p className="m-0 text-[0.8rem] leading-relaxed text-gray-500">
                                      Brief : {lab.description || 'ยังไม่มีคำอธิบายสำหรับ lab นี้'}
                                    </p>
                                    <LabImageLine image={lab.imageId ? imageById.get(lab.imageId) : undefined} hasImage={Boolean(lab.imageId)} />
                                    {publish.isError && publish.variables === lab.id && (
                                      <p className="m-0 text-[0.78rem] text-red-600">{apiErrorMessage(publish.error)}</p>
                                    )}
                                  </div>
                                  <div className="flex shrink-0 gap-2">
                                    {lab.status === 'draft' && (
                                      <button
                                        type="button"
                                        onClick={() => publish.mutate(lab.id)}
                                        disabled={!canPublish(lab, imageById) || (publish.isPending && publish.variables === lab.id)}
                                        title={canPublish(lab, imageById) ? undefined : 'image ต้องสแกนผ่านก่อน'}
                                        className="cursor-pointer border border-blue-600 bg-white px-5 py-1.5 text-[0.8rem] text-blue-600 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
                                      >
                                        Publish
                                      </button>
                                    )}
                                    <Link
                                      to={`/labs/${lab.id}`}
                                      className="bg-blue-600 px-6 py-1.5 text-[0.8rem] text-white no-underline hover:bg-blue-700"
                                    >
                                      Instruction
                                    </Link>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={3} className="px-5 py-7 text-center text-[0.94rem] text-gray-400">
                        {tab === 'reviewing' ? 'ไม่มี lab ที่รอตรวจ (draft)' : 'ยังไม่มี lab ในรายวิชานี้'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </main>

      <CreateLabModal open={modal === 'lab'} onClose={() => setModal(null)} onCreated={refresh} courseId={course.id} courseCode={course.code} />
      <DocumentModal open={modal === 'document'} onClose={() => setModal(null)} onUploaded={refresh} labs={sortedLabs} />
      <AnnouncementModal open={modal === 'announcement'} onClose={() => setModal(null)} onPosted={refresh} courseId={course.id} />
    </div>
  );
}

type ImageMap = Map<string, Parameters<typeof isImageReady>[0]>;

/** publish ได้: lab อ่านอย่างเดียว (ไม่มี image) หรือ image สแกนผ่านแล้ว */
function canPublish(lab: LabSummary, imageById: ImageMap) {
  if (!lab.imageId) return true;
  const image = imageById.get(lab.imageId);
  return Boolean(image && isImageReady(image));
}

function LabImageLine({ image, hasImage }: { image?: Parameters<typeof isImageReady>[0]; hasImage: boolean }) {
  if (!hasImage) return <p className="m-0 text-[0.78rem] text-gray-400">ไม่มี image (lab อ่านอย่างเดียว)</p>;
  if (!image) return <p className="m-0 text-[0.78rem] text-gray-400">กำลังโหลดสถานะ image...</p>;
  return (
    <div className="flex items-center gap-2 text-[0.78rem] text-gray-600">
      <span className="font-mono">{image.repository}:{image.tag}</span>
      <ScanStatusBadge image={image} />
    </div>
  );
}
