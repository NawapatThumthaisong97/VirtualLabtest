import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { courseService } from '../services/course';
import { labService } from '../services/lab';
import type { LabSummary, ProgressStatus } from '../services/lab';
import CoursePageHeader from '../components/CoursePageHeader';

type LabTab = 'all' | 'incomplete' | 'complete';

const TABS: { id: LabTab; label: string }[] = [
  { id: 'all', label: 'All labs' },
  { id: 'incomplete', label: 'Incomplete' },
  { id: 'complete', label: 'Complete' },
];

/** สถานะที่นักศึกษาสนใจคือ "ตัวเองทำถึงไหน" ไม่ใช่ published/draft ของตัว lab */
function getProgressMeta(progress: ProgressStatus | null) {
  if (progress === 'finished') return { label: 'complete', tone: 'green' };
  if (progress === 'in_progress') return { label: 'in progress', tone: 'yellow' };
  return { label: 'not started', tone: 'grey' };
}

export default function CourseDetailPage() {
  const { courseId = '' } = useParams<{ courseId: string }>();
  const [tab, setTab] = useState<LabTab>('all');

  const {
    data: course,
    isPending,
    isError,
  } = useQuery({
    queryKey: ['course-detail', courseId],
    queryFn: () => courseService.getById(courseId),
    enabled: Boolean(courseId),
  });

  const {
    data: labs = [],
    isPending: labsPending,
  } = useQuery({
    queryKey: ['course-labs', courseId],
    queryFn: () => labService.listByCourse(courseId),
    enabled: Boolean(courseId),
  });

  const documents = useMemo(
    () =>
      labs
        .filter((lab: LabSummary) => Boolean(lab.docUrl))
        .map((lab: LabSummary) => ({
          id: lab.id,
          title: lab.title,
          href: labService.docUrl(lab.id),
        })),
    [labs]
  );

  if (isPending || labsPending) {
    return (
      <div className="grid place-items-center min-h-[200px] text-gray-600">
        กำลังโหลดข้อมูลรายวิชา...
      </div>
    );
  }

  if (isError || !course) {
    return (
      <div className="grid place-items-center min-h-[200px] text-gray-600">
        ไม่พบข้อมูลรายวิชา หรือโหลดข้อมูลไม่สำเร็จ
      </div>
    );
  }

  const labTasks = labs
    .map((lab: LabSummary) => ({
      id: lab.id,
      title: lab.title,
      progress: lab.progressStatus ?? null,
      orderNo: lab.orderNo ?? 0,
      dueAt: lab.dueAt ?? null,
    }))
    .filter((lab) => {
      if (tab === 'complete') return lab.progress === 'finished';
      if (tab === 'incomplete') return lab.progress !== 'finished';
      return true;
    });

  return (
    <div className="w-full min-h-screen bg-gray-50">
      <CoursePageHeader title={`${course.code} : ${course.name}`} />

      <main className="w-full max-w-[1250px] mx-auto px-6 my-6 pb-14">
        {/* Documents & Announcements Row */}
        <div className="grid grid-cols-1 md:grid-cols-[1.2fr_1fr] gap-6 mb-6">
          {/* Documents Card */}
          <section className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow">
            <h2 className="m-0 px-5 py-5 text-lg font-bold text-gray-800 border-b border-gray-200">
              Documents
            </h2>
            <ul className="list-none p-0 m-0 px-5 max-h-[280px] overflow-y-auto scrollbar-thin scrollbar-thumb-gray-400 scrollbar-track-gray-100">
              {documents.length > 0 ? (
                documents.map((doc: { id: string; title: string; href: string }) => (
                  <li
                    key={doc.id}
                    className="flex justify-between items-center gap-4 min-h-[46px] py-3 border-b border-gray-100 last:border-b-0"
                  >
                    <a
                      href={doc.href}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-700 hover:text-blue-900 font-medium text-[0.96rem] transition-colors no-underline"
                    >
                      {doc.title}
                    </a>
                    <span className="text-gray-500 text-[0.81rem] whitespace-nowrap font-normal">
                      {course.code}
                    </span>
                  </li>
                ))
              ) : (
                <li className="text-gray-400 py-3 text-[0.93rem]">
                  ยังไม่มีเอกสารสำหรับรายวิชานี้
                </li>
              )}
            </ul>
          </section>

          {/* Announcements Card */}
          <section className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow">
            <h2 className="m-0 px-5 py-5 text-lg font-bold text-gray-800 border-b border-gray-200">
              Announcement
            </h2>
            <div className="px-5 max-h-[280px] overflow-y-auto scrollbar-thin scrollbar-thumb-gray-400 scrollbar-track-gray-100">
              {course.announcements.length > 0 ? (
                <>
                  {course.announcements.map((item) => (
                    <div
                      key={item.id}
                      className="flex flex-col gap-1 py-3.5 border-b border-gray-100 last:border-b-0"
                    >
                      <p className="m-0 text-gray-900 text-[0.86rem] font-bold">
                        {item.authorName ?? course.lecturerName}
                        {item.createdAt
                          ? ` · ${new Date(item.createdAt).toLocaleDateString('en-GB')}`
                          : ''}
                      </p>
                      <p className="m-0 text-gray-800 text-[0.94rem] leading-relaxed font-normal">
                        {item.message}
                      </p>
                    </div>
                  ))}
                </>
              ) : (
                <p className="m-0 py-3.5 text-gray-400 text-[0.94rem] font-normal">
                  ยังไม่มีประกาศสำหรับรายวิชานี้
                </p>
              )}
            </div>
          </section>
        </div>

        {/* Lab Table */}
        <section className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow">
          <div className="px-5 py-5 border-b border-gray-200">
            <h2 className="m-0 text-lg font-bold text-gray-800">My Lab work</h2>
          </div>

          <div className="flex">
            {/* Tab Sidebar */}
            <div className="flex flex-col w-[200px] py-4 border-r border-gray-200 bg-white min-h-[300px] overflow-y-auto">
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`appearance-none border-none bg-transparent text-left px-4 py-3 text-[0.87rem] font-medium cursor-pointer transition-all border-l-3 ${
                    tab === item.id
                      ? 'bg-blue-50 text-blue-700 font-semibold border-l-blue-600'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-blue-700 border-l-transparent'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {/* Table Wrapper */}
            <div className="flex-1 overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="px-3.5 py-3.5 border-b border-gray-200 text-left text-[0.92rem] font-bold text-gray-700 w-[18%]">
                      Lab
                    </th>
                    <th className="px-3.5 py-3.5 border-b border-gray-200 text-left text-[0.92rem] font-bold text-gray-700">
                      Name
                    </th>
                    <th className="px-3.5 py-3.5 border-b border-gray-200 text-left text-[0.92rem] font-bold text-gray-700">
                      Status
                    </th>
                    <th className="px-3.5 py-3.5 border-b border-gray-200 text-left text-[0.92rem] font-bold text-gray-700">
                      Expired date
                    </th>
                    <th className="px-3.5 py-3.5 border-b border-gray-200 text-right text-[0.92rem] font-bold text-gray-700 w-[130px]">
                      Instruction
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {labTasks.length > 0 ? (
                    labTasks.map((lab) => {
                      const statusMeta = getProgressMeta(lab.progress);
                      const statusClasses = {
                        green: 'bg-green-50 text-green-700',
                        yellow: 'bg-orange-50 text-orange-700',
                        grey: 'bg-gray-100 text-gray-600',
                      }[statusMeta.tone];

                      return (
                        <tr key={lab.id} className="hover:bg-gray-50 transition-colors">
                          <td className="px-3.5 py-3.5 border-b border-gray-100 text-gray-600 font-medium text-[0.92rem]">
                            {lab.orderNo ? `Lab ${lab.orderNo}` : 'Lab'}
                          </td>
                          <td className="px-3.5 py-3.5 border-b border-gray-100 text-gray-800 text-[0.92rem]">
                            {lab.title}
                          </td>
                          <td className="px-3.5 py-3.5 border-b border-gray-100 text-[0.92rem]">
                            <span
                              className={`inline-flex items-center justify-center min-w-[72px] px-3 py-1 rounded-full text-[0.73rem] font-bold capitalize tracking-wide ${statusClasses}`}
                            >
                              {statusMeta.label}
                            </span>
                          </td>
                          <td className="px-3.5 py-3.5 border-b border-gray-100 text-gray-800 text-[0.92rem]">
                            {lab.dueAt ? new Date(lab.dueAt).toLocaleDateString('en-GB') : '-'}
                          </td>
                          <td className="px-3.5 py-3.5 border-b border-gray-100 text-right">
                            <Link
                              to={`/labs/${lab.id}`}
                              className="inline-flex items-center justify-center min-w-[90px] h-8 border border-blue-700 bg-blue-700 text-white rounded text-[0.84rem] font-semibold no-underline transition-all hover:bg-blue-800 hover:border-blue-800 hover:shadow-md"
                            >
                              Instruction
                            </Link>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td
                        colSpan={5}
                        className="text-center text-gray-400 py-7 px-3.5 text-[0.94rem]"
                      >
                        {labs.length > 0 ? 'ไม่มี lab ในหมวดนี้' : 'ยังไม่มี Lab สำหรับรายวิชานี้'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
