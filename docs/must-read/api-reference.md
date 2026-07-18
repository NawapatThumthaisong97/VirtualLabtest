# Virtual Lab — API Reference (Request / Response / Error)

> รายละเอียดราย endpoint ต่อยอดจาก [backend.md](backend.md) — ใช้เป็น contract ตอนเขียน FastAPI จริงและตอน frontend เรียกใช้
> อ้างอิง database schema v2 (docs/DB_DIAGRAM.md)

## กติกากลาง

| เรื่อง | กติกา |
|---|---|
| Base URL | `/api` (ตาม `API_PREFIX` ใน settings) |
| Auth | ทุกเส้นอยู่หลัง oauth2-proxy (Google SSO) — backend อ่าน email จาก header `X-Forwarded-Email` แล้ว map เป็น user ใน DB |
| Content-Type | `application/json` ทุก request/response |
| รูปแบบ id | UUID เช่น `"3f2b1c9e-..."` |
| เวลา | ISO 8601 UTC เช่น `"2026-07-18T14:30:00Z"` |
| Error envelope | ทุก error ตอบ `{"detail": "ข้อความ"}` (ตาม exception handler ใน `app/main.py`) |
| Pagination | เส้น list ที่โตได้ใช้ `?limit=&offset=` — default `limit=20` |

## Error codes ที่ใช้ร่วมกันทุกเส้น

| Code | ความหมาย | ตัวอย่าง detail |
|---|---|---|
| 401 | ไม่ผ่าน SSO (ปกติ proxy กันก่อนถึง backend) | `"Not authenticated"` |
| 403 | role ไม่ถึง หรือไม่ใช่เจ้าของ resource | `"Admin only"` / `"Not your session"` |
| 404 | ไม่พบ resource ตาม id | `"Session not found"` |
| 422 | body/query ไม่ผ่าน validation (FastAPI ตอบให้เอง) | รายละเอียด field ที่ผิด |
| 500 | DB/ระบบภายในพัง | `"Database error occurred"` |

> ด้านล่างเขียนเฉพาะ error **เฉพาะทาง** ของแต่ละเส้น — 401/422/500 ใช้ตามตารางนี้ทุกเส้นไม่เขียนซ้ำ

---

## 1. Identity

### GET /api/me

ข้อมูล user ปัจจุบัน — login ครั้งแรก auto-create จาก SSO email

**Request:** ไม่มี parameter

**Success 200**
```json
{
  "id": "3f2b1c9e-8a41-4b7e-9c2d-1f0a5e6b7c8d",
  "email": "peraphat@example.ac.th",
  "name": "Peraphat W.",
  "student_id": "65010123",
  "role": "student",
  "created_at": "2026-06-01T08:00:00Z"
}
```

**Error เฉพาะทาง:** ไม่มี (เส้นนี้สร้าง user ให้เสมอถ้ายังไม่มี)

---

## 2. Courses & Labs (student)

### GET /api/courses

วิชาที่ฉัน enroll + progress สรุป

**Success 200**
```json
[
  {
    "id": "c1...",
    "code": "CS217",
    "name": "Infrastructure",
    "lecturer_name": "อ.สมชาย",
    "banner_color": "#1E63D0",
    "labs_total": 4,
    "labs_finished": 3,
    "nearest_due": "2026-07-24T16:00:00Z"
  }
]
```

### GET /api/courses/{course_id}/labs

แลปในวิชา (เฉพาะ `status='published'`) + สถานะของฉัน

**Success 200**
```json
[
  {
    "id": "l1...",
    "title": "Lab 1 : Linux Network",
    "order_no": 1,
    "due_at": "2026-07-24T16:00:00Z",
    "my_status": "finished",
    "finished_at": "2026-07-10T10:12:00Z"
  },
  {
    "id": "l2...",
    "title": "Lab 2 : Linux File system",
    "order_no": 2,
    "due_at": null,
    "my_status": "in_progress",
    "finished_at": null
  }
]
```

**Error เฉพาะทาง**

| Code | เมื่อไร |
|---|---|
| 403 | ไม่ได้ enroll วิชานี้ — `"Not enrolled in this course"` |
| 404 | ไม่มี course ตาม id |

### GET /api/labs/{lab_id}

รายละเอียดแลป (หน้า Lab Instruction ส่วนหัว)

**Success 200**
```json
{
  "id": "l2...",
  "course": { "id": "c1...", "code": "CS217", "name": "Infrastructure" },
  "title": "Lab 2 : Linux File system",
  "order_no": 2,
  "due_at": null,
  "image": { "repository": "skypilot/music-lab", "tag": "lab-02" },
  "my_status": "in_progress"
}
```

**Error เฉพาะทาง:** 403 ไม่ได้ enroll / 404 ไม่พบหรือยังเป็น draft

### GET /api/labs/{lab_id}/doc

เอกสารแลป (Markdown จาก R2) — ลิงก์รูปแปลงเป็น presigned URL (อายุ ~1 ชม.)

**Success 200**
```json
{
  "markdown": "# Lab 2 : Linux File system\n\nใน lab นี้...\n\n![diagram](https://r2...presigned...)",
  "expires_at": "2026-07-18T15:30:00Z"
}
```

**Error เฉพาะทาง:** 403 ไม่ได้ enroll / 404 แลปไม่มี doc — `"This lab has no document"`

### POST /api/labs/{lab_id}/finish

Mark as Done

**Request:** ไม่มี body

**Success 200**
```json
{ "lab_id": "l2...", "status": "finished", "finished_at": "2026-07-18T14:45:00Z" }
```

**Error เฉพาะทาง**

| Code | เมื่อไร |
|---|---|
| 403 | ไม่ได้ enroll วิชาของแลปนี้ |
| 409 | แลป finished อยู่แล้ว — `"Lab already finished"` (idempotent: ตอบ 409 หรือเลือกตอบ 200 ค่าเดิมก็ได้ — **ทีมต้องเคาะ**) |

---

## 3. Sessions

### POST /api/sessions

Launch — สร้าง session ใหม่ (ตอบทันที ไม่รอ SkyPilot ตาม Constraint 2)

**Request body**
```json
{
  "service_type": "lab",        // "lab" | "compute" | "sandbox" | "ai_job"
  "lab_id": "l2...",            // จำเป็นเมื่อ service_type = "lab", อื่น ๆ = null
  "is_remote": false
}
```

**Success 202** (Accepted — งานเข้าคิวแล้ว ยังไม่ running)
```json
{
  "session_id": "s9...",
  "status": "pending",
  "poll": "/api/sessions/s9..."
}
```

**Error เฉพาะทาง**

| Code | เมื่อไร |
|---|---|
| 403 | เปิดแลปของวิชาที่ไม่ได้ enroll |
| 404 | lab_id ไม่มีจริง/ยัง draft |
| 409 | มี session ของแลปนี้ยังไม่จบอยู่แล้ว (โดน partial unique index) — `"A live session for this lab already exists"` + คืน `session_id` เดิมให้ frontend พาไปต่อ |
| 402 หรือ 429 | quota ชั่วโมงหมด — `"Compute quota exceeded"` (**ทีมต้องเคาะ code — เสนอ 429**) |

### GET /api/sessions

session ของฉัน — query: `?status=running` `?limit=4` `?offset=0`

**Success 200**
```json
[
  {
    "id": "s9...",
    "service_type": "lab",
    "lab": { "id": "l2...", "title": "Lab 2 : Linux File system", "course_code": "CS217" },
    "status": "running",
    "is_cloud": false,
    "started_at": "2026-07-18T12:30:00Z",
    "ended_at": null,
    "uptime_seconds": 8100
  }
]
```

### GET /api/sessions/{id}

รายละเอียด + endpoints — **Lab Hub poll เส้นนี้ทุก 2–3 วิ**

**Success 200**
```json
{
  "id": "s9...",
  "status": "running",          // pending | provisioning | running | stopped | succeeded | failed
  "lab_id": "l2...",
  "node_name": "worker-1",
  "is_cloud": false,
  "endpoints": {
    "ide":    { "url": "https://lab-s9.bell-lab.space/ide",    "ready": true },
    "client": { "url": "https://lab-s9.bell-lab.space/client", "ready": true },
    "ssh":    { "url": "ssh://100.x.x.x:2222",                  "ready": false }
  },
  "started_at": "2026-07-18T12:30:00Z",
  "expires_at": "2026-07-18T16:30:00Z"
}
```

> กติกา frontend: render ลิงก์ใน `endpoints` เฉพาะเมื่อ `status == "running"`

**Error เฉพาะทาง:** 403 ไม่ใช่ session ของฉัน / 404 ไม่พบ

### POST /api/sessions/{id}/stop

**Request:** ไม่มี body

**Success 200**
```json
{ "id": "s9...", "status": "stopped", "ended_at": "2026-07-18T15:00:00Z" }
```

**Error เฉพาะทาง**

| Code | เมื่อไร |
|---|---|
| 403 | ไม่ใช่เจ้าของ |
| 409 | session จบไปแล้ว — `"Session already ended"` |

### POST /api/sessions/{id}/reset

stop ตัวเดิม + launch ตัวใหม่จาก image เดิม

**Success 202**
```json
{ "old_session_id": "s9...", "session_id": "sA...", "status": "pending" }
```

**Error เฉพาะทาง:** เหมือน stop + เหมือน launch (409 ซ้อน, quota)

---

## 4. Console / Dashboard

### GET /api/dashboard/summary

**Success 200**
```json
{
  "labs_in_progress": 2,
  "nearest_due": { "lab_title": "Lab 3 : Docker", "due_at": "2026-07-24T16:00:00Z" },
  "compute_running": 0,
  "sandbox_running": 1,
  "quota_hours_limit": 20.0,
  "quota_hours_used": 13.5,
  "storage_mb_limit": 2048,
  "storage_mb_used": 1638
}
```

### GET /api/dashboard/continue

**Success 200** — มีแลปค้าง
```json
{
  "lab": { "id": "l2...", "title": "Lab 2 : Linux File system", "course_code": "CS217" },
  "updated_at": "2026-07-18T12:30:00Z",
  "due_at": "2026-07-24T16:00:00Z",
  "live_session_id": "s9..."   // null ถ้าไม่มี session รันอยู่
}
```

**Success 204** — ไม่มีแลปค้าง (frontend ซ่อน ContinueStrip)

### GET /api/announcements

query: `?limit=10`

**Success 200**
```json
[
  {
    "id": "a1...",
    "scope": "course",
    "course_code": "CS217",
    "message": "Lab 3 เลื่อน due เป็นศุกร์หน้า",
    "author_name": "Admin Team",
    "created_at": "2026-07-16T09:00:00Z"
  },
  { "id": "a2...", "scope": "global", "course_code": null, "message": "...", "author_name": "...", "created_at": "..." }
]
```

---

## 5. Admin — ทุกเส้นต้อง `role='admin'` (ไม่งั้น 403)

### GET /api/admin/courses
**Success 200:** list ทุกวิชา + `{ "members": 42, "labs": 4 }`

### POST /api/admin/courses
**Request**
```json
{ "code": "CS217", "name": "Infrastructure", "lecturer_name": "อ.สมชาย", "banner_color": "#1E63D0" }
```
**Success 201:** course ที่สร้าง (id ครบ)
**Error:** 409 `code` ซ้ำ — `"Course code already exists"`

### PATCH /api/admin/courses/{id}
**Request:** field ที่จะแก้ (บางส่วนได้) — **Success 200** ค่าใหม่ — **Error:** 404 / 409 code ซ้ำ

### GET /api/admin/courses/{id}
**Success 200:** รายละเอียด + `labs[]` (รวม draft) + `members[]` — ก้อนเดียวสำหรับ 3 แท็บของหน้า Course Detail

### POST /api/admin/courses/{id}/enrollments
**Request**
```json
{ "emails": ["a@example.ac.th", "b@example.ac.th"] }
```
**Success 200**
```json
{ "enrolled": 2, "already_enrolled": 0, "created_users": 1 }
```
**Error:** 404 course / 422 email format ผิด

### DELETE /api/admin/courses/{id}/enrollments/{user_id}
**Success 204** (ไม่มี body) — **Error:** 404 ไม่ได้เป็นสมาชิก

### POST /api/admin/courses/{id}/labs
**Request**
```json
{ "title": "Lab 3 : Docker", "order_no": 3, "doc_url": "labs/l3/instruction.md", "image_id": "img1...", "due_at": "2026-07-24T16:00:00Z" }
```
**Success 201** — **Error:** 409 `order_no` ซ้ำในวิชา / 422 `image_id` ยังไม่ approved — `"Image not approved"`

### PATCH /api/admin/labs/{lab_id}
แก้ field ใด ๆ รวมทั้ง publish: `{ "status": "published" }`
**Error:** 422 publish โดยไม่มี image/doc — `"Cannot publish lab without image"`

### POST /api/images/upload-link
(instructor/admin — Docker Upload Portal)
**Request:** `{ "course_id": "c1...", "repository": "skypilot/cs217-lab3" }`
**Success 201**
```json
{ "image_id": "img2...", "upload_link": "https://...", "expires_at": "2026-07-19T14:00:00Z" }
```

### GET /api/admin/images?status=pending
**Success 200:** list `{ id, repository, tag, size_mb, uploaded_by_name, course_code, created_at }`

### POST /api/admin/images/{id}/approve
**Success 200:** `{ "id": "img2...", "status": "approved", "image_digest": "sha256:...", "size_mb": 812 }`
**Error:** 409 ไม่ได้อยู่สถานะ pending / 502 ติดต่อ registry ไม่ได้ — `"Registry unreachable"`

### POST /api/admin/images/{id}/reject
**Request:** `{ "reason": "image ใหญ่เกิน ไม่ได้ pin เวอร์ชัน" }` — **Success 200** — **Error:** 409 ไม่ pending

### GET /api/admin/sessions
query: `?status=` `?course_id=` `?node=` `?limit=&offset=`
**Success 200:** เหมือน GET /api/sessions + `user: { id, name, student_id }`

### POST /api/admin/sessions/{id}/stop
force-stop ของใครก็ได้ — **Success 200** เหมือน stop ปกติ — **Error:** 409 จบแล้ว

### GET /api/admin/nodes
สถานะ node สดจาก K8s API (ไม่เก็บ DB)
**Success 200**
```json
[
  { "name": "thinkpad", "ready": true, "cpu_percent": 41, "memory_percent": 63, "pods": 7 },
  { "name": "worker-1", "ready": true, "cpu_percent": 78, "memory_percent": 71, "pods": 5 }
]
```
**Error:** 502 K8s API ไม่ตอบ — `"Cluster API unreachable"`

### GET /api/admin/quotas · PUT /api/admin/quotas
**PUT Request** (upsert)
```json
{ "course_id": "c1...", "user_id": null, "compute_hours_limit": 20, "storage_mb_limit": 2048, "period": "semester" }
```
**Success 200** — **Error:** 422 user_id และ course_id เป็น null ทั้งคู่ — `"Must target a user or a course"`

### POST /api/admin/announcements
**Request:** `{ "course_id": null, "message": "ระบบปิดปรับปรุงคืนนี้ 22:00" }` (`course_id: null` = global)
**Success 201** — **DELETE /api/admin/announcements/{id}** → **204** / 404

---

## จุดที่ทีมต้องเคาะ (ตัดสินใจแล้วลบ section นี้)

| ประเด็น | ตัวเลือก | ข้อเสนอ |
|---|---|---|
| กด finish ซ้ำ | 409 หรือ 200 ค่าเดิม (idempotent) | 200 ค่าเดิม — ง่ายกับ frontend |
| quota หมดตอน launch | 402 / 429 / 403 | 429 + detail บอกชั่วโมงที่เหลือ |
| rate limit launch | มี/ไม่มีใน Phase 1 | 10 ครั้ง/ชม./คน ผ่าน slowapi in-memory |
