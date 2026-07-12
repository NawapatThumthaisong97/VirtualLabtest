// ✏️ STUDENT MODULE — theme.js
// เปลี่ยนสีทั้งเว็บได้จากไฟล์นี้ไฟล์เดียว แก้เสร็จกด save ใน editor แล้ว refresh หน้าเว็บ
//
// โจทย์ตัวอย่าง:
//   1. เปลี่ยน accent เป็นสีโปรดของตัวเอง
//   2. ทำโหมดกลางคืน (bg เข้ม ink สว่าง)
//   3. [ยาก] เพิ่ม key ใหม่ เช่น --radius แล้วไปใช้ใน style.css

export const palette = {
  "--bg": "#efe9e1",       // พื้นหลังหน้าเว็บ
  "--panel": "#fdfbf8",    // การ์ด Now Playing
  "--sidebar": "#2b2622",  // แถบเมนูซ้าย
  "--ink": "#221d19",      // สีตัวอักษรหลัก
  "--muted": "#9a8f84",    // ตัวอักษรรอง
  "--accent": "#c8501e",   // สีแบรนด์ ปุ่ม play, hero
  "--accent-ink": "#ffffff",
};

export function applyTheme(root) {
  for (const [key, value] of Object.entries(palette)) {
    root.style.setProperty(key, value);
  }
}
