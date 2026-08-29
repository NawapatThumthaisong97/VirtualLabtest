import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { BookOpen, Cloud, Database, Layers3, Route } from 'lucide-react';
import { coursesService } from '../services/courses';
import styles from './Courses.module.css';
import medicalLabLogo from '../assets/medical-lab.png';
import blueWallBackground from '../assets/a-blue-wall-back.jpg';

const COURSE_ICONS = [Layers3, Database, Cloud, Route, BookOpen];

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
          <img src={medicalLabLogo} alt="" className={styles.headerLogo} />
          <h1>Lab work</h1>
        </div>
      </div>

      <div className={styles.content}>
        {courses.length === 0 ? (
          <PageMessage>ยังไม่มีรายวิชาในบัญชีของคุณ</PageMessage>
        ) : (
          <section className={styles.grid} aria-label="Courses">
            {courses.map((course, index) => {
              const Icon = COURSE_ICONS[index % COURSE_ICONS.length];
              return (
                <Link to={`/courses/${course.id}`} key={course.id} className={styles.cardLink}>
                  <article className={styles.card}>
                    <div
                      className={styles.cover}
                      style={{
                        backgroundImage: `url(${course.imageUrl || blueWallBackground})`,
                        backgroundBlendMode: course.imageUrl ? 'multiply' : 'normal',
                        backgroundColor: '#dfeaf4',
                      }}
                    >
                      <div className={styles.iconTile} aria-hidden="true">
                        <Icon size={27} strokeWidth={1.8} />
                      </div>
                    </div>
                    <div className={styles.cardBody}>
                      <div className={styles.courseLabel}>COURSE</div>
                      <h2>{course.code} : {course.name}</h2>
                      <p>Lecturer : {course.lecturerName}</p>
                    </div>
                  </article>
                </Link>
              );
            })}
          </section>
        )}
      </div>
    </div>
  );
}
