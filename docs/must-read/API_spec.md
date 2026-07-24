# Virtual Lab — API Spec (ฝั่ง User / นักศึกษา)

## กติกากลาง

| กติกา | รายละเอียด |
|-------|-----------|
| Auth | oauth2-proxy + Google SSO กันคนนอกทั้งเว็บ — backend อ่าน identity จาก header ที่ proxy ส่ง ไม่มี endpoint login/logout เอง |
| Ownership | ทุกเส้น `sessions` เช็ค `session.user_id == ผู้ login` ไม่ใช่ → **403** |
| Enrollment guard | เส้นที่ผูกวิชา/แลป เช็คว่า user enroll วิชานั้นจริง (`enrollments`) ไม่ใช่ → **403** |
| Launch ไม่ block | `POST /api/sessions` ตอบ **202** ทันที งานช้า (SkyPilot) เป็น background task — frontend poll เอา (Constraint 2) |
| Quota / Usage | **ทุก session** เปิดแถว `usage_records` เสมอ (track การใช้) · เช็ค quota ก่อน launch **เฉพาะ** `service_type='compute_service'` เกิน = **409** · `lab` ไม่เช็ค |
| Error format | `{ "detail": "..." }` ตาม exception handler ที่มีใน backend อยู่แล้ว |
| Pagination | `limit` / `offset` เฉพาะเส้น list ที่โตได้ (sessions) |
| เวลา | timestamp ทุกตัว ISO 8601 UTC (`...Z`) |



## 1. Identity

### `GET /api/me`
- **หน้า:** ทุกหน้าหลัง login · **ตาราง:** `users` · login ครั้งแรก auto-create จาก SSO email
```json
{ "id": "uuid", "email": "student@ku.th", "name": "สมชาย ใจดี", "student_id": "6510000000", "role": "student" }
```

---

## 2. Courses & Labs

### `GET /api/courses`
- **หน้า:** S2 Course · **ตาราง:** `enrollments` → `courses`
- ไม่ส่ง `progress` (หน้า S2 ไม่โชว์ — track ไว้ใน `lab_progress` เฉย ๆ)
```json
[
  { "id": "uuid", "code": "CS217", "name": "Operating Systems", "lecturer_name": "อ.สมหญิง", "image_url": "https://s3.../course/cs217/banner.png" }
]
```

### `GET /api/courses/{course_id}/labs`
- **หน้า:** S3 Course detail — ตาราง "My labwork"
- **ตาราง:** `labs` (เฉพาะ `published`) + `lab_progress` + `sessions` (หา session ที่ยังรัน)
```json
[
  {
    "id": "uuid",
    "title": "Lab 01 — Processes",
    "order_no": 1,
    "due_at": "2026-08-01T16:59:00Z",
    "my_status": "in_progress",
    "brief_detail": "ทดลองสร้าง/kill process ด้วย fork()",
    "running_session": { "id": "uuid", "status": "running" }
  }
]
```
| field | ที่มา |
|-------|-------|
| `id`, `title`, `order_no`, `due_at`, `brief_detail` | `labs` (`brief_detail` = คอลัมน์ที่ต้องเพิ่ม) |
| `my_status` | `lab_progress.status` — ถ้าไม่มีแถว = `not_started` |
| `running_session` | join `sessions` where `lab_id` + `user_id=ฉัน` + `status='running'` → object หรือ `null` (frontend ใช้ทำปุ่ม Resume/Start) |
- "Uncomplete task" = frontend filter `my_status != 'finished'` จาก list เดียวกัน · **403** ไม่ได้ enroll

### `GET /api/courses/{course_id}/announcements`
- **หน้า:** S3 · **ตาราง:** `announcements` (`course_id = {course_id}`) · **Query:** `limit` (default 10)
```json
[
  { "id": "uuid", "message": "ส่ง Lab 1 ภายในศุกร์นี้", "author_name": "อ.สมหญิง", "created_at": "2026-07-20T03:00:00Z" }
]
```

### `GET /api/courses/{course_id}/docs`
- **หน้า:** S3 · list เอกสารระดับวิชา (PDF/สไลด์ ที่อาจารย์อัป) · **ตาราง:** `course_documents` (ต้องเพิ่ม) → presign URL ตอนส่ง
```json
[
  { "name": "Syllabus.pdf", "url": "https://s3.../presigned...", "size_mb": 2, "uploaded_at": "2026-07-10T00:00:00Z" }
]
```

### `GET /api/labs/{lab_id}`
- **หน้า:** S4 Lab instruction · **ตาราง:** `labs` + `lab_progress`
- ไม่ส่ง image repository/tag (user ไม่ต้องรู้ docker repo — backend ใช้ `labs.image_id` ตอน launch เอง)
```json
{ "id": "uuid", "title": "Lab 01 — Processes", "due_at": "2026-08-01T16:59:00Z", "my_status": "in_progress" }
```
- **403** ไม่ได้ enroll

### `GET /api/labs/{lab_id}/doc`
- **หน้า:** S4 · เอกสารแลป Markdown จาก R2 (`labs.doc_url`)
- backend แปลงลิงก์รูปเป็น **presigned URL** (~1 ชม.) + เช็ค enroll — frontend render ด้วย react-markdown
```json
{ "markdown": "# Lab 01\n\n![diagram](https://s3.../presigned...)\n..." }
```
- **403** ไม่ได้ enroll · **404** ไม่มี doc

### `POST /api/labs/{lab_id}/finish`
- **หน้า:** S5 (ปุ่ม Mark as Done) · **ตาราง:** `lab_progress` (upsert `finished`)
```json
{ "lab_id": "uuid", "status": "finished", "finished_at": "2026-07-23T10:00:00Z" }
```

---

## 3. Sessions

### `POST /api/sessions`
- **หน้า:** S4 (ปุ่ม Launch) · **ตาราง:** `sessions` (insert `pending`) + `lab_progress` (upsert `in_progress` ถ้าเป็น lab) + เปิด `usage_records`
```json
{ "service_type": "lab", "lab_id": "uuid", "is_remote": false }
```
- `service_type='lab'` → ไม่เช็ค quota · `service_type='compute_service'` → เช็ค quota ก่อน เกิน = **409**
- **202** — background task เรียก SkyPilot ต่อ, frontend เด้งไป S5-pre แล้ว poll
```json
{ "session_id": "uuid" }
```
- **403** ไม่ได้ enroll (เฉพาะ lab)

### `GET /api/sessions`
- **หน้า:** S1 Console (Recent work) · **ตาราง:** `sessions` (เฉพาะของฉัน) · **Query:** `status=`, `limit=`
```json
[
  { "id": "uuid", "service_type": "lab", "lab_id": "uuid", "status": "running", "started_at": "2026-07-23T09:00:00Z", "expires_at": "2026-07-23T13:00:00Z" }
]
```

### `GET /api/sessions/{id}`
- **หน้า:** S5-pre (poll 2–3 วิ) และ S5 Session (poll) · **ตาราง:** `sessions`
- S5-pre ดู `status` จน `running` · S5 ดู `endpoints` + `expires_at`
```json
{
  "id": "uuid",
  "status": "running",
  "endpoints": { "ide": "https://...", "client": "https://...", "ready": true },
  "expires_at": "2026-07-23T13:00:00Z"
}
```
- กำลัง provision → `status: "provisioning"`, `endpoints: null` · ล้มเหลว → `status: "failed"`
- สถานะ: `pending → provisioning → running → stopped | succeeded | failed`
- **403** ไม่ใช่ของฉัน · **404** ไม่มี session

### `POST /api/sessions/{id}/stop`
- **หน้า:** S5 (+ S1 แท็บ Dashboard) · **ตาราง:** `sessions` (`stopped`, `ended_at=now()`) — SkyPilot down
```json
{ "id": "uuid", "status": "stopped", "ended_at": "2026-07-23T11:00:00Z" }
```
- **403** ไม่ใช่ของฉัน

### `POST /api/sessions/{id}/reset`
- **หน้า:** S5 · stop เก่า + launch ใหม่จาก `image_ref` เดิม
```json
{ "session_id": "uuid-ใหม่" }
```
- **202** · **403** ไม่ใช่ของฉัน

---

## 4. Announcements (global)

### `GET /api/announcements`
- **หน้า:** S1 Console · **ตาราง:** `announcements` (global `course_id IS NULL` + วิชาที่ enroll) เรียงใหม่สุดก่อน · **Query:** `limit` (default 10, S1 ใช้ 4)
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
| S1 Console | `/api/me`, `/api/sessions?status=running&limit=4`, `/api/announcements?limit=4` | ครบ |
| S2 Course | `/api/courses` | ครบ |
| S3 Course detail | `/api/courses/{id}/labs`, `/api/courses/{id}/announcements`, `/api/courses/{id}/docs` | ครบ |
| S4 Lab instruction | `/api/labs/{id}`, `/api/labs/{id}/doc`, `POST /api/sessions` | ครบ |
| S5-pre Loading | `GET /api/sessions/{id}` (poll) | ครบ |
| S5 Session | `GET /api/sessions/{id}` (poll), `/stop`, `/reset`, `POST /api/labs/{id}/finish` | ครบ |
| S6 Login | — ยังไม่เคาะ | — |

---

## Quota & Usage lifecycle

> "เช็ค quota" กับ "เก็บ usage" คนละจังหวะกัน · quota ไม่ใช่ counter ที่ลดลง — เก็บแค่ `limit` แล้วเทียบกับ `SUM(usage)`

**2 ตารางที่เกี่ยว**

| ตาราง | เก็บอะไร | field หลัก |
|-------|---------|-----------|
| `sessions` | เวลา | `started_at`, `ended_at`, `expires_at` |
| `usage_records` | ผลการใช้ (ไม่มี started/ended) | `session_id`, `cpu_seconds`, `gpu_seconds`, `ram_mb_hours`, `is_cloud_burst`, `est_cost_thb`, `recorded_at` |

**จังหวะ**

```
1) POST /api/sessions              จุด "เช็ค" (gate) เฉพาะ compute_service
   - อ่าน SUM(usage งวดนี้) เทียบ quotas.compute_hours_limit → เต็ม = 409
   - ผ่าน → insert sessions(status=pending)
   - lab: ข้ามการเช็ค แต่ยังนับ usage ตอนจบเหมือนกัน

2) provisioning → running          set sessions.started_at

3) ระหว่างรัน                       usage สะสมตามเวลา (ยังไม่เขียน usage_records)

4) จบ session                      จุด "เก็บ usage"
   ทางที่จบได้: POST /stop · POST /reset · background task (expires_at ผ่าน / SkyPilot succeeded|failed)
   - update sessions.ended_at = now()
   - duration = ended_at − started_at
   - insert usage_records:
       cpu_seconds  = duration_sec × core ที่ขอตอน launch
       gpu_seconds  = duration_sec × gpu
       ram_mb_hours = ram_mb × duration_hours
       est_cost_thb = คิดจากตารางราคา (snapshot ไว้เลย ห้าม recompute)
```

**จุดสำคัญ**
- **จุดเก็บ usage ไม่ใช่ API เส้นเดียว** — ทุกทางที่ session จบต้องเขียน (รวม background task ตอนหมดเวลา/พังเอง) กัน usage หายเวลา user ปิดเบราว์เซอร์หนี
- **"เหลือกี่ชั่วโมง"** (dashboard) = `limit − ( SUM(session ที่จบแล้ว) + (now − started_at ของตัวที่ยังรัน) )` คำนวณสด ไม่ decrement
- `usage_records.*` เป็น **NOT NULL หมด** → ตอนจบต้องเติมค่าครบ — Phase 1 อนุโลมใช้ `duration × core` ตรง ๆ, metering ละเอียดจาก pod = Phase 2

---

## ยังต้องเคาะ

| # | คำถาม | หมายเหตุ |
|---|-------|----------|
| 1 | **Quota config** — `compute_hours_limit` ตั้งเริ่มต้นเท่าไร, ใครตั้ง (admin ต่อคน/ต่อวิชา), `period` ไหน (weekly/monthly/semester) | ใช้เฉพาะ `compute_service` |
| 2 | **HTTP code ตอน quota หมด** | ชั่วคราวใช้ 409 |
| 3 | **หน้า S6 Login** | ถ้าคง SSO → เหลือหน้า Home + ปุ่ม Sign in |

## Phase 2 (จองไว้)

| เส้น/ฟีเจอร์ | รอ |
|------|-----|
| WebSocket log สดที่ S5-pre | ตอนนี้ใช้ poll |
| `GET /api/sessions/{id}/logs` (SSE) | log streaming |
| metering ละเอียด (cpu/gpu seconds ใน `usage_records`) | Phase 1 track แบบ wall-clock เปิด–ปิด session ไปก่อน |
