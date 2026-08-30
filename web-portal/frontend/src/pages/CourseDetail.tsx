import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { courseService } from '../services/course';
import { labService } from '../services/lab';
import type { LabSummary, ProgressStatus } from '../services/lab';
import CoursePageHeader from '../components/CoursePageHeader';
import styles from './CourseDetail.module.css';

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
    // ผ่าน labService เพื่อให้ apiClient แนบ token ให้ — fetch() ดิบไม่แนบ
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
          // docUrl ที่ backend ส่งมาเป็น object key (labs/{id}/doc.pdf) ไม่ใช่ URL
          // ที่เบราว์เซอร์เปิดได้ ต้องแปลงเป็นเส้น /labs/{id}/doc เสมอ
          href: labService.docUrl(lab.id),
        })),
    [labs]
  );

  if (isPending || labsPending) {
    return <div className={styles.pageMessage}>กำลังโหลดข้อมูลรายวิชา...</div>;
  }

  if (isError || !course) {
    return <div className={styles.pageMessage}>ไม่พบข้อมูลรายวิชา หรือโหลดข้อมูลไม่สำเร็จ</div>;
  }

  const labTasks = labs
    .map((lab: LabSummary) => ({
      id: lab.id,
      title: lab.title,
      progress: lab.progressStatus ?? null,
      orderNo: lab.orderNo ?? 0,
      dueAt: lab.dueAt ?? null,
    }))
    // lab ที่ยังไม่เคยเปิดทำ (progress = null) นับเป็น incomplete เหมือนกัน
    .filter((lab) => {
      if (tab === 'complete') return lab.progress === 'finished';
      if (tab === 'incomplete') return lab.progress !== 'finished';
      return true;
    });

  return (
    <div className={styles.pageShell}>
      <CoursePageHeader title={`${course.code} : ${course.name}`} />

      <main className={styles.content}>
        <div className={styles.cardRow}>
          <section className={styles.card}>
            <h2 className={styles.cardTitle}>Documents</h2>
            <ul className={styles.docList}>
              {documents.length > 0 ? (
                documents.map((doc: { id: string; title: string; href: string }) => (
                  <li key={doc.id}>
                    <a href={doc.href} target="_blank" rel="noreferrer">
                      {doc.title}
                    </a>
                    <span>{course.code}</span>
                  </li>
                ))
              ) : (
                <li className={styles.emptyRow}>ยังไม่มีเอกสารสำหรับรายวิชานี้</li>
              )}
            </ul>
          </section>

          <section className={styles.card}>
            <h2 className={styles.cardTitle}>Announcement</h2>
            <div className={styles.announcementBox}>
              {course.announcements.length > 0 ? (
                <>
                  {course.announcements.map((item) => (
                    <div key={item.id} className={styles.announcementItem}>
                      <p className={styles.announcementAuthor}>
                        {/* ประกาศเก่าที่ยังไม่มี author ให้ตกมาที่ชื่ออาจารย์ประจำวิชา */}
                        {item.authorName ?? course.lecturerName}
                        {item.createdAt
                          ? ` · ${new Date(item.createdAt).toLocaleDateString('en-GB')}`
                          : ''}
                      </p>
                      <p className={styles.announcementText}>{item.message}</p>
                    </div>
                  ))}
                </>
              ) : (
                <p className={styles.noAnnouncement}>ยังไม่มีประกาศสำหรับรายวิชานี้</p>
              )}
            </div>
          </section>
        </div>

        <section className={styles.tableCard}>
          <div className={styles.tableHeader}>
            <h2 className={styles.cardTitle}>My Lab work</h2>
          </div>

          <div className={styles.tableContentWrapper}>
            <div className={styles.tabSidebar}>
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`${styles.tabButton} ${tab === item.id ? styles.activeTab : ''}`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            <div className={styles.tableWrapper}>
              <table>
                <thead>
                  <tr>
                    <th className={styles.firstColumn}>Lab</th>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Expired date</th>
                    <th className={styles.actionColumn}>Instruction</th>
                  </tr>
                </thead>
                <tbody>
                  {labTasks.length > 0 ? (
                    labTasks.map((lab) => {
                      const statusMeta = getProgressMeta(lab.progress);

                      return (
                        <tr key={lab.id}>
                          <td className={styles.firstColumn}>{lab.orderNo ? `Lab ${lab.orderNo}` : 'Lab'}</td>
                          <td>{lab.title}</td>
                          <td>
                            <span className={`${styles.statusTag} ${styles[statusMeta.tone]}`}>
                              {statusMeta.label}
                            </span>
                          </td>
                          <td>{lab.dueAt ? new Date(lab.dueAt).toLocaleDateString('en-GB') : '-'}</td>
                          <td className={styles.actionColumn}>
                            <Link to={`/labs/${lab.id}`} className={styles.instructionButton}>
                              Instruction
                            </Link>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={5} className={styles.emptyTable}>
                        {labs.length > 0
                          ? 'ไม่มี lab ในหมวดนี้'
                          : 'ยังไม่มี Lab สำหรับรายวิชานี้'}
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
