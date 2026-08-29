import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { courseService } from '../services/course';
import { labService } from '../services/lab';
import CoursePageHeader from '../components/CoursePageHeader';
import styles from './CourseDetail.module.css';

type LabRecord = {
  id: string;
  title: string;
  description?: string | null;
  status?: string | null;
  order_no?: number | null;
  orderNo?: number | null;
  due_at?: string | null;
  dueAt?: string | null;
  doc_url?: string | null;
  docUrl?: string | null;
};

function getLabStatusMeta(status?: string | null) {
  const value = (status ?? '').toLowerCase();

  if (['running', 'active', 'started', 'ready', 'published', 'completed', 'finished'].includes(value)) {
    return { label: 'Running', tone: 'green', action: 'View' };
  }

  if (['starting', 'starting_up', 'initializing', 'activating'].includes(value)) {
    return { label: 'Starting', tone: 'yellow', action: 'View' };
  }

  return { label: 'Not running', tone: 'red', action: 'View' };
}

export default function CourseDetailPage() {
  const { courseId = '' } = useParams<{ courseId: string }>();

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
    queryFn: async () => {
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000/api'}/labs?courseId=${courseId}`);
      const json = await response.json();
      return Array.isArray(json?.data) ? (json.data as LabRecord[]) : [];
    },
    enabled: Boolean(courseId),
  });

  const documents = useMemo(() => {
    if (!labs) return [];
    return labs.filter((lab: LabRecord) => lab.doc_url || lab.docUrl).map((lab: LabRecord) => ({
      id: lab.id,
      title: lab.title,
      name: lab.title,
      docUrl: lab.doc_url || lab.docUrl || labService.docUrl(lab.id),
    }));
  }, [labs]);

  if (isPending || labsPending) {
    return <div className={styles.pageMessage}>กำลังโหลดข้อมูลรายวิชา...</div>;
  }

  if (isError || !course) {
    return <div className={styles.pageMessage}>ไม่พบข้อมูลรายวิชา หรือโหลดข้อมูลไม่สำเร็จ</div>;
  }

  const labTasks = (labs ?? []).map((lab: LabRecord) => ({
    id: lab.id,
    title: lab.title,
    status: lab.status ?? 'draft',
    orderNo: lab.order_no ?? lab.orderNo ?? 0,
    dueAt: lab.due_at ?? lab.dueAt ?? null,
    instruction: lab.description ?? 'No description',
  }));

  return (
    <div className={styles.pageShell}>
      <CoursePageHeader title={`${course.code} : ${course.name}`} />

      <main className={styles.content}>
        <div className={styles.cardRow}>
          <section className={styles.card}>
            <h2 className={styles.cardTitle}>Documents</h2>
            <ul className={styles.docList}>
              {documents.length > 0 ? (
                documents.map((doc: { id: string; title: string; docUrl: string }) => (
                  <li key={doc.id}>
                    <a href={doc.docUrl} target="_blank" rel="noreferrer">
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
                    <p key={item.id} className={styles.announcementText}>
                      {item.message}
                    </p>
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
              <button type="button" className={`${styles.tabButton} ${styles.activeTab}`}>
                All labs
              </button>
              <button type="button" className={styles.tabButton}>
                Incomplete
              </button>
              <button type="button" className={styles.tabButton}>
                Complete
              </button>
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
                    labTasks.map((lab: { id: string; orderNo: number; title: string; status: string; dueAt: string | null; instruction: string }) => {
                      const statusMeta = getLabStatusMeta(lab.status);

                      return (
                        <tr key={lab.id}>
                          <td className={styles.firstColumn}>{lab.orderNo ? `Lab ${lab.orderNo}` : 'Lab'}</td>
                          <td>{lab.title}</td>
                          <td>
                            <span className={`${styles.statusTag} ${styles[statusMeta.tone]}`}>
                              {lab.status === 'published' ? 'incomplete' : lab.status}
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
                      <td colSpan={5} className={styles.emptyTable}>ยังไม่มี Lab สำหรับรายวิชานี้</td>
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
