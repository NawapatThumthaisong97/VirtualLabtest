# Virtual Lab — Design Component Ideas

> คลังไอเดีย UI component สำหรับหน้าใน [frontend.md](../docs/must-read/frontend.md) (S0–S6, A1–A6)
> Stack ที่มีอยู่แล้ว: React + Tailwind + @tanstack/react-query · โลโก้ขาว/ดำใน `assets/`
> อ้างอิง mockup: หน้า Lab Instruction (topbar ดำ, ปุ่ม Start Lab work น้ำเงิน) + หน้า Console ฉบับตกลงแล้ว
> (interactive mockup ของ Console อยู่ที่ artifact ของ Pete — แชร์ให้ทีมได้จากหน้านั้น)
> **หมายเหตุ:** S7 My Dashboard ถูกยุบเป็นแท็บ Dashboard ใน Console แล้ว — ดู section Console

## 1. Design tokens (ตกลงก่อน component)

| Token | ค่าที่เสนอ | หมายเหตุ |
|---|---|---|
| สีหลัก (primary) | น้ำเงิน (ปุ่ม Start Lab work ใน mockup) | ปุ่ม action หลักทั้งเว็บใช้สีเดียวกัน |
| Topbar | พื้นดำ + โลโก้ขาว | ตาม mockup — ใช้ `virtual-lab-logo-white.svg` |
| สีสถานะ | เขียว = running/finished · เหลือง = provisioning/in progress · แดง = failed · เทา = stopped/not started | ใช้ชุดเดียวกันทุกหน้า ห้ามต่างคนต่างเลือก |
| สีต่อวิชา | จาก `courses.banner_color` ใน DB | การ์ดวิชา/หัวหน้า Labwork |
| Font | ไทย + อังกฤษอ่านง่าย เช่น Noto Sans Thai / IBM Plex Sans Thai | เอกสารแลปมี code block ต้องมี mono ด้วย |

## 2. Layout components (ใช้ร่วมทุกหน้า)

| Component | อยู่หน้าไหน | รายละเอียด |
|---|---|---|
| `TopNav` | ทุกหน้าหลัง login | โลโก้ · ช่องค้นหา (Search labs, courses...) · avatar เมนู (ชื่อ, role, logout) |
| `PageHeader` | S3–S5, A2–A6 | ชื่อหน้า/วิชา (เช่น "CS217 : Infrastructure") + แท็บ + ปุ่ม action หลักขวาสุด — ตาม mockup |
| `Tabs` | S4/S5 (Instruction / Dashboard), A3 (Labs / Members / Announcements) | แท็บแบบขีดเส้นใต้ตัว active |
| `SideMenu` (hamburger) | ทุกหน้า | ลิงก์ไป Console, Courses, Compute, Dashboard (+ เมนู Admin ถ้า role=admin) |
| `EmptyState` | ทุก list | ภาพ + ข้อความ + ปุ่มชวนทำ เช่น "ยังไม่มีแลปที่กำลังทำ — ไปที่ Courses" |
| `LoadingSkeleton` | ทุกหน้า | โครงเทา ๆ ระหว่างรอ react-query |
| `Toast` | ทุกหน้า | แจ้งผลสั้น ๆ: "หยุด session แล้ว", "เกิดข้อผิดพลาด" |
| `ConfirmDialog` | ก่อน stop/reset/force-stop/reject | action ทำลายต้องยืนยันก่อนเสมอ |

## 3. Components ฝั่งนักศึกษา

### Console (S1) — 2 แท็บ: Quick Action / Dashboard

> **ตกลงแล้ว: ยุบ S7 My Dashboard เข้ามาเป็นแท็บ Dashboard ของ Console** — API ไม่เปลี่ยน
> ผังตกลงตาม mockup (2026-07-18): ซ้ายกว้าง (การ์ด + Recent) / ขวาแคบ (โปรไฟล์ + ประกาศ)

```
[TopNav ดำ]
[แท็บ: Quick Action | Dashboard]

--- แท็บ Quick Action ---
[ContinueStrip (แถบดำ + ปุ่ม Resume น้ำเงิน)]
[Virtual Environment: การ์ด 2 ใบ]   [ProfileQuotaCard]
[Recent work (ตาราง + see more)]     [AnnouncementFeed]

--- แท็บ Dashboard (S7 เดิม) ---
[SessionTable (running + ปุ่ม Stop)]
[QuotaMeter ใหญ่: ชั่วโมง | storage]
```

**แท็บ Quick Action**

| Component | ผูกกับ API | รายละเอียด |
|---|---|---|
| `ContinueStrip` | `/api/dashboard/continue` | แถบดำบนสุด: label "ทำต่อจากที่ค้างไว้" + ชื่อแลป + วิชา + due + ปุ่ม Resume (น้ำเงิน) — ถ้าไม่มีแลปค้าง ซ่อนทั้งแถบ |
| `ServiceCard` x2 | `/api/dashboard/summary` | **Lab work**: ตัวเลขจริง "2 แลปกำลังทำ · ใกล้ due: Lab 3" คลิกไป Courses (เป็นประตูสู่ flow หลัก) / **Compute**: disabled + ป้าย "Coming soon" |
| `RecentWorkTable` | `/api/sessions?limit=4` | ตาราง 3 คอลัมน์: ชื่อ · ชั่วโมง · `StatusBadge` — ลิงก์ "see more" สลับไปแท็บ Dashboard |
| `ProfileQuotaCard` | `/api/me` + `/api/dashboard/summary` | "Welcome!, {name}" + role/วิชา + แถบ quota ชั่วโมง + แถบ storage (เกิน ~80% เปลี่ยนสีเตือน) — กล่องทักทายที่มีหน้าที่ |
| `AnnouncementFeed` | `/api/announcements` | badge ที่มา: วิชา (สี primary) / global (เทา) + เวลา relative + ข้อความ |

**แท็บ Dashboard** (ยุบจาก S7)

| Component | ผูกกับ API | รายละเอียด |
|---|---|---|
| `SessionTable` | `/api/sessions?status=running` | คอลัมน์: Session · วิชา · สถานะ · Uptime · ปุ่ม Stop (ผ่าน ConfirmDialog) — แถว provisioning ไม่มีปุ่ม Stop |
| `QuotaMeter` | `/api/dashboard/summary` | สองกล่อง: Compute quota ("ใช้ไป 13.5/20 h · 6.5 h left" + คำอธิบาย wall-clock) / Storage ("1.6/2 GB") — **แสดงชั่วโมง ไม่แสดงเงิน** |

### Courses / Labwork (S2, S3)

| Component | ผูกกับ API | รายละเอียด |
|---|---|---|
| `CourseCard` | `/api/courses` | แถบสี banner_color + code + ชื่อ + ชื่ออาจารย์ + `ProgressBar` "3/4 labs" |
| `LabRow` | `/api/courses/{id}/labs` | ลำดับ + ชื่อแลป + `StatusBadge` + due date — ใกล้ due เปลี่ยนสีเตือน |
| `ProgressBar` | (คำนวณจาก labs_finished/labs_total) | ใช้ซ้ำทั้ง CourseCard และหัวหน้า Labwork |
| `StatusBadge` | — | ป้ายสถานะกลาง: not started (เทา) / in progress (เหลือง) / finished (เขียว) |

### Lab Instruction / Lab Hub (S4, S5)

| Component | ผูกกับ API | รายละเอียด |
|---|---|---|
| `MarkdownViewer` | `/api/labs/{id}/doc` | react-markdown + syntax highlight + **ปุ่ม copy บน code block** (แลปสั่ง terminal เยอะ) |
| `LaunchButton` | `POST /api/sessions` | กดแล้ว disabled + spinner ทันที (กันกดรัว) แล้วพาไป Lab Hub |
| `SessionStatusPill` | `GET /api/sessions/{id}` (poll) | pending → provisioning → running — สีตามชุดสถานะกลาง |
| `ServiceReadyList` | endpoints ใน session | แถว IDE / Client / SSH: จุดสถานะ ready + ปุ่ม "เปิด" (เปิด tab ใหม่) — ยังไม่ ready เป็นสีเทากดไม่ได้ |
| `CountdownTimer` | `expires_at` | เวลาที่เหลือของ session — ต่ำกว่า 10 นาทีเปลี่ยนสีเตือน |
| `SessionActions` | `/stop`, `/reset` | ปุ่ม Stop (แดง) / Reset — ผ่าน ConfirmDialog |
| `MarkDoneButton` | `POST /api/labs/{id}/finish` | ปุ่ม "Mark as Done" — กดแล้วเปลี่ยนเป็นสถานะ finished |

## 4. Components ฝั่งแอดมิน

| Component | หน้า | รายละเอียด |
|---|---|---|
| `AdminStatCards` | A1 | ตัวเลขรวม: session รันอยู่ · ต่อ node · image รอ approve (badge) |
| `DataTable` | A1, A5 | ตารางกลาง sort/filter ได้ — ใช้ซ้ำทุกหน้า admin |
| `ForceStopButton` | A5 | ปุ่มหยุด session ของใครก็ได้ + ConfirmDialog ระบุชื่อ user |
| `CourseForm` | A2 | ฟอร์มสร้าง/แก้วิชา + ตัวเลือก banner_color แบบ swatch |
| `BulkEnrollBox` | A3 Members | textarea วาง email หลายบรรทัด → preview รายชื่อ → ยืนยัน |
| `LabEditor` | A3 Labs | ฟอร์มแลป: ชื่อ, ลำดับ, due, เลือก image (dropdown จาก lab_images ที่ approved), ปุ่ม publish |
| `ImageQueueRow` | A4 | repository:tag + ขนาด + ผู้อัปโหลด + ปุ่ม Approve / Reject (ใส่เหตุผล) |
| `QuotaForm` | A6 | ตั้ง default ต่อวิชา + override รายคน |

## 5. กติกา UI กลาง

| กติกา | รายละเอียด |
|---|---|
| ลิงก์เปิด service | render เฉพาะเมื่อ `status='running'` — สถานะอื่นปุ่มเทา (ตามที่ตกลงเรื่อง endpoints) |
| Poll | Lab Hub poll `GET /api/sessions/{id}` ทุก 2–3 วิ ด้วย react-query `refetchInterval` — หยุด poll เมื่อสถานะนิ่ง (stopped/failed) |
| Error | ทุก mutation แสดง Toast จาก `{detail}` ของ backend — ไม่ swallow error เงียบ |
| Responsive | นักศึกษาเปิดจากมือถือได้ (ดูสถานะ/ประกาศ) แต่หน้า Lab Hub เน้น desktop |
| ธีม | เริ่ม light theme ก่อน (ตาม mockup) — โครง token เผื่อ dark ไว้ |

## 6. ลำดับการทำ (เสนอ)

1. Design tokens + `TopNav` + `PageHeader` + `StatusBadge` — ของที่ทุกหน้าใช้
2. เส้นทางหลักนักศึกษา: Courses → Labwork → Instruction (`MarkdownViewer`) → Lab Hub — คือ demo ที่ขายได้
3. Console + Dashboard (การ์ด/ตาราง — ต้องรอ API aggregate)
4. ฝั่ง Admin (ใช้ `DataTable` ร่วมเป็นแกน)
