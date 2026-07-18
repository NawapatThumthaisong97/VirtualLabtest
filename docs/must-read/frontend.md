# Virtual Lab — Frontend Pages

> โครงหน้าเว็บทั้งหมด (Draft v1 — อิงจาก database schema v2 ใน PR #30)

## หน้าฝั่งนักศึกษา (Student)

| # | หน้า | หมายเหตุ |
|---|------|----------|
| S0 | **Home** (public) | ยังไม่ login — แนะนำระบบ + ปุ่ม Sign in with Google |
| S1 | **Console** | หลัง login — 2 แท็บ: **Quick Action** (Continue strip, การ์ด service, Recent work, โปรไฟล์+quota, ประกาศ) / **Dashboard** (ตาราง session ที่รันอยู่ + quota meter) |
| S2 | **Courses** | รายวิชาที่ enroll |
| S3 | **Labwork** (ต่อวิชา) | แลปทั้งหมดในวิชา + สถานะ + due |
| S4 | **Lab Instruction** | โจทย์/เอกสาร (doc จาก R2) + ปุ่ม **Launch Lab** |
| S5 | **Lab Hub** | คุม session หลัง launch |
| S6 | **Compute Service** | โชว์ UI เฉย ๆ (placeholder — ปุ่มกดไม่ได้/ขึ้น "Coming soon") |

> S7 My Dashboard (เดิม) ถูกยุบเป็นแท็บ Dashboard ของ Console (S1) — เนื้อหาเดิมครบ ไม่มีหน้าแยกแล้ว

**Flow หลัก:** `Console -> Courses -> Labwork -> Lab Instruction -> กด Launch -> Lab Hub`

## หน้าฝั่งแอดมิน (Admin)

| # | หน้า | หมายเหตุ |
|---|------|----------|
| A1 | **Admin Console** | ภาพรวมระบบ: session ทั้งหมด/ต่อ node, badge image รอ approve, โพสต์ประกาศ global |
| A2 | **Courses** | รายวิชาทั้งหมด + สร้างวิชาใหม่ (code, ชื่อ, ชื่ออาจารย์, สี) |
| A3 | **Course Detail** | หน้าเดียว 3 แท็บ: Labs / Members (bulk enroll) / Announcements |
| A4 | **Images** | คิว approve/reject จาก Docker Upload Portal + พื้นที่ registry |
| A5 | **Sessions Monitor** | session ทั้งระบบ, filter วิชา/node, ปุ่ม force-stop |
| A6 | **Quotas** | default ต่อวิชา + override รายคน |

> Login ด้วย Google เหมือนกันทั้งสองฝั่ง — `role='admin'` เห็นเมนู Admin เพิ่ม / นักศึกษาเข้า `/admin/*` ได้ 403
