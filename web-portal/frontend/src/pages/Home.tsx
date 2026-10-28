/**
 * Home Page
 *
 * Hero on a full-bleed background with the tab strip and the service cards,
 * then two list cards whose top third overlaps the hero.
 * The navbar comes from RootLayout, so it is not repeated here.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { coursesService } from '../services/courses.ts';
import { courseService } from '../services/course.ts';
import TabNav from '../components/TabNav.tsx';
import type { Tab } from '../components/TabNav.tsx';
import ServiceCard from '../components/ServiceCard.tsx';
import type { Service } from '../components/ServiceCard.tsx';
import EntryBox from '../components/EntryBox.tsx';
import type { Entry } from '../components/EntryBox.tsx';
import styles from './Home.module.css';
import heroBg from '../assets/B1.jpg';

// Placeholder copy — swap for real data once the endpoints exist.
const LOREM =
  'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nunc quis nisi ac tortor';

const TABS: Tab[] = [
  { id: 'recent', label: 'Recent' },
  { id: 'service', label: 'Service' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'helpdesk', label: 'Help Desk' },
];

const LAB_WORK: Service = {
  id: 'labwork',
  title: 'Lab work',
  text: 'Launch a preconfigured lab in one click. No setup, no installs, just start working.',
  icon: 'labwork',
  iconWidth: 48,
};

const COMPUTE: Service = {
  id: 'compute',
  title: 'Compute service',
  text: 'Need more power? Burst your lab to the cloud and get GPUs on demand.',
  icon: 'compute',
  iconWidth: 60,
};

const INSTRUCTOR_CONSOLE: Service = {
  id: 'instructor',
  title: 'Instructor Console',
  text: 'Manage your courses, labs and lab images in one place.',
  icon: 'instructor',
  iconWidth: 48,
};

// อาจารย์ / admin ไม่มีงานแลปให้ทำเอง การ์ดแรกเลยเป็นหน้าจัดการวิชาแทน (เรียงตาม mockup)
const STUDENT_SERVICES: Service[] = [LAB_WORK, COMPUTE];
const INSTRUCTOR_SERVICES: Service[] = [COMPUTE, INSTRUCTOR_CONSOLE];

const ACTIVITY_LOG: Entry[] = [
  { name: 'Virtual Lab team', text: LOREM },
  { name: 'CS102 : Prof.Jose Matt', text: LOREM },
];

const NO_ANNOUNCEMENT: Entry[] = [
  { name: 'Virtual Lab team', text: 'ยังไม่มีประกาศจากวิชาที่คุณลงเรียน' },
];

// คำนำหน้าที่ถ้าเจอเป็นคำแรก ต้องเอาชื่อต้นมาต่อด้วย (ไม่งั้นทักว่า "Good Afternoon! , Dr.")
const TITLE_RE = /^(dr|prof|asst|assoc|mr|mrs|ms|miss|อ|อาจารย์|ดร|ผศ|รศ|ศ|นาย|นาง|นางสาว)\.?$/i;

/** ชื่อบนหัวหน้า home: ชื่อต้น — ถ้าขึ้นต้นด้วยคำนำหน้า (Dr. / Asst. Prof. / ผศ.ดร.) เก็บคำนำหน้าไว้คู่ชื่อต้น */
export function greetingName(fullName: string): string {
  const words = fullName.trim().split(/\s+/).filter(Boolean);
  const titles: string[] = [];
  while (words.length > 1 && words[0].split('.').filter(Boolean).every((part) => TITLE_RE.test(part))) {
    titles.push(words.shift() as string);
  }
  return [...titles, words[0] ?? ''].join(' ').trim();
}

/** ทักตามเวลาบนเครื่องผู้ใช้ ไม่ใช่เวลา server */
function greetingFor(hour: number): string {
  if (hour < 12) return 'Good Morning!';
  if (hour < 18) return 'Good Afternoon!';
  return 'Good Evening!';
}

type HomePageProps = {
  /** ปกติดึงจาก /api/me — รับ prop ไว้เผื่อ storybook/เทสหน้าเดี่ยว ๆ */
  studentName?: string;
  greeting?: string;
};

export default function HomePage({ studentName, greeting }: HomePageProps) {
  const navigate = useNavigate();
  const [tab, setTab] = useState('service');
  const [selectedService, setSelectedService] = useState<string | null>(null);

  // คนที่ login (cookie) — ไม่ login ProtectedRoute เด้งไปหน้า /login ให้แล้ว
  const { user: currentUser } = useAuth();

  const { data: announcements } = useQuery({
    queryKey: ['home-announcements'],
    enabled: Boolean(currentUser),
    queryFn: async () => {
      // /courses กรองตามคนล็อกอินแล้ว ที่ได้มาจึงเป็นวิชาของเขาล้วน ๆ
      // ยิงรายวิชาเพราะยังไม่มีเส้นรวมประกาศ — นักศึกษาลงไม่กี่วิชาเลยรับไหว
      const courses = await coursesService.getAll();
      const details = await Promise.all(
        courses.map((course) => courseService.getById(course.id))
      );
      return details.flatMap((course) =>
        course.announcements.map((item) => ({
          name: `${course.code} : ${item.authorName ?? course.lecturerName}`,
          text: item.message,
        }))
      );
    },
  });

  // ชื่อจริงอาจยาว หัวเรื่องเอาแค่ชื่อต้น
  const displayName = studentName ?? greetingName(currentUser?.name ?? '');
  const displayGreeting = greeting ?? greetingFor(new Date().getHours());
  const announcementEntries =
    announcements && announcements.length > 0 ? announcements : NO_ANNOUNCEMENT;

  const isService = tab === 'service';
  const isInstructor = currentUser?.role === 'instructor' || currentUser?.role === 'admin';
  const services = isInstructor ? INSTRUCTOR_SERVICES : STUDENT_SERVICES;

  const handleServiceSelect = (serviceId: string) => {
    if (serviceId === 'labwork') {
      navigate('/courses');
      return;
    }
    if (serviceId === 'instructor') {
      navigate('/instructor/courses');
      return;
    }
    setSelectedService(serviceId);
  };

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] w-full flex-col bg-[#FAFAF8] pb-24">
      {/* Hero — full-bleed background, content constrained to 1150px */}
      <div
        className="min-h-[280px] w-full flex-shrink-0 bg-cover bg-center px-10 pt-14 pb-[145px]"
        style={{ backgroundImage: `url(${heroBg})` }}
      >
        <div className="mx-auto flex w-full max-w-[1150px] flex-col gap-6">
          <div className="text-[32px] font-medium text-white">
            {displayGreeting} , {displayName}
          </div>

          <TabNav tabs={TABS} active={tab} onChange={setTab} />

          {isService && (
            <div key={tab} className={`flex flex-col gap-3.5 ${styles.fadeUp}`}>
              <div className="flex items-center justify-between">
                <div className="text-[19px] text-white">Virtual Environment</div>
                {selectedService && (
                  <button
                    type="button"
                    onClick={() => setSelectedService(null)}
                    className="cursor-pointer rounded-sm border border-white/40 bg-white/15 px-3.5 py-1.5 text-[13px] font-semibold text-white"
                  >
                    Clear
                  </button>
                )}
              </div>

              <div className="flex flex-wrap gap-4">
                {services.map((svc) => (
                  <ServiceCard
                    key={svc.id}
                    service={svc}
                    selected={selectedService === svc.id}
                    onSelect={handleServiceSelect}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Overlapping list cards — the top third sits on the hero */}
      {isService && (
        <div
          key={tab}
          className={`relative z-[2] mx-auto -mt-[60px] grid w-full max-w-[1230px] grid-cols-2 gap-5 px-10 ${styles.fadeUp}`}
        >
          <EntryBox heading="Activity Logging" entries={ACTIVITY_LOG} />
          <EntryBox heading="Announcement" entries={announcementEntries} />
        </div>
      )}
    </div>
  );
}
