/**
 * Instructor Course Page
 * Route: /instructor/courses/:courseId
 *
 * หน้าวิชาฝั่งอาจารย์ที่กดมาจาก Instructor Console — ตอนนี้เป็นโครงไว้ redesign
 * ระหว่างนี้งานจัดการจริง (labs / lab images / students) ยังอยู่ที่ /instructor เดิม
 */
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { courseService } from '../services/course';
import CoursePageHeader from '../components/CoursePageHeader';

export default function InstructorCoursePage() {
  const { courseId = '' } = useParams<{ courseId: string }>();

  const { data: course, isPending, isError } = useQuery({
    queryKey: ['course', courseId],
    queryFn: () => courseService.getById(courseId),
    enabled: Boolean(courseId),
  });

  if (isPending) {
    return <div className="grid min-h-[200px] place-items-center text-gray-600">กำลังโหลด...</div>;
  }
  if (isError || !course) {
    return (
      <div className="grid min-h-[200px] place-items-center text-gray-600">
        ไม่พบวิชานี้ หรือคุณไม่ได้เป็นอาจารย์ของวิชานี้
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full bg-gray-50">
      <CoursePageHeader title={`${course.code} : ${course.name}`} />

      <main className="mx-auto my-6 w-full max-w-[1250px] px-6 pb-14">
        <section className="rounded-lg border border-dashed border-gray-300 bg-white px-6 py-12 text-center text-gray-500">
          <p className="m-0 text-[15px]">หน้านี้กำลังออกแบบใหม่</p>
          <Link
            to="/instructor"
            className="mt-3 inline-block text-[14px] font-semibold text-blue-700 no-underline hover:underline"
          >
            จัดการวิชาแบบเดิม →
          </Link>
        </section>
      </main>
    </div>
  );
}
