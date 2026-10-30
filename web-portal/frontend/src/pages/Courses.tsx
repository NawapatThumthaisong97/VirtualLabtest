import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { coursesService } from '../services/courses';
import type { Courses } from '../services/courses';
import styles from './Courses.module.css';
import DashboardHeader from '../components/admin/DashboardHeader';
import CreateCourseModal from '../components/lab-builder/CreateCourseModal';
import { BACKGROUND_PRESETS, ICON_KEYS, ICON_PRESETS } from '../constants/coursePresets';

// ไฟล์ที่อัปเองมาก่อน ถ้าไม่มีค่อยใช้ preset ที่เลือกไว้ ถ้าไม่มีอีกก็ปล่อยเป็น gradient ใน CSS
function backgroundFor(course: Courses) {
  if (course.imageUrl) return course.imageUrl;
  if (course.backgroundKey) return BACKGROUND_PRESETS[course.backgroundKey];
  return null;
}

// คอร์สเก่าที่ยังไม่ได้เลือกไอคอน ใช้ id หาแทน จะได้ไม่เปลี่ยนตอนมีคอร์สใหม่แทรกเข้ามา
function iconFor(course: Courses) {
  if (course.iconKey) return ICON_PRESETS[course.iconKey];
  let sum = 0;
  for (const ch of course.id) sum += ch.charCodeAt(0);
  return ICON_PRESETS[ICON_KEYS[sum % ICON_KEYS.length]];
}

function PageMessage({ children }: { children: React.ReactNode }) {
  return <div className={styles.message}>{children}</div>;
}

type CoursesPageProps = {
  /** หัวแถบ — นักศึกษา "My Laboratory" / อาจารย์ "Instructor Console" */
  title?: string;
  /** การ์ดวิชาพาไปไหน — อาจารย์ไปหน้าจัดการวิชาแทนหน้าเรียน */
  linkTo?: (course: Courses) => string;
  /** อาจารย์ / admin: ปุ่ม Create course บนแถบฟ้า (นักศึกษาไม่มี) */
  canCreate?: boolean;
};

const createButton = {
  border: 0,
  background: 'none',
  padding: '4px 2px',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  color: '#fff',
  fontFamily: 'inherit',
  fontSize: 15,
  fontWeight: 300,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
} as const;

// หน้าเดียวใช้ทั้งนักศึกษาและอาจารย์ /courses กรองตาม role ให้แล้ว (อาจารย์ได้เฉพาะวิชาที่สอน)
export default function CoursesPage({
  title = 'My Laboratory',
  linkTo = (course) => `/courses/${course.id}`,
  canCreate = false,
}: CoursesPageProps) {
  const [creating, setCreating] = useState(false);
  const queryClient = useQueryClient();
  const { data: courses = [], isPending, isError } = useQuery({
    queryKey: ['courses'],
    queryFn: coursesService.getAll,
  });

  if (isPending) return <PageMessage>กำลังโหลดรายวิชา...</PageMessage>;
  if (isError) return <PageMessage>โหลดรายวิชาไม่สำเร็จ ลองใหม่อีกครั้ง</PageMessage>;

  return (
    <div className={styles.page}>
      {/* กว้างเท่า .grid ใน .content — ขอบซ้ายชื่อหน้าตรงกับขอบการ์ด */}
      <DashboardHeader
        title={title}
        features={[]}
        inner={{ width: 'min(1120px, calc(100% - 2 * clamp(1.25rem, 5vw, 4rem)))', margin: '0 auto', padding: 0 }}
      >
        {/* ตัวอักษรขาวไม่มีกรอบ ไอคอนดินสอแทน + (Pete ขอ) hover ขีดเส้นใต้แบบเมนูบนแถบ */}
        {canCreate && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            style={createButton}
            onMouseEnter={(e) => (e.currentTarget.style.textDecoration = 'underline')}
            onMouseLeave={(e) => (e.currentTarget.style.textDecoration = 'none')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="M4 20h4L19 9l-4-4L4 16v4z" />
              <path d="M13.5 6.5l4 4" />
            </svg>
            Create course
          </button>
        )}
      </DashboardHeader>

      {canCreate && (
        <CreateCourseModal
          open={creating}
          onClose={() => setCreating(false)}
          onCreated={() => queryClient.invalidateQueries({ queryKey: ['courses'] })}
        />
      )}

      <div className={styles.content}>
        {courses.length === 0 ? (
          <PageMessage>ยังไม่มีรายวิชาในบัญชีของคุณ</PageMessage>
        ) : (
          <section className={styles.grid} aria-label="Courses">
            {courses.map((course) => (
              <Link to={linkTo(course)} key={course.id} className={styles.cardLink}>
                <article className={styles.card}>
                  <div
                    className={styles.cover}
                    style={
                      backgroundFor(course)
                        ? { backgroundImage: `url(${backgroundFor(course)})` }
                        : undefined
                    }
                  >
                    <div className={styles.iconTile} aria-hidden="true">
                      <img src={iconFor(course)} alt="" className={styles.iconImg} />
                    </div>
                  </div>
                  <div className={styles.cardBody}>
                    <div className={styles.courseLabel}>COURSE</div>
                    <h2>{course.code} : {course.name}</h2>
                    <p>Lecturer : {course.lecturerName}</p>
                  </div>
                </article>
              </Link>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
