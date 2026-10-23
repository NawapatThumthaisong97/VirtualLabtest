# Launch Test — โปรแกรม text เรียก curl เทสการเปิด lab

สถานะ: **ทำแล้ว** (2026-10-20) `script/launch-test.sh` ข้อความบนจอเป็นภาษาอังกฤษ — แบบแรก (Python คุม pod / DB เอง) ยกเลิกแล้ว

## ทำไม
อยากกดเลือกแล้วดูผลการเปิด lab แบบที่เทสกันมือ (POST แล้วรอ → ได้ endpoint → ลบ) โดยไม่ต้องพิมพ์ curl ยาว ๆ เอง
โปรแกรม**แค่เรียก API ของ backend ด้วย curl** ไม่สร้าง pod / ไม่แก้ DB / ไม่เรียก kubectl, AWS, SkyPilot ตรง

## หน้าจอ
```
Virtual Lab : Launch Test ---------------------------------------------------
 Backend : active | Sky : active | Registry : active | Worker : 2/3 ready
 User : Sophia Davis | Backend : http://100.93.121.17:8000
-----------------------------------------------------------------------------
 1) Start lab K8s   2) Start lab AWS   3) Warm pods   4) Sessions   5) Terminate   r) Refresh   q) ออก
=> 1
POST /api/sessions  lab : OOP with Spring Boot (K8s)
⠼ รอ backend ... 01:47
✅ สำเร็จ 151s   mode : skypilot   cluster : music-lab-1792423833
   8443  http://10.42.2.200:8443
   5173  http://10.42.2.200:5173
   session : a0b5b34d-ab47-4707-b3f9-3bd88b23e116
=> 5
 1) a0b5b34d  RUNNING  skypilot  music-lab-1792423833
เลือก session (all = ทุกตัว): 1
DELETE /api/sessions/a0b5b34d…  ✅ Session stopped and deleted successfully (11s)
```
- สีเขียวที่หัวข้อ / ผลสำเร็จ / spinner, แดงที่ error, จาง ๆ ที่รายละเอียด
- ระหว่างรอ POST (2–4 นาที) แสดง spinner + เวลาที่ผ่านไป (curl รันเบื้องหลัง)

## เมนูเรียกอะไร
| เมนู | curl |
|---|---|
| แถบสถานะ / r | `GET /health`, `GET /api/kubernetes/nodes` (worker ready), `GET <sky>/api/health`, `GET <registry>/v2/` |
| 1 Start K8s | `POST /api/sessions {lab_id: lab K8s, user_id}` |
| 2 Start AWS | `POST /api/sessions {lab_id: lab AWS, user_id}` |
| 3 Start AUTO | `POST /api/sessions {lab_id: lab AUTO, user_id}` — ไปไหนขึ้นกับเครื่องที่รัน script (ดู docs/RUN_TARGET_AUTO.md) |
| 4 Warm pods | `GET /api/warm-pods` → ตาราง เครื่อง / ว่าง-ใช้อยู่ / ready |
| 5 Sessions | `GET /api/sessions` → เฉพาะของ user ที่ RUNNING / PENDING |
| 6 Terminate | `GET /api/sessions` ให้เลือก → `DELETE /api/sessions/{id}` |
| 7 Scheduler | `GET /api/prewarm/schedule` (ใหม่) + `GET /api/prewarm` + `GET /api/warm-pods` → scheduler เปิดไหม / ทุกกี่วิ / เริ่มก่อนคาบกี่นาที, คาบถัดไปพร้อมเวลาเริ่ม pre-pull + warm pod (นับถอยหลัง), ของที่มีตอนนี้ — `w` = live ทุก 5 วิ |

## ไฟล์ / การตั้งค่า
- `script/launch-test.sh` (bash + curl + jq แบบเดียวกับ `script/tailscale-acl.sh`)
- ค่าข้างบนไฟล์ แก้ด้วย env ได้: `BACKEND_URL` (ค่าเริ่มต้น `http://127.0.0.1:8000`), `USER_ID` (Sophia),
  `LAB_K8S` (OOP with Spring Boot), `LAB_AWS`, `SKY_URL` (`http://100.125.244.48:30880`), `REGISTRY` (`100.127.74.48:5001`)
- ใช้แค่ curl + jq → copy ไปรันบนเครื่อง worker ได้ (backend จะเห็น IP เครื่องนั้น = เหมือนนักศึกษากดจากเครื่องแลป
  ได้ warm pod / pin เครื่อง) ถ้ารันบน ThinkPad ด้วย `127.0.0.1` = ไม่ผูกกับเครื่องไหน

## API ใหม่: `GET /api/prewarm/schedule?limit=10`
ดูอย่างเดียว ใช้เงื่อนไขเดียวกับ scheduler (`build_schedule` ใน `app/services/prewarm_scheduler.py`)
คืน `enabled`, `interval_seconds`, `lead_minutes`, `warm_pod_enabled`, `now`,
`slots[]` (คาบ KUBERNETES ที่ยังไม่จบ: `starts_at`, `ends_at`, `prewarm_at = starts_at - lead`, `status`, `active`)
และ `targets[]` (PREWARM_TARGETS ที่ยังไม่หมดเวลา)

## ต้องมีก่อน (ทำครั้งเดียว ไม่ใช่งานของโปรแกรม)
- lab AWS: backend ไม่มี API ตั้ง `run_target` จึงต้องสร้างใน DB ครั้งเดียว — lab **"OOP with Spring Boot (AWS)"**
  ใช้ image music-lab เดิม `run_target = AWS` — สร้างแล้ว 2026-10-20 (`536989c2-52d1-4169-b23a-ed06247cdb57`)
- backend รันด้วย `AWS_PROFILE=skypilot` (ไม่งั้นขอ ECR token ด้วย root)
- warm pod จะมีก็ต่อเมื่อมีคาบเรียน (class slot) — โปรแกรมแค่ดู ไม่สร้างคาบ

## นอกขอบเขต
- สร้าง / ลบคาบเรียน, เช็ก isolation จากเครื่องอื่น, ดู EC2 — ทำมือหรือเพิ่มทีหลัง
