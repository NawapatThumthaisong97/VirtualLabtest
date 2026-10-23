import { colors } from './theme';
import { Card, cellBorder } from './ui';

/** การ์ดที่ยังไม่มี API — บอกตรง ๆ ว่ายังไม่มีข้อมูล ไม่ใส่ตัวเลขตัวอย่าง */
export default function PendingCard({ title, note, height = 180 }: { title: string; note: string; height?: number }) {
  return (
    <Card>
      <div style={{ padding: '12px 14px', borderBottom: cellBorder, color: colors.blue, fontSize: 14 }}>{title}</div>
      <div
        style={{
          height,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          color: colors.muted,
          textAlign: 'center',
          padding: 16,
        }}
      >
        <span style={{ fontSize: 14 }}>ยังไม่มีข้อมูล</span>
        <span style={{ fontSize: 11 }}>{note}</span>
      </div>
    </Card>
  );
}
