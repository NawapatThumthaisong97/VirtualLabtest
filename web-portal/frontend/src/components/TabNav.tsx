/**
 * TabNav Component
 * Underlined tab strip used on the Home hero.
 */
export type Tab = {
  id: string;
  label: string;
};

type TabNavProps = {
  tabs: Tab[];
  active: string;
  onChange: (id: string) => void;
};

export default function TabNav({ tabs, active, onChange }: TabNavProps) {
  return (
    <div
      role="tablist"
      className="inline-flex items-center gap-7 self-start border-b border-white/25 text-base"
    >
      {tabs.map((t) => {
        const on = active === t.id;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(t.id)}
            className={`cursor-pointer border-b-2 pb-2 transition-colors ${
              on ? 'border-white font-semibold text-white' : 'border-transparent text-white/55'
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
