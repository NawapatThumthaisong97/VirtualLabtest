# Virtual Lab — API Spec (ฝั่ง User / นักศึกษา)

> สเปคเส้น API เฉพาะหน้า **user** (ไม่รวม admin) — สกัดจาก
> [full-stack.md](full-stack.md) (หน้า × API × redirect) + [../DB_DIAGRAM.md](../DB_DIAGRAM.md) (schema v2)
> จุดประสงค์: ลงลึกกว่า full-stack.md ตรงที่ระบุ **request / response / error / ตาราง DB ที่แตะ** รายเส้น
>
> ⚠️ **field name อิงโค้ดจริงบน `main`** (ไม่ใช่ DB_DIAGRAM.md ที่ stale) — เพื่อนอัปเดต schema ไปแล้วแต่ยังไม่ sync กลับ diagram:
> `courses.banner_color` → **`courses.image_url`** + ตาราง `course_images` (1 course : 1 รูป, S3 URL) — ควรอัปเดต DB_DIAGRAM.md ตาม
>
> **การตัดสินใจที่ล็อกแล้ว** (Pete เคาะ 2026-07-23):
> 1. หน้า Session Loading (S5-pre) ใช้ **polling ทุก 2–3 วิ** — WebSocket เลื่อนไป Phase 2
> 2. หยุด lab ใช้ **`POST /api/sessions/{id}/stop`** (action ชัด กัน frontend ส่ง status มั่ว)
> 3. ประกาศมี **2 เส้น**: global (`/api/announcements`) + ราย course (`/api/courses/{id}/announcements`)
> 4. `GET /api/courses/{id}/docs` = list เอกสารที่อาจารย์อัป (PDF ฯลฯ) — **ยังไม่มีในตาราง DB** ดูท้ายไฟล์
> 5. หน้า S6 Login — **ยังไม่เคาะ** (ข้ามไปก่อน)
> 6. **Quota อยู่ระดับนักศึกษา (`quotas.user_id`) ไม่ใช่ระดับ lab** — ดู `POST /api/sessions` + Questionnaire ท้ายไฟล์

## กติกากลาง

| กติกา | รายละเอียด |
|-------|-----------|
| Auth | oauth2-proxy + Google SSO กันคนนอกทั้งเว็บ — backend อ่าน identity จาก header ที่ proxy ส่งมา ไม่มี endpoint login/logout เอง |
| Ownership | ทุกเส้น `sessions` เช็ค `session.user_id == ผู้ login` ไม่ใช่ → **403** |
| Enrollment guard | เส้นที่ผูกวิชา/แลป เช็คว่า user enroll วิชานั้นจริง (`enrollments`) ไม่ใช่ → **403** |
| Launch ไม่ block | `POST /api/sessions` ตอบ **202** ทันที งานช้า (SkyPilot) เป็น background task — frontend poll เอา (Constraint 2, ARCHITECTURE.md) |
| Polling | หน้า loading/session poll `GET /api/sessions/{id}` ทุก 2–3 วิ จน `status` เป็น terminal |
| Error format | `{ "detail": "..." }` ตาม exception handler ที่มีใน backend อยู่แล้ว |
| Pagination | `limit` / `offset` เฉพาะเส้น list ที่โตได้ (sessions) |
| เวลา | timestamp ทุกตัวเป็น ISO 8601 UTC (`...Z`) |

---

## 1. Identity

### `GET /api/me`
- **หน้า:** ทุกหน้าหลัง login (S1–S5)
- **ตาราง:** `users`
- **หมายเหตุ:** login ครั้งแรก auto-create user จาก SSO email
- **200**
```json
{
  "id": "uuid",
  "email": "student@ku.th",
  "name": "สมชาย ใจดี",
  "student_id": "6510000000",
  "role": "student"
}
```

---

## 2. Courses & Labs

### `GET /api/courses`
- **หน้า:** S2 Course
- **ตาราง:** `enrollments` → `courses` (+ นับจาก `labs`, `lab_progress`)
- **อธิบาย:** วิชาที่ฉัน enroll + สรุป progress ต่อวิชา
- **200**
```json
[
  {
    "id": "uuid",
    "code": "CS217",
    "name": "Operating Systems",
    "lecturer_name": "อ.สมหญิง",
    "image_url": "https://s3.../course/cs217/banner.png",
    "progress": { "labs_total": 8, "labs_finished": 3, "nearest_due": "2026-08-01T16:59:00Z" }
  }
]
```
> 📝 Pete ตีธง `progress` ไว้ (comment ②) — รูปแบบ `{labs_total, labs_finished, nearest_due}` ยังไม่ฟิกซ์ ถ้าไม่ใช้ที่หน้า S2 จริงตัดทิ้งได้ รอเคาะ

### `GET /api/courses/{course_id}/labs`
- **หน้า:** S3 Course detail — ตาราง "My labwork" (All my lab task / Uncomplete task)
- **ตาราง:** `labs` (เฉพาะ `status='published'`) + `lab_progress` ของฉัน + `sessions` (หา session ที่ยังรันของแลปนั้น)
- **อธิบาย:** Pete comment ③ — response เดิมน้อยไป หน้า S3 ต้องโชว์คอลัมน์ Name / Status / due date / Start-Stop / Brief detail ครบในตารางเดียว จึงเพิ่ม field:
- **200**
```json
[
  {
    "id": "uuid",
    "title": "Lab 01 — Processes",
    "order_no": 1,
    "due_at": "2026-08-01T16:59:00Z",
    "my_status": "in_progress",
    "running_session": { "id": "uuid", "status": "running" },
    "brief_detail": "ทดลองสร้าง/kill process ด้วย fork()"
  }
]
```
| field | ที่มา | หมายเหตุ |
|-------|-------|----------|
| `id`, `title`, `order_no`, `due_at` | `labs` | ตรง ๆ |
| `my_status` | `lab_progress.status` (`not_started`/`in_progress`/`finished`) | ถ้าไม่มีแถว = `not_started` |
| `running_session` | join `sessions` where `lab_id` + `user_id=ฉัน` + `status='running'` | คอลัมน์ "Start/Stop" ในกระดาษ — `null` ถ้าไม่มี session รันอยู่ ⚠️ ดู [ต้องเคาะ #4](#ต้องเคาะ-ที่เหลือ) |
| `brief_detail` | ❌ **ยังไม่มีในตาราง `labs`** (main มีแค่ title/order_no/doc_url/due_at) | ต้องเพิ่มคอลัมน์ `labs.brief_detail` ⚠️ ดู [ต้องเคาะ #5](#ต้องเคาะ-ที่เหลือ) |
- **หมายเหตุ frontend:** "Uncomplete task" = filter `my_status != 'finished'` ฝั่ง client จาก list เดียวกัน ไม่ต้องมีเส้นแยก
- **403** ไม่ได้ enroll วิชานี้

### `GET /api/courses/{course_id}/announcements`
- **หน้า:** S3 Course detail
- **ตาราง:** `announcements` (`course_id = {course_id}`)
- **อธิบาย:** ประกาศเฉพาะวิชานี้ (ต่างจากเส้น global ข้อ 4) — query จาก table เดิม ไม่แตะ schema
- **Query:** `limit` (default 10)
- **200**
```json
[
  { "id": "uuid", "message": "ส่ง Lab 1 ภายในศุกร์นี้", "author_name": "อ.สมหญิง", "created_at": "2026-07-20T03:00:00Z" }
]
```

### `GET /api/courses/{course_id}/docs`  ⚠️ รอเคาะ schema
- **หน้า:** S3 Course detail
- **อธิบาย:** list เอกสารระดับวิชา (PDF/สไลด์ ที่อาจารย์อัป) — **ยังไม่มีตารางรองรับใน DB_DIAGRAM.md** ดู [ต้องเคาะ #1](#ต้องเคาะ-ที่เหลือ)
- **200 (รูปแบบที่เสนอ)**
```json
[
  { "name": "Syllabus.pdf", "url": "https://r2.../presigned...", "size_mb": 2, "uploaded_at": "2026-07-10T00:00:00Z" }
]
```

### `GET /api/labs/{lab_id}`
- **หน้า:** S4 Lab instruction
- **ตาราง:** `labs` + `lab_progress` ของฉัน
- **อธิบาย:** Pete comment ✗ — **ตัด `image: {repository, tag}` ออก** user ไม่ต้องรู้ docker repo/tag (backend เก็บ `labs.image_id` ไว้ใช้ตอน launch เองพอ) response ฝั่ง user เหลือเท่าที่หน้าอ่านแลปต้องใช้จริง
- **200**
```json
{
  "id": "uuid",
  "title": "Lab 01 — Processes",
  "due_at": "2026-08-01T16:59:00Z",
  "my_status": "in_progress"
}
```
- **403** ไม่ได้ enroll

### `GET /api/labs/{lab_id}/doc`
- **หน้า:** S4 Lab instruction
- **ที่มา:** ไฟล์ Markdown บน R2 (`labs.doc_url`)
- **อธิบาย:** backend แปลงลิงก์รูปใน markdown เป็น **presigned URL** (อายุ ~1 ชม.) ก่อนส่ง + เช็ค enroll — frontend render ด้วย react-markdown
- **200**
```json
{ "markdown": "# Lab 01\n\n![diagram](https://r2.../presigned...)\n..." }
```
- **403** ไม่ได้ enroll · **404** ไม่มี doc
> 💡 Pete comment — ไอเดีย: ทำ tool แปลง **PDF → Markdown** เผื่ออาจารย์อัปเอกสารเป็น PDF แล้วให้ render เป็น markdown ในหน้าแลปได้ (ยังเป็นแค่ไอเดีย รอเคาะ — ดู Questionnaire)

### `POST /api/labs/{lab_id}/finish`
- **หน้า:** S5 Session (ปุ่ม Mark as Done)
- **ตาราง:** `lab_progress` (upsert `status='finished'`, `finished_at=now()`)
- **200**
```json
{ "lab_id": "uuid", "status": "finished", "finished_at": "2026-07-23T10:00:00Z" }
```

---

## 3. Sessions

### `POST /api/sessions`
- **หน้า:** S4 (ปุ่ม Launch)
- **ตาราง:** `sessions` (insert `status='pending'`) + `lab_progress` (upsert `in_progress`)
- **Body**
```json
{ "service_type": "lab", "lab_id": "uuid", "is_remote": false }
```
- **202** — background task เรียก SkyPilot ต่อ, frontend เด้งไป S5-pre แล้ว poll
```json
{ "session_id": "uuid" }
```
- **403** ไม่ได้ enroll · **409** quota หมด
> **Quota (Pete comment):** เช็ค quota ตอน launch ที่ **ระดับนักศึกษา** (`quotas.user_id`) — **ไม่ใช่**ระดับ lab ของ course. `service_type='compute'` (Compute service) ก็ต้องหักโควตาเดียวกันนี้. Phase 1 คิดแบบ wall-clock เวลาเปิด–ปิด session; `usage_records` (metering ละเอียด เผื่อฝั่ง admin) เป็น Phase 2 — วิธีคำนวณ/ตั้งค่ายังต้องเคาะ ดู Questionnaire ท้ายไฟล์

### `GET /api/sessions`
- **หน้า:** S1 Console (Recent work)
- **ตาราง:** `sessions` (เฉพาะของฉัน)
- **Query:** `status=` (เช่น `running`), `limit=` (Recent work ใช้ `limit=4`)
- **200**
```json
[
  { "id": "uuid", "service_type": "lab", "lab_id": "uuid", "status": "running", "started_at": "2026-07-23T09:00:00Z", "expires_at": "2026-07-23T13:00:00Z" }
]
```

### `GET /api/sessions/{id}`
- **หน้า:** S5-pre Session Loading (poll 2–3 วิ) และ S5 Session (poll)
- **ตาราง:** `sessions`
- **อธิบาย:** ตัวเดียวใช้ทั้ง 2 หน้า — S5-pre ดู `status` จน `running`, S5 ดู `endpoints` + `expires_at`
- **200 (กำลัง provision)**
```json
{ "id": "uuid", "status": "provisioning", "endpoints": null, "expires_at": null }
```
- **200 (พร้อมแล้ว)**
```json
{
  "id": "uuid",
  "status": "running",
  "endpoints": { "ide": "https://...", "client": "https://...", "ready": true },
  "expires_at": "2026-07-23T13:00:00Z"
}
```
- **200 (ล้มเหลว)** `status: "failed"` — frontend โชว์ error + ปุ่มลองใหม่
- **403** ไม่ใช่ session ของฉัน · **404** ไม่มี session

> **สถานะที่เป็นไปได้:** `pending → provisioning → running → stopped | succeeded | failed`

### `POST /api/sessions/{id}/stop`
- **หน้า:** S5 Session (+ S1 แท็บ Dashboard)
- **ตาราง:** `sessions` (`status='stopped'`, `ended_at=now()`)
- **อธิบาย:** SkyPilot down แล้ว mark stopped
- **200**
```json
{ "id": "uuid", "status": "stopped", "ended_at": "2026-07-23T11:00:00Z" }
```
- **403** ไม่ใช่ของฉัน

### `POST /api/sessions/{id}/reset`
- **หน้า:** S5 Session
- **ตาราง:** `sessions` (stop เก่า + insert ใหม่จาก `image_ref` เดิม)
- **202**
```json
{ "session_id": "uuid-ใหม่" }
```
- **403** ไม่ใช่ของฉัน

---

## 4. Announcements (global)

### `GET /api/announcements`
- **หน้า:** S1 Console
- **ตาราง:** `announcements` (global `course_id IS NULL` + วิชาที่ enroll) เรียงใหม่สุดก่อน
- **Query:** `limit` (S1 ใช้ `limit=4`, default 10)
- **200**
```json
[
  { "id": "uuid", "course_code": "CS217", "message": "ส่ง Lab 1 ภายในศุกร์นี้", "created_at": "2026-07-20T03:00:00Z" },
  { "id": "uuid", "course_code": null, "message": "ปิดปรับปรุงระบบเสาร์นี้", "created_at": "2026-07-19T02:00:00Z" }
]
```

---

## ตาราง cross-check — หน้า user มี API ครบ

| หน้า | เส้นที่ใช้ | ครบ |
|------|-----------|-----|
| S1 Console | `/api/me`, `/api/sessions?status=running&limit=4`, `/api/announcements?limit=4` | ✅ |
| S2 Course | `/api/courses` | ✅ |
| S3 Course detail | `/api/courses/{id}/labs`, `/api/courses/{id}/announcements`, `/api/courses/{id}/docs`⚠️ | ✅ |
| S4 Lab instruction | `/api/labs/{id}`, `/api/labs/{id}/doc`, `POST /api/sessions` | ✅ |
| S5-pre Loading | `GET /api/sessions/{id}` (poll) | ✅ |
| S5 Session | `GET /api/sessions/{id}` (poll), `/stop`, `/reset`, `POST /api/labs/{id}/finish` | ✅ |
| S6 Login | — ยังไม่เคาะ | ⏸ |

---

## ต้องเคาะ (ที่เหลือ)

| # | ประเด็น | สถานะ | เสนอ |
|---|---------|-------|------|
| 1 | **`GET /api/courses/{id}/docs`** — เอกสารระดับวิชา (PDF) ที่อาจารย์อัป **ไม่มีตารางใน DB** | รอเคาะ | (ก) เพิ่มตาราง `course_documents (id, course_id, name, r2_key, size_mb, uploaded_by, created_at)` หรือ (ข) ไม่แตะ schema — list จาก R2 prefix `course/{id}/docs/` ตรง ๆ แล้ว presign ตอนส่ง · **เอนไป (ก)** เพราะมี metadata (ชื่อไฟล์, คนอัป) คุมง่ายกว่า |
| 2 | **S6 Login** | ข้ามไปก่อน (Pete บอก) | เดิมเสนอ: คง SSO → S6 เหลือหน้า Home + ปุ่ม Sign in |
| 3 | **quota หมด ตอบ code ไหน** ที่ `POST /api/sessions` | รอเคาะ (ค้างจาก #34) | เอนไป **409 Conflict** + `detail` บอกเหลือกี่ชม. |
| 4 | **`running_session` ใน labs list** — คอลัมน์ Start/Stop | รอเคาะ | join `sessions` (lab_id + user + `status='running'`) แล้ว return เป็น object/`null` — ถ้าไม่อยากให้ query หนัก ทำเป็นเส้นแยกหรือ lazy โหลดทีหลังก็ได้ |
| 5 | **`labs.brief_detail`** — คำอธิบายสั้นต่อแลป (คอลัมน์ Brief detail) **ไม่มีในตาราง `labs` บน main** | รอเคาะ schema | เพิ่มคอลัมน์ `labs.brief_detail TEXT NULL` (ถ้าจะโชว์ในตาราง S3) |
| 6 | **PDF → Markdown converter** สำหรับ `labs/{id}/doc` | ไอเดีย | เผื่ออาจารย์อัป PDF แล้วอยากให้ render เป็น markdown — ประเมินว่ามี tool convert ที่เชื่อถือได้ไหม |

## ❓ Questionnaire (Pete ตั้งคำถามให้ทีมช่วยเคาะ)

| # | คำถาม | บริบท |
|---|-------|-------|
| Q1 | **Quota / Usage คิดยังไง ตั้งค่ายังไงใน DB?** | `quotas` มี `compute_hours_limit`, `storage_mb_limit`, `period` (weekly/monthly/semester) — ต้องตกลงว่า seed ค่าเริ่มต้นให้นักศึกษาเท่าไร ใครตั้ง (admin ต่อคน/ต่อวิชา) |
| Q2 | **นักศึกษาสร้าง labwork/session ได้กี่อัน แล้วถ้าโควตาหมดเกิดอะไรขึ้น?** | ตอน `POST /api/sessions` เกินโควตา → block (409) หรือให้ burst แล้วคิดเงินทีหลัง? |
| Q3 | **Compute service หักโควตาเดียวกับ lab ไหม?** | Pete บอกต้องหักด้วย — ยืนยันว่าใช้ pool เดียว (`quotas.user_id`) ทั้ง `service_type='lab'` และ `'compute'` |

## Phase 2 (จองไว้ ยังไม่ทำ)

| เส้น/ฟีเจอร์ | รอ |
|------|-----|
| WebSocket log สด ที่ S5-pre | ตอนนี้ใช้ poll ไปก่อน |
| `GET /api/sessions/{id}/logs` (SSE) | log streaming |
| metering จริง (`usage_records`) | ตอนนี้ quota คิดจาก wall-clock เปิด–ปิด session |

---

> **หมายเหตุ schema:** ไฟล์นี้ปรับ field name ให้ตรงกับโค้ดจริงบน `main` แล้ว (`courses.image_url` + ตาราง `course_images`, commit 3b519bf/e81e6bb) — **DB_DIAGRAM.md ยัง stale** (ยังเขียน `banner_color`) ควรอัปเดต diagram แยกอีก PR ให้ตรงกับ schema จริง
