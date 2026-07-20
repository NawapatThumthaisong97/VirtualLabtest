# Virtual Lab — Full-stack Map (หน้า × API × redirect)

> สกัดจากโน้ตลายมือของ Pete (2026-07-21) — ไฟล์นี้เขียนเพื่อแยกส่วนให้เห็นครบวงจร:
> **frontend ของ user** / **backend API** / **ตาราง compatibility** ว่าแต่ละหน้า required API เส้นไหน แล้ว redirect ไปไหนต่อ

## หลักการฝั่ง Frontend

- ทุกหน้าในตารางคือ **redirectable page** — หน้าที่มี URL ของตัวเอง กระโดดถึงกันได้ทั้งหมดที่เราต้องใช้
- **เรียกหน้าด้วยชื่อ ไม่เรียกด้วย path** — เช่นเรียกว่าหน้า "Lab instruction" แทน `course/{id}/lab/{id}` เพราะ API GET ทำงานได้เหมือนกันอยู่แล้ว แต่ชื่อหน้าทำให้ทีมคุยกันเข้าใจ
- บางหน้า**ยังไม่ทำ** เช่น Dashboard — เพราะยังไม่รู้จะใส่ข้อมูลอะไร รอข้อมูลจริงก่อน

## Client-side pages

| # | หน้า | หน้าที่ |
|---|------|---------|
| S1 | **Console** | หน้าที่ใช้สำหรับดู service ต่าง ๆ และ announcement |
| S2 | **Course** | รายละเอียด course ที่ทำการ enrolled ไว้แล้ว |
| S3 | **Course detail** | รายละเอียดเชิงลึกของแต่ละ course ว่าเป็นยังไงบ้าง และ lab list ที่สามารถทำได้ |
| S4 | **Course lab instruction** | หน้าแลปของเรา — เอา markdown file ไว้อ่าน |
| S5-pre | **Session Loading** | หน้า load เพื่อรอ launching instance |
| S5 | **Session** | หน้าแสดง link ไปยัง IDE หรือ client web ที่เรากดสร้างไว้ |
| S6 | **Login** | ยังไม่สรุป (ดูข้อสังเกตท้ายไฟล์) |

## ตาราง Compatibility (หน้า × API × redirect)

| หน้า | API ที่ต้องใช้ | redirect ไป |
|------|---------------|-------------|
| S1 Console | `GET /api/sessions?status=running` · `GET /api/announcements?limit=4` · `GET /api/me` | → S2 Course · → S7 Compute service *(not yet)* |
| S2 Course | `GET /api/courses` | → S3 Course detail (`/api/courses/{id}`) |
| S3 Course detail | `GET /api/courses/{id}/docs` · `GET /api/courses/{id}/announcements` · `GET /api/courses/{id}/labs` | → S4 Course lab instruction |
| S4 Lab instruction | `GET /api/courses/{id}/labs/{id}` · `POST /api/sessions` | → S5-pre Session loading |
| S5-pre Session loading | WebSocket (ดึง log สด) | ไม่ redirect — รอจน instance พร้อมแล้วเข้า S5 |
| S5 Session | `GET /api/sessions/{id}` (poll ทุก ๆ X วิ เพื่อฟังจนกว่าจะเสร็จ) · `PATCH /api/sessions/{id}` (เปลี่ยนสถานะ เช่น stop lab) | → กลับ S4 Lab instruction · → IDE / web portal (ลิงก์ที่สร้าง) |
| S6 Login | unknown | unknown |

## ข้อสังเกต: จุดที่ต่างจาก spec เดิม (ทีมต้องเคาะ)

> ลายมือต้นฉบับเขียน API แบบย่อ ในตารางข้างบนปรับชื่อ path ให้ตรงกับ
> [api-reference.md](api-reference.md) แล้ว (เช่น `/api/session` → `/api/sessions`)
> ส่วนที่**ขัดกันจริง**กับ spec เดิม แยกไว้ให้เคาะทีละข้อ:

| # | ประเด็น | โน้ตนี้ | spec เดิม | ต้องตัดสินใจ |
|---|---------|---------|-----------|---------------|
| 1 | เลขหน้า | S2 Course / S3 Course detail / S5-pre / S5 Session | S2 Courses / S3 Labwork / S5 Lab Hub (ไม่มี S5-pre) | ใช้ชุดไหนเป็นทางการ — เสนอใช้ชุดใหม่นี้ + อัปเดต frontend.md |
| 2 | หน้า Session Loading (S5-pre) | แยกเป็นหน้าของตัวเอง | รวมอยู่ใน Lab Hub (โชว์สถานะ provisioning) | เสนอแยกตามโน้ต — สถานะ "รอเครื่อง" มีอย่างเดียวที่ user ทำได้คือรอ แยกหน้าทำให้เขียนง่ายขึ้น |
| 3 | S5-pre ใช้ WebSocket ดึง log สด | WebSocket | spec เดิมใช้ polling (log streaming เป็น Phase 2 แบบ SSE) | WebSocket ต้องมี infra เพิ่ม (ผ่าน Cloudflare Tunnel ได้แต่ต้อง config) — เสนอ Phase 1 ใช้ poll `GET /api/sessions/{id}` ทุก 2–3 วิ ไปก่อน แล้วค่อยอัปเกรด |
| 4 | หยุด lab ด้วย `PATCH /api/sessions/{id}` | PATCH เปลี่ยน status | `POST /api/sessions/{id}/stop` | ความหมายเท่ากัน — เสนอคง POST /stop ตาม api-reference (action ชัดกว่า และกัน frontend ส่ง status มั่ว) |
| 5 | ประกาศราย course: `GET /api/courses/{id}/announcements` | แยกเส้นต่อวิชา | รวมที่ `GET /api/announcements` (global + ทุกวิชาที่ enroll) | หน้า S3 อยากโชว์เฉพาะของวิชานั้น — เสนอเพิ่มเส้นนี้ใน api-reference (query จาก table announcements ได้เลย ไม่แตะ schema) |
| 6 | `GET /api/courses/{id}/docs` ที่หน้า S3 | มี | เดิม doc อยู่ระดับแลป: `GET /api/labs/{id}/doc` | ต้องชัดว่า S3 ต้องการเอกสารระดับวิชา (syllabus?) หรือแค่ list แลป — ถ้าอย่างหลังใช้ `GET /api/courses/{id}/labs` พอ |
| 7 | หน้า S6 Login | unknown | ไม่มีหน้า login — oauth2-proxy + Google SSO redirect ให้เอง (ARCHITECTURE.md) | ถ้าคง SSO ตามสถาปัตยกรรม S6 อาจเหลือแค่หน้า Home (public) ที่มีปุ่ม Sign in |
| 8 | Dashboard | ยังไม่ทำ รอข้อมูลจริง | เป็นแท็บใน Console (ยุบ S7 แล้ว) | โอเคตามโน้ต — เลื่อนไปหลังมี session จริงในระบบ |
