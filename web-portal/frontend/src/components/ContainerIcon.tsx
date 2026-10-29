/**
 * ContainerIcon — กล่อง 4 ช่องแบบเดียวกับ LabLoader แต่นิ่ง (ไม่มีแขนคีบ / ไม่กระพริบ)
 * ใช้เป็นไอคอนของแต่ละพอร์ตในหน้า lab ที่เปิดแล้ว สีไล่ตามช่องแบบ mockup ของ Pete
 */
export default function ContainerIcon({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="1.5" y="1.5" width="37" height="37" fill="#fff" stroke="#185FA5" strokeWidth="3" />
      <rect x="7" y="7" width="12" height="12" fill="#185FA5" />
      <rect x="21" y="7" width="12" height="12" fill="#5B8EC4" />
      <rect x="7" y="21" width="12" height="12" fill="#5B8EC4" />
      <rect x="21" y="21" width="12" height="12" fill="#C4D6EC" />
    </svg>
  );
}
