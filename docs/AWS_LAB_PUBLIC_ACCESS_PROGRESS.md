# บันทึกความคืบหน้า: เปิด lab บน AWS ให้คนนอก tailnet ใช้ได้

> ทำตาม [AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md](AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md) — doc นี้จดว่า **ทำอะไรไปแล้ว ตัดสินใจอะไร เจออะไรระหว่างทาง**
> เขียนต่อท้ายทุกครั้งที่จบขั้น ห้ามแก้ของเก่า (ถ้าเปลี่ยนใจให้เขียนบันทึกใหม่ว่าเปลี่ยนเพราะอะไร)
> branch: `feature/aws-dns`

---

## สถานะล่าสุด

| ส่วน | ขั้น | สถานะ |
|---|---|---|
| A: โค้ด backend | A1 ✅ A2 ✅ A3 ✅ A4 ✅ / A5–A10 ⏳ | กำลังทำ — ถัดไป **A5** |
| B: Ansible web-service | B1–B3 | ยังไม่เริ่ม |
| C: เตรียม infra (Phase 0) | C1–C6 | ยังไม่เริ่ม |
| D: Cloudflare | D1–D4 | ยังไม่เริ่ม |
| E: Router | E1–E6 | ยังไม่เริ่ม |
| F: เปิดใช้งาน | F1–F4 | ยังไม่เริ่ม |
| เฟส 2 (portal public) | 2A–2G | **พักไว้** ทำหลังเฟส 1 เสร็จ |

ความหมายของแต่ละขั้น A–F ดูหัวข้อ "แผนขั้นย่อยของเฟส 1" ท้าย doc

---

## ภาพรวม: เฟส 1 กับเฟส 2 ต่างกันยังไง

นักศึกษาใช้ lab มี 2 จังหวะ ตอนนี้ทั้งคู่ใช้ได้เฉพาะคนที่อยู่ใน Tailscale

| | เฟส 1 (lab gateway) | เฟส 2 (portal public) |
|---|---|---|
| แก้จังหวะไหน | **เปิดหน้า lab** ที่รันบน AWS | **เข้าเว็บ portal** เพื่อ login / กด Start |
| ก่อน | `http://10.10.2.14:8443` (IP ภายใน AWS) | `http://100.102.72.39` (Tailscale IP) |
| หลัง | `https://l-<token>-8443.bell-lab.space` | `https://vlab.bell-lab.space` |
| ทำที่ไหน | router บน AWS (`vlab-ts-router`) + backend | VM `vlab-web` (nginx, frontend, backend) |

ทำเฟส 1 ก่อน เพราะถ้ามีแค่เฟส 2 นักศึกษากด Start จากบ้านได้ แต่ลิงก์ที่ได้ยังเป็น `10.10.2.x` ซึ่งเปิดไม่ได้

### เส้นทางของ traffic ในเฟส 1

```
มือถือ ──> Cloudflare ──> cloudflared ──> Traefik (บน vlab-ts-router)
                                              │  ① ทุก 5 วิ: "token ไหน = เครื่องไหน?"
                                              ▼
                                         backend บน vlab-web :8000  (ผ่าน tailnet)
                                              │  ② ตอบตาราง route จาก DB
                                              ▼
                                   Traefik ส่ง traffic ต่อไป 10.10.2.x:<port>
```

การกด Start ไม่เปลี่ยน (backend → SkyPilot → AWS เหมือนเดิม) ของใหม่คือทาง ① ที่ **router วิ่งกลับมาถาม backend**

---

## การตัดสินใจ

| วันที่ | เรื่อง | ตัดสินใจ | เหตุผล |
|---|---|---|---|
| 2026-11-09 | ใช้ router ตัวไหน | ทางเลือก A: ใช้ `vlab-ts-router` เดิม (Pete อนุมัติ) | ดู [AWS_LAB_PUBLIC_ACCESS.md](AWS_LAB_PUBLIC_ACCESS.md) |
| 2026-11-10 | ลำดับงาน | ทำเฟส 1 ให้เสร็จก่อน เฟส 2 พักไว้ | เฟส 1 ใช้ได้ทันทีและเทสง่ากว่า (คนในทีมกด Start แล้วส่งลิงก์ให้เปิดบนมือถือได้) |
| 2026-11-10 | เทส backend ที่ไหน | เขียนโค้ด + unit test บน PC แล้ว **deploy ลง `vlab-web`** (flag ปิด) เพื่อเทสกับ router | ถ้าใช้ backend บน PC: Traefik บน router ต้องเข้า PC ผ่าน tailnet (ACL, listen `0.0.0.0`, firewall, override URL) และ gateway ตายเมื่อปิด PC — runbook ออกแบบให้ใช้ `vlab-web` อยู่แล้ว |
| 2026-11-10 | portal อยู่ใน K8s หรือนอก cluster | **อยู่นอก cluster แบบเดิม** (docker compose บน VM) แต่ควรย้ายไปเครื่องที่เปิดตลอดก่อนใช้สอนจริง | (1) ใน K8s IP จริงของคนกดหายหลัง Service/kube-proxy → ระบบแยกห้องแลป/ข้างนอกพัง (ปัญหาเดียวกับ D4) (2) worker = เครื่องในห้องแลป นักศึกษาปิดได้ (3) cluster พัง ตัวควบคุมก็พังด้วย (4) compose ง่ายกว่าสำหรับทีมเล็ก |
| 2026-11-11 | branch | ทำทุกอย่างบน `feature/aws-dns` ไม่แยก PR 1–4 ตาม runbook ข้อ 7 | ชื่อ branch ตรงกับงาน docs กับโค้ดอยู่ PR เดียวกัน ยังปลอดภัยเพราะทุกอย่างอยู่หลัง flag |
| 2026-11-11 | 2 docs ออกแบบเดิม | **เก็บไว้** ไม่ลบ ใช้ runbook เป็นตัวหลัก | runbook ยังอ้างถึง: ตารางเทส G1–G12 (`AWS_LAB_GATEWAY_ROUTER.md` 7.2), ตารางเทสเฟส 2 (`AWS_LAB_PUBLIC_ACCESS.md` 8), เหตุผลของการตัดสินใจ |

---

## บันทึกการทำงาน

### 2026-11-10 — ทำความเข้าใจ + เตรียม

- อ่าน runbook แล้วแบ่งเฟส 1 เป็นขั้นย่อย A–F (ท้าย doc)
- ยืนยันจากโค้ด Ansible ว่า **`vlab-web` อยู่นอก K8s cluster**
  - `ansible/site.yml` group `webservice` ลงแค่ `common`, `tailscale`, `web-service` (ไม่มี role k3s)
  - role `web-service` รัน `docker compose -f docker-compose.prod.yml up -d --build` (backend + frontend + Postgres)
  - ดึง `kubeconfig` จาก master มาให้ backend เป็น client ของ cluster
  - `k8s/auth/06-backend-deployment.yaml` เป็น design เก่า (Issue #81) ไม่ได้ deploy
- เช็กว่าฟังก์ชันที่ runbook อ้างใน `session_service.py` ยังอยู่บรรทัดตามที่เขียน (160 / 231 / 450 / 499)

### 2026-11-10 — วิธีรัน test

- Python บน Windows (miniconda) รัน test ไม่ได้: `module 'sky' has no attribute '__commit__'` ตอนโหลด `conftest.py`
- **ใช้ WSL แทน:**
  ```bash
  wsl -d Ubuntu-24.04
  cd /mnt/c/Users/Panup/VirtualLabtest/web-portal/backend
  source .venv/bin/activate
  python -m pytest tests/session -q
  ```
- รอบแรก skip 188 เคส เพราะไม่มี DB เทส → สร้างตาม `tests/README.md`
  ```bash
  docker exec virtual_lab_db psql -U postgres -c "CREATE DATABASE virtual_lab_test;"
  ```
  (สั่งจากฝั่ง Windows เพราะ WSL ยังไม่ได้เปิด Docker Desktop integration)
- baseline หลังสร้าง DB: **226 passed**

### 2026-11-10 — A2: ตัวแปร `LAB_GATEWAY_*` ✅

ไฟล์: `web-portal/backend/app/configs/settings.py` — commit `a0be92c`

| ตัวแปร | ค่าเริ่ม | มีไว้ทำไม |
|---|---|---|
| `LAB_GATEWAY_ENABLED` | `False` | สวิตช์ทั้งระบบ — merge แล้ว prod ไม่เปลี่ยนจนกว่าจะเปิด |
| `LAB_GATEWAY_DOMAIN` | `""` | ต่อท้ายลิงก์ `l-<token>-<port>.<domain>` |
| `LAB_GATEWAY_TOKEN` | `""` | รหัสลับร่วมระหว่าง backend กับ Traefik (header `X-Gateway-Token`) กันคนใน tailnet ดึงตารางที่มี token ของทุกคน |
| `LAB_GATEWAY_PORT_MIN/MAX` | `3000` / `9999` | กันพอร์ตอย่าง 22 ออกอินเทอร์เน็ต |
| `LAB_GATEWAY_UPSTREAM_CIDRS_STR` | `10.10.2.0/24,10.10.3.0/24` | Traefik ส่งต่อได้แค่ subnet ของ lab บน AWS |

**ต่างจาก runbook:**
- runbook บอกให้ทำ validator "แบบเดียวกับ `SECRET_KEY`" แต่ `SECRET_KEY` ใช้ `Field(min_length=32)` ซึ่งใช้ไม่ได้ เพราะตอน flag ปิด token ต้องว่างได้ → ใช้ `@model_validator(mode="after")` เช็กข้ามหลาย field
- เพิ่มเอง: เช็กช่วงพอร์ต + CIDR ตอน start, ทำความสะอาด domain (`.Bell-Lab.Space` → `bell-lab.space` กันลิงก์เป็น `..`), property `lab_gateway_upstream_cidrs` (parse ครั้งเดียวให้ A4 ใช้)

**เทส:** 7 เคส (ปิด / เปิดไม่มี token / token สั้น / ไม่มี domain / พอร์ตกลับด้าน / CIDR ผิด / ครบ) ผลตรงทุกเคส — ยังเป็นสคริปต์ชั่วคราว จะย้ายเป็น test จริงใน A10
`pytest tests/session`: 226 passed

> หมายเหตุ: commit `a0be92c` มี docs (runbook, `CICD_ARGOCD_*`) และ `FILM.md` ติดไปด้วย — ตัดสินใจไม่แก้ประวัติ จะลบ `FILM.md` ใน commit หลัง

### 2026-11-11 — งานข้างเคียงที่เจอระหว่างทาง

- **merge `origin/main` เข้า `feature/aws-dns`** (`8801b64`) — branch ตามหลัง main (ไม่มี `InstructorSchedule`, `MyRequestsModal`, แก้ `booking_service`) ถ้าไม่ merge PR จะดูเหมือนลบไฟล์พวกนี้ และอาจชนใน `session_service.py` ตอน A7–A8
  หลัง merge: ต่างจาก main แค่ docs, migration head ยังเป็น `20261031_01`, test **230 passed**
- **fix ansible 2 ไฟล์ที่ไม่เกี่ยวกับ gateway** (`dae7f97`) — แก้ไว้ตั้งแต่ 2026-11-09 ก่อนเริ่มงานนี้
  - `k3s-server`: `registry_ip` tag `scan` → `always` (รัน `--tags k3s-server` / `--skip-tags scan` แล้วตัวแปรไม่มี)
  - `siem-layer1-collector`: `ansible.builtin.Environment` (ไม่มี module นี้) → keyword `environment`

### 2026-11-11 — A3: column ใหม่ + migration ✅

ไฟล์: `app/models/session.py`, `migrations/versions/20261111_01_session_lab_gateway.py` — commit `b64eca6`

| column | ชนิด | มีไว้ทำไม |
|---|---|---|
| `gateway_token` | `String(32)` unique nullable | token ในลิงก์ `l-<token>-<port>` |
| `upstreams` | `JSONB` nullable | ปลายทางจริงให้ Traefik `{"8443": "http://10.10.2.14:8443"}` |

ต้องแยก `upstreams` ออกจาก `endpoints` เพราะ `endpoints` จะกลายเป็นลิงก์ public ที่นักศึกษาเห็น ส่วน IP ภายในต้องเก็บไว้ให้ Traefik เท่านั้น
**ห้าม** เพิ่ม 2 field นี้ใน `SessionResponse` (ใส่ comment เตือนไว้ใน model แล้ว)

migration รันบน DB local `virtual_lab` (container `virtual_lab_db`):

| คำสั่ง | ผล |
|---|---|
| `alembic upgrade head` | ✅ `20261031_01 → 20261111_01` |
| `alembic downgrade -1` | ✅ กลับ `20261031_01` |
| `alembic upgrade head` | ✅ `20261111_01 (head)` |

`pytest tests/session`: **230 passed**
ตอน deploy ไม่ต้องสั่ง migrate เอง — ansible task "Create database schema" รัน `alembic upgrade` ให้

> ข้อสังเกต: ชื่อ unique constraint ใน DB จริงคือ `uq_sessions_gateway_token` (จาก migration) ส่วน DB เทสคือ `sessions_gateway_token_key` (จาก `create_all`) ไม่มีผลกับการทำงาน

### 2026-11-11 — A4: ฟังก์ชันช่วยของ gateway ✅

ไฟล์ใหม่: `web-portal/backend/app/services/lab_gateway_service.py`, `tests/session/test_lab_gateway.py`

ทุกฟังก์ชันเป็น**ฟังก์ชันล้วน** (รับค่า → คืนค่า ไม่ต่อ DB ไม่เรียก SkyPilot) อ่านค่าจาก `settings` ที่ทำใน A2
`build_routes()` ที่ runbook ใส่ไว้ในไฟล์เดียวกัน แยกไปทำใน A5 เพราะต้องอ่าน DB

ตัวอย่างด้านล่างใช้ token = `k7m2q9xw4bz3ha6c`, domain = `bell-lab.space`, ช่วงพอร์ต 3000–9999

#### `new_token() -> str`

**หน้าที่:** สุ่ม token ใหม่ให้ session หนึ่งตัว ใช้เป็นส่วนหนึ่งของ hostname
**หลักการ:**
1. `secrets.token_bytes(10)` สุ่ม 10 byte (80 bit) จากแหล่งสุ่มที่ปลอดภัยของ OS
2. `base64.b32encode` แปลงเป็น base32 ได้ 16 ตัวพอดี (10 byte หาร 5 ลงตัว จึงไม่มี `=` ต่อท้าย)
3. `.lower()` เพราะ DNS ไม่สนตัวพิมพ์ และอักขระ base32 (`a-z`, `2-7`) ใช้ใน hostname ได้ทั้งหมด

**ทำไม:** ลิงก์ lab ยังไม่มี login (forward-auth คือเฟส 3) ใครรู้ลิงก์ก็เข้าได้ token จึงเป็น "กุญแจ" ต้องสุ่มด้วย `secrets` ไม่ใช่ `random` (ซึ่งเดาได้) 80 bit คือ ~10²⁴ แบบ เดาสุ่มไม่ได้ในทางปฏิบัติ และ 16 ตัวใส่ใน `gateway_token String(32)` ของ A3 ได้

#### `port_allowed(port) -> bool`

**หน้าที่:** บอกว่าพอร์ตนี้เปิดผ่าน gateway ได้ไหม
**หลักการ:**
1. ตัด `bool` ทิ้งก่อน (ใน Python `True` เป็น int = 1)
2. แปลงเป็น str แล้ว `.strip()` → ต้องเป็นตัวเลขล้วน (`isdigit`) ไม่งั้น False — รับได้ทั้ง `8443` และ `"8443"` เพราะ key ของ JSONB เป็น str
3. เช็ก `LAB_GATEWAY_PORT_MIN <= port <= LAB_GATEWAY_PORT_MAX`

**ทำไม:** กันพอร์ตอย่าง 22 (SSH) หรือ 80 ของ lab image ออกอินเทอร์เน็ต และช่วงนี้ต้องตรงกับ SG ของ router (E1) ไม่งั้นได้ลิงก์ที่เปิดไม่ได้
**ตัวอย่าง:** `8443` → True / `"8443"` → True / `22` → False / `"abc"`, `None`, `"-1"` → False

#### `public_host(token, port) -> str`

**หน้าที่:** สร้าง hostname ของ lab หนึ่งพอร์ต
**หลักการ:** ต่อ string `l-{token}-{port}.{LAB_GATEWAY_DOMAIN}`
**ทำไม:** 1 hostname = 1 พอร์ตของ 1 session ให้ Traefik ใช้ `Host(...)` เลือกปลายทางได้ตรง ๆ ขึ้นต้นด้วย `l-` ให้ Cache Rule / Configuration Rule ของ Cloudflare (D3) จับได้ และไม่ชนกับชื่อที่ตั้งไว้แล้ว เช่น `skypilot`, `vlab` ความยาว label สูงสุด `l-` + 16 + `-` + 4 = 23 ตัว ไม่เกินลิมิต DNS 63 ตัว
**ตัวอย่าง:** `public_host("k7m2q9xw4bz3ha6c", 8443)` → `l-k7m2q9xw4bz3ha6c-8443.bell-lab.space`

#### `public_endpoints(token, ports) -> dict[str, str]`

**หน้าที่:** สร้างลิงก์ทั้งหมดที่นักศึกษาจะเห็น (ค่าที่จะเก็บใน `sessions.endpoints` ใน A8)
**หลักการ:** วนทุกพอร์ต → เอาเฉพาะที่ `port_allowed` → key เป็น str ของพอร์ต, value เป็น `https://` + `public_host(...)`
**ทำไม:** หน้าเว็บแสดงปุ่มจาก `endpoints` อยู่แล้ว ถ้าเปลี่ยนค่าในนี้เป็นลิงก์ public ก็**ไม่ต้องแก้ frontend** ใช้ `https` เพราะ Cloudflare ถือ cert ให้ (`*.bell-lab.space`) key เป็น str ให้ตรงกับรูปแบบเดิมที่เก็บใน JSONB พอร์ตนอกช่วงหายไปจากหน้าเว็บบน AWS (D13 ใน runbook)
**ตัวอย่าง:** `[8443, 5173, 22]` → `{"8443": "https://l-…-8443.bell-lab.space", "5173": "https://l-…-5173.bell-lab.space"}`

#### `gateway_envs(token, ports) -> dict[str, str]`

**หน้าที่:** env ที่ต้องส่งเข้า container ของ lab บน AWS (`docker run -e ...` ใน A7)
**หลักการ:** คืน `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=.<domain>` เสมอ + `VLAB_PUBLIC_URL_<port>=<ลิงก์>` ทุกพอร์ตที่ได้จาก `public_endpoints`
**ทำไม:**
- Vite dev server (music-lab) ตรวจ `Host` header และปฏิเสธ host ที่ไม่รู้จัก (กัน DNS rebinding) พอเปิดผ่าน `l-….bell-lab.space` จะโดนบล็อก ต้องบอกว่า `.bell-lab.space` อนุญาต — Vite 5.4 ของ music-lab อาจไม่อ่าน env นี้ ต้องเช็กใน F1
- lab บางตัวต้องรู้ URL ของตัวเอง (สร้างลิงก์, websocket, callback) ให้อ่านจาก `VLAB_PUBLIC_URL_<port>`

**ตัวอย่าง:** `[8443, 22]` → `{"__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS": ".bell-lab.space", "VLAB_PUBLIC_URL_8443": "https://l-…-8443.bell-lab.space"}`

#### `upstream_ok(url) -> bool`

**หน้าที่:** ด่านสุดท้ายก่อนใส่ปลายทางลงตาราง route ของ Traefik (A5 จะเรียกทุกพอร์ตของทุก session)
**หลักการ:** ผ่านเมื่อครบทุกข้อ ข้อไหนไม่ผ่านหรือ parse พัง = False
1. scheme เป็น `http` (traffic ใน VPC ไม่ได้เข้ารหัส ส่วน https อยู่ที่ Cloudflare)
2. มีพอร์ต และ `port_allowed`
3. host เป็น **IP** (ไม่รับชื่อ host เพราะ resolve ไปที่ไหนก็ได้)
4. IP อยู่ใน `settings.lab_gateway_upstream_cidrs` (`10.10.2.0/24`, `10.10.3.0/24`)

**ทำไม:** ถ้าค่าใน DB เพี้ยนหรือถูกแก้ router ต้องไม่กลายเป็นทางเข้าเครือข่ายภายใน เช่น backend `100.102.72.39:8000`, ตัว router เอง `127.0.0.1`, subnet อื่นใน VPC หรือเว็บข้างนอก
**ตัวอย่าง:** `http://10.10.2.14:8443` → True / `http://8.8.8.8:8080`, `http://10.10.2.14:22`, `https://10.10.2.14:8443`, `http://lab.internal:8443`, `None` → False

**ต่างจาก runbook:**
- `_upstream_ok` → `upstream_ok` (ไม่มี `_`) เพราะ A5 และ test เรียกจากข้างนอก
- ใช้ `settings.lab_gateway_upstream_cidrs` จาก A2 แทนการ parse CIDR ใหม่ทุกครั้ง (Traefik ดึงทุก 5 วิ × ทุกพอร์ตของทุก session)
- เพิ่มเงื่อนไข: ต้องเป็น `http` และต้องมีพอร์ต (runbook ไม่ได้เช็ก — URL ไม่มีพอร์ตทำให้ `port_allowed(None)` False อยู่แล้ว แต่เขียนให้ชัด)
- `port_allowed` กัน `True` / ช่องว่าง / ค่าติดลบ เพิ่ม

**เทส:** `tests/session/test_lab_gateway.py` 39 เคส (token รูปแบบ + ไม่ซ้ำ 1000 ตัว + ยาวไม่เกิน DNS label / ขอบช่วงพอร์ต 2999–10000 + ค่าแปลก / ลิงก์ + ตัดพอร์ต 22, 80 / env / upstream ผ่าน 2 แบบ ไม่ผ่าน 12 แบบ / ค่าตาม settings)
`pytest tests/session`: **269 passed** (230 เดิม + 39 ใหม่)

---

## เรื่องที่ค้าง / ต้องถาม

- [ ] **C1** (Panupong): ดู record `*.bell-lab.space` ใน Cloudflare แล้วจดค่าเดิม
- [ ] **C2** (Pete): ยืนยัน backend ยังอยู่ที่ `vlab-web` `100.102.72.39` บน ThinkPad + ตอบคำถามที่ค้างในข้อ 0.1 ของ runbook
- [ ] ลบ `FILM.md` ออกจาก repo (ติดมาใน `a0be92c`) หรือย้ายไป `.git/info/exclude`
- [ ] ก่อนใช้สอนจริง: ย้าย `vlab-web` ไปเครื่องที่เปิดตลอด (ThinkPad ปิด = portal ล่ม)
- [ ] `CICD_ARGOCD_SOLUTION.md` ข้อ 0 วางแผนย้าย web-portal เข้า K3s — สวนกับการตัดสินใจ 2026-11-10 และ runbook (backend อยู่ที่ `vlab-web`) ถ้าแผน CI/CD เดินหน้า ต้องแก้เรื่อง IP จริงหลัง kube-proxy และ ACL/URL ของ Traefik

---

## แผนขั้นย่อยของเฟส 1

ลำดับ: `A1–A10` ∥ `C1` → `B` → (`D` ∥ `C2–C6`) → `E` → `F`

**A: โค้ด backend** (dev บน PC)

| ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|
| A1 ✅ | ใช้ branch `feature/aws-dns` | — |
| A2 ✅ | `settings.py`: `LAB_GATEWAY_*` + validator | start ได้ตอนปิด / เปิดแต่ไม่มี token start ไม่ขึ้น |
| A3 ✅ | model `gateway_token`, `upstreams` + migration | upgrade / downgrade ผ่าน |
| A4 ✅ | `lab_gateway_service.py`: token, ลิงก์, เช็ก upstream | unit test ผ่าน |
| A5 | `build_routes()` | RUNNING อยู่ในตาราง / PENDING, STOPPED, IP นอก ไม่อยู่ |
| A6 | route `/internal/v1/gateway/routes` | ไม่มี token 404 / token ถูกได้ JSON |
| A7 | `session_service.py`: token ไหล `_new_sky_session` → `create_fastapi_task` → `_build_aws_task` | `docker run` มี `-e VLAB_PUBLIC_URL_...` / K8s ไม่มี |
| A8 | `_run_sky_launch`: แยก `endpoints` / `upstreams` | endpoint `https://l-...` / API ไม่คืน `upstreams` |
| A9 | `main.py`: ซ่อน 2 column ในหน้า admin | หน้า admin ไม่เห็น |
| A10 | test ทั้งหมด | เก่าไม่พัง + ใหม่ผ่าน |

**B: Ansible web-service** — B1 ตัวแปร + `backend.env.j2` / B2 สุ่ม `vault_lab_gateway_token` / B3 deploy ลง `vlab-web` flag ปิด (แจ้งทีมก่อน)

**C: Phase 0** — C1 จดค่า DNS `*` / C2 คุยกับ Pete / C3 จดค่า 5 ตัว / C4 เก็บสถานะ router / C5 AMI snapshot / C6 เทส baseline

**D: Cloudflare** (Panupong) — D1 tunnel `vlab-lab-gateway` / D2 hostname + DNS `*` (521 → 1033) / D3 Cache + Configuration Rule / D4 เช็ก `skypilot` ยังใช้ได้

**E: Router** (กับ Pete ช่วงไม่มีคาบ ตามลำดับ) — E1 terraform plan (ต้อง in-place) / E2 apply + ลบ rule มือ / E3 Tailscale tag + ACL / E4 SSH + inventory / E5 role `lab-gateway` / E6 รัน role (tunnel Healthy)

**F: เปิดใช้งาน** — F1 เช็ก Vite ใน music-lab / F2 เปิด flag / F3 เปิดลิงก์บนมือถือ 4G / F4 เทส G1–G12
