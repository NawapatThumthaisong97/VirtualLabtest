/**
 * Home Page
 *
 * Hero on a full-bleed background with the tab strip and the service cards,
 * then two list cards whose top third overlaps the hero.
 * The navbar comes from RootLayout, so it is not repeated here.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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

const SERVICES: Service[] = [
  {
    id: 'labwork',
    title: 'Lab work',
    text: 'Launch a preconfigured lab in one click. No setup, no installs, just start working.',
    icon: 'labwork',
    iconWidth: 48,
  },
  {
    id: 'compute',
    title: 'Compute service',
    text: 'Need more power? Burst your lab to the cloud and get GPUs on demand.',
    icon: 'compute',
    iconWidth: 60,
  },
];

const ACTIVITY_LOG: Entry[] = [
  { name: 'Virtual Lab team', text: LOREM },
  { name: 'CS102 : Prof.Jose Matt', text: LOREM },
];

const ANNOUNCEMENTS: Entry[] = [
  { name: 'Virtual Lab team', text: LOREM },
  { name: 'CS102 : Prof.Jose Matt', text: LOREM },
];

type HomePageProps = {
  /** Placeholder until the session tells us who is signed in. */
  studentName?: string;
  greeting?: string;
};

export default function HomePage({
  studentName = 'Peraphat',
  greeting = 'Good Morning!',
}: HomePageProps) {
  const navigate = useNavigate();
  const [tab, setTab] = useState('service');
  const [selectedService, setSelectedService] = useState<string | null>(null);

  const isService = tab === 'service';

  const handleServiceSelect = (serviceId: string) => {
    if (serviceId === 'labwork') {
      navigate('/courses');
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
            {greeting} , {studentName}
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
                {SERVICES.map((svc) => (
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
          <EntryBox heading="Announcement" entries={ANNOUNCEMENTS} />
        </div>
      )}
    </div>
  );
}
