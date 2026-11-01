/**
 * หน้าแรกหลัง login: กลับไปหน้าที่ถูกเด้งมา login (ถ้ามี) ไม่งั้น admin → /admin, role อื่น → /
 */
export function homeFor(role: string | undefined, from?: string): string {
  if (from && from !== '/' && from !== '/login') return from;
  return role === 'admin' ? '/admin' : '/';
}

/** หน้าหลักของบุคลากร — ใช้ตอนอาจารย์ / admin เปิดหน้าที่เป็นของนักศึกษา (วิชาที่ลงเรียน / แลป) */
export function staffHomeFor(role: string): string {
  return role === 'admin' ? '/admin' : '/instructor';
}
