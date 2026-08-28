/**
 * ServiceCard Component
 * Selectable card on the Home hero — one per virtual environment service.
 */
import flask from '../assets/home/labwork-flask-icon-white.png';
import compute from '../assets/home/compute-service-icon-white.png';

/** Icon key -> bundled asset, so services can be described as plain data. */
const ICONS: Record<string, string> = {
  labwork: flask,
  compute: compute,
};

export type Service = {
  id: string;
  title: string;
  text: string;
  /** key into ICONS */
  icon: string;
  /** rendered icon width in px — the two artworks have different aspect ratios */
  iconWidth: number;
};

type ServiceCardProps = {
  service: Service;
  selected: boolean;
  onSelect: (id: string) => void;
};

export default function ServiceCard({ service, selected, onSelect }: ServiceCardProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={() => onSelect(service.id)}
      className={`flex w-[340px] cursor-pointer items-center justify-between gap-3.5 rounded-[10px] border-[1.5px] bg-white/12 p-[22px] text-left transition-colors ${
        selected ? 'border-white' : 'border-white/32 hover:border-white/60'
      }`}
    >
      <div>
        <div className="mb-2 text-[17px] font-semibold text-white">{service.title}</div>
        <div className="text-[13.5px] leading-relaxed text-white/75">{service.text}</div>
      </div>
      <img
        src={ICONS[service.icon]}
        alt=""
        style={{ width: service.iconWidth }}
        className="h-auto flex-shrink-0"
      />
    </button>
  );
}
