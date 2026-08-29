/**
 * EntryBox Component
 * Cream list card used for Activity Logging / Announcement on the Home page.
 * The top third of the box overlaps the hero, so it carries its own shadow.
 */
export type Entry = {
  name: string;
  text: string;
};

type EntryBoxProps = {
  heading: string;
  entries: Entry[];
};

export default function EntryBox({ heading, entries }: EntryBoxProps) {
  return (
    <div className="flex flex-col gap-3.5">
      <div className="text-[15px] font-semibold text-white">{heading}</div>
      <div className="rounded-xl bg-[#FAF7F1] p-6 shadow-[0_8px_24px_rgba(10,30,60,0.15)]">
        {entries.map((e, i) => (
          <div
            key={i}
            className={i === 0 ? 'pb-3' : 'border-t border-[#E9E4DA] py-3'}
          >
            <div className="mb-1 text-[13.5px] font-semibold text-[#2C2C2A]">{e.name}</div>
            <div className="text-[13px] leading-normal text-[#6B6A66]">{e.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
