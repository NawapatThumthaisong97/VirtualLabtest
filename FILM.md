# Phase 1: ขั้นตอนย่อย

แต่ละขั้นทำเสร็จได้ในรอบเดียว และมีวิธีเช็กว่าผ่านแล้ว
ขั้นที่ทำคู่กันได้ทำเครื่องหมาย ∥ ไว้ (อ้างอิงรายละเอียดใน [docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md](docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md))

**ลำดับที่แนะนำ:** `A1–A10` ∥ `C1` → `B` → (`D` ∥ `C2–C6`) → `E` → `F`

---

## ส่วน A: โค้ด backend

> dev ทำบน PC, ยังไม่แตะ prod

| ✔ | ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|---|
| ☑ | A1 | ใช้ branch `feature/aws-dns` ทำทั้งหมด (ไม่แตก branch ใหม่) | อยู่บน `feature/aws-dns` |
| ☑ | A2 | `settings.py`: เพิ่มตัวแปร `LAB_GATEWAY_*` + validator | backend start ได้ตอน flag ปิด / เปิด flag แต่ไม่มี token ต้อง start ไม่ขึ้น |
| ☑ | A3 | model: เพิ่ม `gateway_token` และ `upstreams` + สร้าง migration | `alembic upgrade head` แล้ว `downgrade -1` บน DB local ผ่านทั้งสองทาง |
| ☑ | A4 | `lab_gateway_service.py`: ฟังก์ชันช่วย (token, ลิงก์, เช็ก upstream) | unit test ของฟังก์ชันพวกนี้ผ่าน |
| ☑ | A5 | `build_routes()` สร้างตาราง route | session RUNNING อยู่ในตาราง ส่วน PENDING / STOPPED / IP นอก ไม่อยู่ |
| ☐ | A6 | route `/internal/v1/gateway/routes` + ลงทะเบียน | `curl` local: ไม่มี token ได้ 404, มี token ถูกได้ JSON |
| ☐ | A7 | `session_service.py`: ส่ง token ไหลจาก `_new_sky_session` → `create_fastapi_task` → `_build_aws_task` (env) | `docker run` มี `-e VLAB_PUBLIC_URL_...` ส่วน K8s ไม่มี |
| ☐ | A8 | `_run_sky_launch`: แยก `endpoints` (ลิงก์ `l-...`) กับ `upstreams` (`10.10.2.x`) | endpoint เป็น `https://l-...` และ API ของ sessions ไม่คืน `upstreams` |
| ☐ | A9 | `main.py`: ซ่อน 2 column ในหน้า admin | เปิดหน้า admin local แล้วไม่เห็น 2 column นี้ |
| ☐ | A10 | รัน test ทั้งหมด `pytest tests/session` | test เก่าไม่พัง + test ใหม่ผ่าน → เปิด **PR 1** |

> **หมายเหตุ A1:** ตัดสินใจทำทุกส่วนของ Phase 1 บน `feature/aws-dns` (2026-11-11) แทนการแยก PR 1–4 ตาม runbook ข้อ 7
> ยัง merge ได้อย่างปลอดภัยเพราะทุกอย่างอยู่หลัง flag `LAB_GATEWAY_ENABLED=false`

---

## ส่วน B: Ansible ฝั่ง web-service

> dev ทำ

| ✔ | ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|---|
| ☐ | B1 | เพิ่มตัวแปรใน `web-service/defaults` + `backend.env.j2` + `all.yml.example` | `--check --diff` เห็นแค่ `.env` เปลี่ยน |
| ☐ | B2 | สุ่ม `vault_lab_gateway_token` แล้วใส่ใน `group_vars/all.yml` | มีค่ายาว ≥ 32 ตัวอักษร |
| ☐ | B3 | merge PR 1 + 2 แล้ว deploy ลง `vlab-web` โดย **flag ปิด** (แจ้งทีมก่อน) | `curl` ได้ 404 และกด Start AWS ยังได้ `10.10.2.x` |

---

## ส่วน C: เตรียม infra (Phase 0) ∥

> ทำคู่กับส่วน A ได้

| ✔ | ขั้น | ทำอะไร | ใคร |
|---|---|---|---|
| ☐ | C1 | ดู record `*.bell-lab.space` ใน Cloudflare แล้วจดค่าเดิม | คุณ |
| ☐ | C2 | ยืนยันกับ Pete ว่า backend อยู่ที่ `vlab-web` และตอบคำถามที่ค้างในข้อ 0.1 | คุณ + Pete |
| ☐ | C3 | จดค่าทั้ง 5 ตัวในข้อ 0.2 (IP, instance ID, SG ID) | Pete |
| ☐ | C4 | เก็บสถานะ router ผ่าน SSM (ข้อ 0.3) | Pete |
| ☐ | C5 | สร้าง AMI snapshot ของ router | Pete |
| ☐ | C6 | เทส baseline: กด Start AWS แล้วจดเวลา | dev |

---

## ส่วน D: Cloudflare ∥

> คุณทำ — เริ่มได้หลังจบ C1

| ✔ | ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|---|
| ☐ | D1 | สร้าง tunnel `vlab-lab-gateway` แล้วเก็บ token ลง `all.yml` | tunnel ขึ้นใน dashboard |
| ☐ | D2 | ตั้ง public hostname `*` → `127.0.0.1:8081` + แก้ DNS `*` ให้ชี้ tunnel | `curl l-test-8080...` เปลี่ยนจาก 521 เป็น **1033** |
| ☐ | D3 | Cache Rule + Configuration Rule สำหรับ `l-*` | มี rule ขึ้นใน dashboard |
| ☐ | D4 | เช็ก `skypilot.bell-lab.space` ยังใช้งานได้ | เปิดได้เหมือนเดิม |

---

## ส่วน E: Router

> ทำกับ Pete ช่วงที่ไม่มีคาบ **ต้องทำตามลำดับ**

| ✔ | ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|---|
| ☐ | E1 | Terraform: แก้ `router.tf` + `security_groups.tf` แล้ว `plan` | plan ขึ้น **update in-place** (ถ้าขึ้น replace ให้หยุด) |
| ☐ | E2 | `terraform apply` + ลบ rule 5173 / 8443 ที่เคยเพิ่มด้วยมือ | R1–R3 ผ่าน และ plan รอบสองขึ้น `No changes` |
| ☐ | E3 | Tailscale: แก้ไฟล์ tag + ACL แล้ว `plan` / `apply` | router มี tag, route ยัง approved, R1–R3 ผ่าน |
| ☐ | E4 | ใส่ SSH key ให้ router + เพิ่ม `aws_router` ใน inventory | `ansible aws_router -m ping` ผ่าน |
| ☐ | E5 | เขียน role `lab-gateway` (ปักเลข version + sha256) | `--check --diff` ผ่าน |
| ☐ | E6 | รัน role จริง | tunnel **Healthy**, RAM เหลือ ≥ 800MB, R1–R4 ผ่าน |

---

## ส่วน F: เปิดใช้งาน

| ✔ | ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|---|
| ☐ | F1 | เช็ก Vite ใน image music-lab (ข้อ 1F.0) | รองรับ env — ถ้าไม่รองรับต้องแก้ `vite.config.js` แล้ว build ใหม่ |
| ☐ | F2 | เปิด flag ด้วย `-e webservice_lab_gateway_enabled=true` | `curl` ตาราง route ได้ `{"routers":{}}` |
| ☐ | F3 | กด Start AWS แล้วเปิดลิงก์ `l-...` บนมือถือ 4G | เปิด lab ได้ |
| ☐ | F4 | เทส G1–G12 แล้วจดผลลงข้อ 9 | G1–G11 ผ่าน → ตั้ง flag เป็น `true` ถาวร |
