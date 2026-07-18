# Virtual Lab — Backend API Specification

> เส้น API ทั้งหมดของ FastAPI backend (Draft v1)
> คู่กับ [frontend.md](frontend.md) — ทุก endpoint ระบุว่าหน้าไหนเรียกใช้ (S0–S7, A1–A6)
> อิงกับ database schema v2 (PR #30)

## กติกากลาง

| กติกา | รายละเอียด |
|-------|-----------|
| Auth | oauth2-proxy + Google SSO กันคนนอกทั้งเว็บ — backend อ่าน identity จาก header ที่ proxy ส่งมา ไม่มี endpoint login/logout เอง |
| สิทธิ์ 2 ชั้น | `/api/admin/*` ต้อง `role='admin'` (ไม่ใช่ได้ 403) / ทุกเส้น sessions เช็ค ownership: `session.user_id` ต้องตรงกับคน login |
| Launch ไม่ block | `POST /api/sessions` ตอบ **202** ทันที งานช้า (SkyPilot) เป็น background task — frontend poll เอา (Constraint 2 ใน ARCHITECTURE.md) |
| Error format | `{detail: "..."}` ตาม exception handler ที่มีอยู่ใน backend แล้ว |
| Pagination | `limit` / `offset` เฉพาะเส้น list ที่โตได้ (sessions, admin lists) |

## 1. Identity

| Method | Path | ใช้โดยหน้า | อธิบาย |
|--------|------|-----------|--------|
| GET | `/api/me` | ทุกหน้าหลัง login | user ปัจจุบัน `{id, email, name, student_id, role}` — login ครั้งแรก auto-create user จาก SSO email |

## 2. Courses & Labs (นักศึกษา)

| Method | Path | ใช้โดยหน้า | อธิบาย |
|--------|------|-----------|--------|
| GET | `/api/courses` | S2 Courses | วิชาที่ enroll + progress สรุป `{labs_total, labs_finished, nearest_due}` |
| GET | `/api/courses/{course_id}/labs` | S3 Labwork | แลปในวิชา (เฉพาะ published) + สถานะของฉันต่อแลป |
| GET | `/api/labs/{lab_id}` | S4 Lab Instruction | รายละเอียดแลป: title, image, due_at |
| GET | `/api/labs/{lab_id}/doc` | S4 Lab Instruction | เอกสารแลป (Markdown) จาก R2 — backend แปลงลิงก์รูปเป็น presigned URL (อายุ ~1 ชม.) ก่อนส่ง + เช็คว่า user enroll วิชานี้จริง — frontend render ด้วย react-markdown |
| POST | `/api/labs/{lab_id}/finish` | S5 Lab Hub | Mark as Done — upsert `lab_progress.status='finished'` |

## 3. Sessions

| Method | Path | ใช้โดยหน้า | อธิบาย |
|--------|------|-----------|--------|
| POST | `/api/sessions` | S4 (ปุ่ม Launch) | body `{service_type, lab_id?, is_remote?}` — insert `status='pending'` + upsert `lab_progress='in_progress'` แล้วตอบ 202 `{session_id}` — background task เรียก SkyPilot ต่อ |
| GET | `/api/sessions` | S1 Console (RECENT), S7 Dashboard | session ของฉัน — query: `status=`, `limit=` (RECENT ใช้ `limit=4`) |
| GET | `/api/sessions/{id}` | S5 Lab Hub (poll ทุก 2–3 วิ) | สถานะ + `endpoints` (URL ต่อ service + ready) + `expires_at` (countdown) |
| POST | `/api/sessions/{id}/stop` | S5, S7 | หยุด session — SkyPilot down แล้ว `status='stopped'`, `ended_at=now()` |
| POST | `/api/sessions/{id}/reset` | S5 | stop + launch ใหม่จาก image เดิม — ตอบ 202 + session id ใหม่ |

## 4. Console / Dashboard aggregates

| Method | Path | ใช้โดยหน้า | อธิบาย |
|--------|------|-----------|--------|
| GET | `/api/dashboard/summary` | S1, S7 | เลขทุกการ์ดใน request เดียว `{labs_in_progress, nearest_due, compute_running, sandbox_running, quota_hours_left, storage_used_mb}` — quota คิดแบบ wall-clock (Phase 1) |
| GET | `/api/dashboard/continue` | S1 (Continue strip) | แลป `in_progress` ล่าสุด 1 รายการ |
| GET | `/api/announcements` | S1 | ประกาศ global + วิชาที่ enroll เรียงใหม่สุดก่อน (`limit` default 10) |

## 5. Admin — Courses & Labs

| Method | Path | ใช้โดยหน้า | อธิบาย |
|--------|------|-----------|--------|
| GET | `/api/admin/courses` | A2 Courses | ทุกวิชา + จำนวนสมาชิก/แลป |
| POST | `/api/admin/courses` | A2 | สร้างวิชา `{code, name, lecturer_name, banner_color}` |
| PATCH | `/api/admin/courses/{id}` | A2, A3 | แก้ไขวิชา |
| GET | `/api/admin/courses/{id}` | A3 Course Detail | รายละเอียดวิชา + แลป + สมาชิก (ก้อนเดียวสำหรับ 3 แท็บ) |
| POST | `/api/admin/courses/{id}/enrollments` | A3 แท็บ Members | bulk enroll — body `{emails: [...]}` — email ที่ยังไม่เคย login สร้างเป็น user placeholder |
| DELETE | `/api/admin/courses/{id}/enrollments/{user_id}` | A3 | เอาออกจากวิชา |
| POST | `/api/admin/courses/{id}/labs` | A3 แท็บ Labs | สร้างแลป `{title, order_no, doc_url, image_id, due_at}` |
| PATCH | `/api/admin/labs/{lab_id}` | A3 | แก้/publish แลป (`draft → published`) |

## 6. Admin — Images (Docker Upload Portal)

| Method | Path | ใช้โดยหน้า | อธิบาย |
|--------|------|-----------|--------|
| POST | `/api/images/upload-link` | Upload Portal (โมดูลเพื่อน) | ขอ upload link TTL 24h — สร้างแถว `lab_images status='pending'` |
| GET | `/api/admin/images` | A4 Images | list ตาม `status=` (default `pending` = คิวรออนุมัติ) |
| POST | `/api/admin/images/{id}/approve` | A4 | approve — ดึง digest/size จาก registry manifest API มาเก็บตอนนี้ |
| POST | `/api/admin/images/{id}/reject` | A4 | reject พร้อมเหตุผล |

## 7. Admin — Monitor / Quotas / Announcements

| Method | Path | ใช้โดยหน้า | อธิบาย |
|--------|------|-----------|--------|
| GET | `/api/admin/sessions` | A1, A5 | session ทั้งระบบ + join user/course — filter `status=`, `course_id=`, `node=` |
| POST | `/api/admin/sessions/{id}/stop` | A5 | force-stop session ของใครก็ได้ |
| GET | `/api/admin/nodes` | A1 | สถานะ node สด ๆ proxy จาก K8s API — **ไม่เก็บ DB** ตามหลัก "node health not in DB" |
| GET | `/api/admin/quotas` | A6 Quotas | quota ทั้งหมด |
| PUT | `/api/admin/quotas` | A6 | ตั้ง/แก้ `{user_id? หรือ course_id?, compute_hours_limit, storage_mb_limit, period}` |
| POST | `/api/admin/announcements` | A1, A3 แท็บ Announcements | โพสต์ `{course_id?, message}` — null = global |
| DELETE | `/api/admin/announcements/{id}` | A1, A3 | ลบประกาศ |

## 8. ตารางตรวจ Compatibility — ทุกหน้าใน frontend.md ต้องมี API ครบ

| หน้า (frontend.md) | เส้นที่ใช้ | ครบไหม |
|--------------------|-----------|--------|
| S0 Home (public) | ไม่เรียก API — static + ปุ่ม Sign in (redirect ไป oauth2-proxy) | ครบ |
| S1 Console | `/api/me`, `/api/dashboard/summary`, `/api/dashboard/continue`, `/api/sessions?limit=4`, `/api/announcements` | ครบ |
| S2 Courses | `/api/courses` | ครบ |
| S3 Labwork | `/api/courses/{id}/labs` | ครบ |
| S4 Lab Instruction | `/api/labs/{id}`, `/api/labs/{id}/doc` (markdown + รูป), `POST /api/sessions` (ปุ่ม Launch) | ครบ |
| S5 Lab Hub | `GET /api/sessions/{id}` (poll), `/stop`, `/reset`, `POST /api/labs/{id}/finish` | ครบ |
| S6 Compute Service | ไม่เรียก (placeholder) — อนาคต `POST /api/sessions` ด้วย `service_type='compute'` รองรับอยู่แล้ว | ครบ |
| S7 My Dashboard | `/api/sessions?status=running`, `/api/dashboard/summary` | ครบ |
| A1 Admin Console | `/api/admin/sessions?status=running`, `/api/admin/nodes`, `/api/admin/images?status=pending` (นับ badge), `POST /api/admin/announcements` | ครบ |
| A2 Courses | `/api/admin/courses` (GET/POST) | ครบ |
| A3 Course Detail | `/api/admin/courses/{id}` + `/labs`, `/enrollments`, announcements | ครบ |
| A4 Images | `/api/admin/images` + `/approve`, `/reject` | ครบ |
| A5 Sessions Monitor | `/api/admin/sessions`, `POST /api/admin/sessions/{id}/stop` | ครบ |
| A6 Quotas | `/api/admin/quotas` (GET/PUT) | ครบ |

## Phase 2 (จองชื่อไว้ ยังไม่ทำ)

| Path | รอเงื่อนไข |
|------|-----------|
| `GET /api/admin/costs?group_by=course` | รอ metering (`usage_records`) |
| `GET /api/sessions/{id}/logs` | log streaming (SSE) |
| workspace sync endpoints | รอตัดสินใจเรื่อง sync งานค้างขึ้น R2 |
