import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { coursesService } from '../services/courses';
import type { Courses } from '../services/courses';
import styles from './Courses.module.css';
import labLogo from '../assets/lab.png';
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

export default function CoursesPage() {
  const { data: courses = [], isPending, isError } = useQuery({
    queryKey: ['courses'],
    queryFn: coursesService.getAll,
  });

  if (isPending) return <PageMessage>กำลังโหลดรายวิชา...</PageMessage>;
  if (isError) return <PageMessage>โหลดรายวิชาไม่สำเร็จ ลองใหม่อีกครั้ง</PageMessage>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.headerInner}>
          <img src={labLogo} alt="" className={styles.headerLogo} />
          <h1>Lab work</h1>
        </div>
      </div>

      <div className={styles.content}>
        {courses.length === 0 ? (
          <PageMessage>ยังไม่มีรายวิชาในบัญชีของคุณ</PageMessage>
        ) : (
          <section className={styles.grid} aria-label="Courses">
            {courses.map((course) => (
              <Link to={`/courses/${course.id}`} key={course.id} className={styles.cardLink}>
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
