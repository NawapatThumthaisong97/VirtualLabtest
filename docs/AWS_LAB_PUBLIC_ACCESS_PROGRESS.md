# บันทึกความคืบหน้า: เปิด lab บน AWS ให้คนนอก tailnet ใช้ได้

> ทำตาม [AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md](AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md) — doc นี้จดว่า **ทำอะไรไปแล้ว ตัดสินใจอะไร เจออะไรระหว่างทาง**
> เขียนต่อท้ายทุกครั้งที่จบขั้น ห้ามแก้ของเก่า (ถ้าเปลี่ยนใจให้เขียนบันทึกใหม่ว่าเปลี่ยนเพราะอะไร)
> branch: `feature/aws-dns`

---

## สถานะล่าสุด

| ส่วน | ขั้น | สถานะ |
|---|---|---|
| A: โค้ด backend | A1–A10 ✅ | **เสร็จ** (2026-11-11) — ถัดไป **B** (Ansible) หรือ C1 / D (Cloudflare) |
| B: Ansible web-service | B1 ✅ B2 ✅ / B3 ⏳ | ถัดไป **B3** — รอ VM ของ Panupong + `masterlab2` online |
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
| 2026-11-11 | deploy backend ที่ไหน (B3) | Panupong **สร้าง VM ของตัวเอง** แล้วลง role `web-service` ลงเครื่องนั้น แทน `vlab-web` ของ Pete | `vlab-web` offline (Pete ปิดเครื่อง) และไม่มี `inventory.home.yml` ในเครื่อง Panupong / ไม่กระทบ portal ตัวจริงของทีม ผลที่ตามมา: `<BACKEND_TS_IP>` ใน ACL (E3) และ URL ของ Traefik (E5) = Tailscale IP ของ VM ใหม่ (ดึงจาก group `webservice` ใน inventory อัตโนมัติ) / DB ของ VM ใหม่ว่าง ต้อง seed user / course / lab / image เอง |

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

### 2026-11-11 — A5: ตาราง route ของ Traefik ✅

ไฟล์: `app/services/lab_gateway_service.py` (เพิ่มส่วนล่าง), `tests/session/test_lab_gateway.py` (เพิ่ม 19 เคส)

#### Traefik ใช้ตารางนี้ยังไง

config ของ Traefik มี 2 ส่วน:

| | static config | dynamic config |
|---|---|---|
| คืออะไร | ฟังพอร์ตไหน ไปดึงตาราง route จากไหน | hostname ไหนส่งไปเครื่องไหน |
| อยู่ที่ | `/etc/traefik/traefik.yml` บน router | JSON ที่ backend ตอบ |
| ทำในขั้น | **E5–E6** (role `lab-gateway`, template `traefik.yml.j2`) | **A5** (`build_routes`) + **A6** (endpoint) |

static config บอก Traefik ว่า "ทุก 5 วิ ไปถาม `http://<vlab-web>:8000/api/internal/v1/gateway/routes` พร้อม header `X-Gateway-Token`" แล้ว Traefik เอา JSON ที่ได้มา**แทนตารางเดิมทั้งก้อน**
ต้องทำ A5–A6 ก่อน E เพราะถ้าลง Traefik ก่อน backend มี endpoint ตัว verify ของ E6 (เช็ก `provider error` ใน log) จะไม่ผ่าน

#### `routable_sessions(db) -> list[Session]`

**หน้าที่:** หา session ที่ลิงก์ gateway ควรเปิดได้ **ณ ตอนนี้**
**หลักการ:** query เดียว ต้องผ่านทุกเงื่อนไข:

| เงื่อนไข | ทำไม |
|---|---|
| `status == RUNNING` | PENDING เครื่องยังไม่พร้อม / STOPPED, FAILED ปิดแล้ว ห้ามมีลิงก์ที่ใช้ได้ |
| `is_cloud == True` | เฉพาะ lab บน AWS (`session_service.py:459` ตั้ง `is_cloud = run_target == AWS`) |
| มี `gateway_token` และ `upstreams` | session ที่เปิดตอน flag ปิดไม่มีค่าเหล่านี้ |
| `deleted_at` ว่าง | ลบแล้วห้ามเปิด |
| `prelaunched_at` ว่าง **หรือ** `claimed_at` มีค่า | เครื่องที่ scheduler เปิดรอไว้ก่อนคาบ online แต่ยังไม่มีนักศึกษามารับ = ยังไม่ใช่ของใคร |

เรียงตาม `id` ให้ผลลัพธ์คงที่ทุกรอบ แยกออกมาเป็นฟังก์ชันของตัวเอง (runbook รวมไว้ใน `build_routes`) ให้อ่านง่ายและใช้ซ้ำได้

#### `build_routes(db) -> dict`

**หน้าที่:** แปลง session จาก `routable_sessions` เป็น dynamic config ของ Traefik (HTTP provider)
**หลักการ:**
1. วนทุก session → วนทุกพอร์ตใน `upstreams`
2. เช็ก **key** ด้วย `port_allowed` และ **URL** ด้วย `upstream_ok` ไม่ผ่าน = ข้าม + log warning
3. ผ่าน = สร้าง 2 อย่างด้วยชื่อเดียวกัน `s-<token>-<port>`:
   - **router:** `Host(\`l-<token>-<port>.<domain>\`)` → service ชื่อนี้ ผ่าน entryPoint `web`
   - **service:** `loadBalancer` → URL จริง `http://10.10.2.x:<port>`

```json
{"http": {
  "routers":  {"s-k7m2…-8443": {"rule": "Host(`l-k7m2…-8443.bell-lab.space`)", "service": "s-k7m2…-8443", "entryPoints": ["web"]}},
  "services": {"s-k7m2…-8443": {"loadBalancer": {"servers": [{"url": "http://10.10.2.14:8443"}]}}}
}}
```

ไม่มี session = `{"http": {"routers": {}, "services": {}}}` → Traefik ตอบ 404 ทุก Host (ค่าที่เช็กใน F2)

**ทำไมคำนวณใหม่จาก DB ทุกรอบ:** ไม่ต้องมีขั้น "ลบ route" แยก session ปิดเมื่อไหร่ (ผู้ใช้กดปิด / หมดเวลา / reconciler เปลี่ยน status) รอบถัดไปหลุดจากตารางเอง ภายใน 5 วิ จึงไม่ต้องแก้ `session_reconciler.py`

**ทำไมข้ามทีละพอร์ตแทนการ error:** ตารางเป็นของทุกคนรวมกัน ถ้า session เดียวมีข้อมูลเพี้ยนแล้ว raise Traefik จะดึงไม่ได้และลิงก์ของ**ทุกคน**ใช้ไม่ได้ จึงข้ามเฉพาะพอร์ตที่มีปัญหา พอร์ตอื่นของ session เดียวกันและ session อื่นยังใช้ได้

**ต่างจาก runbook:**
- แยก `routable_sessions()` ออกมา
- **เช็ก key ของ `upstreams` ด้วย `port_allowed`** — runbook เช็กแค่ URL ถ้า key ไม่ใช่ตัวเลข (เช่น `"abc"`) `int(port)` ตอนตั้งชื่อจะ error แล้วตารางของทุกคนล้มทั้งก้อน
- `entryPoints` ใช้ค่าคงที่ `TRAEFIK_ENTRYPOINT = "web"` ให้เห็นว่าต้องตรงกับ `traefik.yml` ของ E5

**เทส (19 เคสใหม่ ใช้ DB `virtual_lab_test`):** ตารางว่าง / session ปกติได้ JSON ตรงทุกตัวอักษร / หลาย session ไม่ปนกัน / PENDING, STOPPED, FAILED, ลบแล้ว, K8s, ไม่มี token, ไม่มี upstreams ไม่อยู่ / prelaunch ยังไม่รับไม่อยู่ รับแล้วอยู่ / session ปิดแล้วหลุดในรอบถัดไป / upstream เพี้ยน 5 แบบ (นอก subnet, พอร์ต 22, IP ของ backend, key ไม่ใช่ตัวเลข, URL เป็น null) ถูกข้าม + มี warning + พอร์ตดีของ session เดียวกันยังอยู่ / session เพี้ยนไม่ทำให้ session อื่นหาย
`test_lab_gateway.py`: 58 passed / `pytest tests/session`: **288 passed**

### 2026-11-11 — ภาพรวมของ flow ทั้งหมด (ตอบคำถามระหว่างทำ)

```
                       ┌──────────────── AWS VPC ──────────────────────────────┐
นักศึกษา (มือถือ 4G)    │   EC2 vlab-ts-router                     EC2 lab ของ นศ │
   │ ① https://l-…     │  ┌──────────────────────────────┐                     │
   ▼                   │  │ cloudflared ──③──> Traefik    │ ──⑤──> 10.10.2.14:8443
Cloudflare ──② tunnel──┼─>│ (systemd)       127.0.0.1:8081│                     │
(DNS *, cert https)    │  │                      │ ④ ทุก 5 วิ │                     │
                       │  └──────────────────────┼────────┘                     │
                       └─────────────────────────┼──────────────────────────────┘
                                                 │ Tailscale (ACL: router → :8000 เท่านั้น)
                                                 ▼
                                vlab-web: FastAPI GET /api/internal/v1/gateway/routes → build_routes()
```

| เครื่อง | ตอนกด Start | ตอนกดลิงก์ `l-…` |
|---|---|---|
| `vlab-web` (FastAPI + Postgres) | สุ่ม token, สั่ง launch, บันทึก `endpoints` / `upstreams` | ตอบตาราง route ให้ Traefik |
| k3s master | SkyPilot API server (`webservice_skypilot_endpoint` = `http://<master>:30880`) สั่งเปิด EC2 | **ไม่เกี่ยว** |
| `vlab-ts-router` (EC2) | — | cloudflared + Traefik รับแล้วส่งต่อใน VPC |
| EC2 lab | ถูกเปิด | ให้บริการ lab |
| Cloudflare | — | DNS `*`, https, tunnel |

- **cloudflared และ Traefik อยู่บน router ไม่ใช่ master** (ไม่ใช่ pod — เป็น systemd service) router เป็นเครื่องเดียวที่อยู่ทั้งใน VPC (ส่งถึง `10.10.2.x`) และใน Tailscale (ถาม backend ได้)
- tunnel บน master ที่มีอยู่แล้วคือของ `skypilot.bell-lab.space` คนละเรื่องกัน
- **FastAPI ไม่เคยเรียก router** — Traefik เป็นฝ่ายดึง (pull) ทุก 5 วิ: backend ไม่ต้องรู้ที่อยู่ router / router ไม่ต้องเปิดพอร์ตรับคำสั่ง / router รีบูตแล้วดึงตารางทั้งก้อนใหม่เอง / session ปิดแล้วหลุดเอง แลกกับช้าสุด 5 วิ (EC2 เปิดใช้ 1.5–3 นาทีอยู่แล้ว)
- master ล่ม = กด Start lab AWS ใหม่ไม่ได้ แต่ lab ที่เปิดอยู่ยังใช้ได้ / `vlab-web` ล่ม = ตารางไม่อัปเดต
- เฟส 1 ยังต้อง login + กด Start ผ่าน Tailscale (portal public คือเฟส 2) เทสโดยคนในทีมกด Start แล้วเปิดลิงก์บนมือถือ 4G
- คนเข้าไปจัดการ router: Pete บอกว่า SSH ผ่าน Tailscale IP ได้เลย (ไม่ต้องใช้ SSM ใน E4) — ดู "เรื่องที่ค้าง"

### 2026-11-11 — A6: endpoint ที่ Traefik เรียก ✅

ไฟล์ใหม่ `app/routes/lab_gateway_route.py` + ลงทะเบียนใน `app/routes/__init__.py` → `GET /api/internal/v1/gateway/routes`

#### `_token_ok(given) -> bool`

**หน้าที่:** ตัดสินว่า request นี้มาจาก Traefik ของเราจริงไหม
**หลักการ:** ผ่านเมื่อ flag เปิด **และ** server ตั้ง token ไว้ **และ** header ไม่ว่าง **และ** ตรงกันทุกตัว เทียบด้วย `hmac.compare_digest`
**ทำไม `compare_digest`:** การเทียบ string ธรรมดา (`==`) หยุดทันทีที่เจอตัวแรกที่ไม่ตรง เวลาตอบจึงบอกได้ว่าเดาถูกกี่ตัวแรก (timing attack) `compare_digest` ใช้เวลาเท่ากันเสมอ
**ทำไมเช็ก server token ว่าง:** กันกรณี token ไม่ได้ตั้งแล้ว header ว่างไปตรงกับค่าว่าง (`"" == ""`)

#### `gateway_routes(x_gateway_token, db)`

**หน้าที่:** endpoint ที่ Traefik (HTTP provider) เรียกทุก 5 วิ
**หลักการ:** `_token_ok` ไม่ผ่าน → **404** / ผ่าน → คืน `build_routes(db)` ตรง ๆ
**ทำไม:**
- **ไม่ห่อ `ApiResponse`** เหมือน endpoint อื่น เพราะ Traefik อ่านรูปแบบ `{"http": {...}}` ของมันเองเท่านั้น
- **ตอบ 404 ไม่ใช่ 401/403** — ไม่บอกคนที่ลองยิงว่ามี endpoint นี้อยู่
- **ไม่ใช้ JWT** — Traefik ไม่ใช่ user ใช้รหัสลับร่วม (`LAB_GATEWAY_TOKEN` = `X-Gateway-Token` ใน `traefik.yml`) แทน
- `include_in_schema=False` ไม่โผล่ใน `/docs`

**เทส (11 เคส):** ลงทะเบียนใน `api_router` จริง / ไม่อยู่ใน OpenAPI / token ถูก 200 + ตาราง / ไม่มี lab ได้ตารางว่าง / token หาย, ว่าง, ผิด, สั้นไป 1 ตัว, ยาวไป 1 ตัว = 404 และไม่มีตารางหลุด / flag ปิด 404 / server ไม่ตั้ง token + header ว่าง 404

### 2026-11-11 — A7: token ไหลเข้า task ของ AWS ✅

ไฟล์: `app/services/session_service.py`

| ฟังก์ชัน | แก้อะไร | ทำไม |
|---|---|---|
| `_new_sky_session` | `gateway_token = new_token() if LAB_GATEWAY_ENABLED and is_cloud else None` แล้วส่งเข้า `create_fastapi_task` และใส่ใน `SessionModel(...)` | token ต้องรู้**ก่อน**สร้าง task (env อยู่ใน `docker run`) แต่เดิม task ถูกสร้างก่อน record จึงสุ่มตรงจุดเริ่ม แล้วใช้ค่าเดียวกันทั้งสองที่ (runbook D3) |
| `create_fastapi_task` | รับ `gateway_token` ส่งต่อ `_build_aws_task` เท่านั้น | K3s ไม่ผ่าน gateway (เปิดผ่าน localhost บนเครื่องแลป) |
| `_build_aws_task` | `envs = _lab_envs(...)` แล้ว `envs.update(gateway_envs(token, ports))` ก่อนวนสร้าง `-e` | **ไม่แตะ `_lab_envs`** เพราะ K3s / warm pod / direct pod ใช้ร่วม |

prelaunch (`prelaunch_service`) เรียก `_new_sky_session` ตัวเดียวกัน จึงได้ token ตั้งแต่ PENDING โดยไม่ต้องแก้

### 2026-11-11 — A8: แยก `endpoints` กับ `upstreams` ✅

`_run_sky_launch` หลังได้ `formatted_endpoints` จาก `sky.endpoints` (`{"8080": "http://10.10.2.14:8080"}`):
- **มี token:** `upstreams = formatted_endpoints` (IP ภายใน ให้ Traefik) / `endpoints = public_endpoints(token, ports)` (ลิงก์ที่นักศึกษาเห็น) / พอร์ตนอกช่วง → log warning `[gateway] … ports ['80'] outside 3000-9999, no public link` (runbook D13)
- **ไม่มี token:** `endpoints = formatted_endpoints` แบบเดิม

**ไม่ต้องแก้:** `_claim_prelaunched` (คืน `session.endpoints` ที่ตั้งไว้แล้ว), `_sky_result` (คืน `endpoints` ซึ่งตอนนี้เป็นลิงก์ public แล้ว), `session_reconciler.py`, **frontend** (แสดงปุ่มจาก `endpoints` อยู่แล้ว)

> ต้องยืนยันตอน **C6** (เร็วสุด) หรือ F3: runbook ถือว่า `sky.endpoints` ของ lab AWS คืน **private IP** `10.10.2.x` ถ้าคืน IP อื่น `upstream_ok` จะตัดทิ้ง ลิงก์ทุกลิงก์ได้ 404 และมี warning `not allowed` ใน log ของ backend
> หลักฐานว่าน่าจะถูก (2026-11-11): `ansible/roles/skypilot-node/tasks/main.yml:188` ตั้ง `use_internal_ips: true` / `docs/archive/EXPERIMENT_ECR_PULL_RESULT.md` lab อยู่ใน private subnet `10.10.2.0/24` ไม่มี public IPv4 / runbook 0.5 เปิด lab ทุกวันนี้ด้วย `http://10.10.2.x` — DB local ไม่มี session AWS เก่าให้ดู
> ถ้าผิด: เพิ่ม CIDR ใน `LAB_GATEWAY_UPSTREAM_CIDRS_STR` หรือให้ backend หา private IP เอง

### 2026-11-11 — A9: ซ่อนใน หน้า admin ✅

`app/main.py` `SessionAdmin`:
```python
column_list = get_model_columns(Session, exclude=["endpoints", "gateway_token", "upstreams"])
column_details_exclude_list = ["gateway_token", "upstreams"]
form_excluded_columns = ["gateway_token", "upstreams"]
```
**ทำไม:** หน้า admin เดิมแสดงทุก column ยกเว้น `endpoints` (runbook D9) — `gateway_token` คือกุญแจเข้า lab ของนักศึกษา ใครเห็นก็เปิด lab คนอื่นได้
**ต่างจาก runbook:** ใส่ใน `exclude` ของ `column_list` แทน `column_exclude_list` เพราะ sqladmin ไม่ให้ตั้งทั้งสองอย่างพร้อมกัน และเพิ่ม details / form ด้วย

### 2026-11-11 — A10: เทสทั้งหมด ✅

`tests/session/test_lab_gateway.py` รวม **83 เคส**:

| กลุ่ม | ขั้น | จำนวน |
|---|---|---|
| token / port / ลิงก์ / env / upstream | A4 | 39 |
| ตาราง route (DB) | A5 | 19 |
| endpoint | A6 | 11 |
| env ใน task (AWS มี token / ไม่มี / K3s ไม่มีแม้ส่ง token) | A7 | 3 |
| กด Start ทั้งเส้นด้วย sky ปลอม: AWS ได้ลิงก์ public + upstreams, task ใช้ token เดียวกับ record, เข้าตาราง route, flag ปิดเหมือนเดิม, K3s ไม่มี token, พอร์ต 80 ถูกตัด + warning, token ใหม่ทุกครั้ง, prelaunch มี token ตั้งแต่ PENDING แต่เข้าตารางหลังรับเครื่อง | A7–A8 | 8 |
| ไม่หลุด: `SessionResponse` / `SessionDetailResponse` ไม่มี 2 field / response ของ Start ไม่มี IP ภายใน | A8 | 2 |
| หน้า admin | A9 | 1 |

ผล:
- `pytest tests/session`: **313 passed**
- `pytest tests` (ทั้ง repo): **703 passed, 2 failed, 3 skipped** — 2 ตัวที่ fail คือ `test_siem_layer1_collector` / `test_siem_layer3_processing` (`*_strict_binary_validation`) ต้องเรียก `docker` แต่ WSL ไม่มี (Docker Desktop ยังไม่เปิด WSL integration) **ไม่เกี่ยวกับ gateway**

เจอระหว่างเทส: **run target มาจากที่ที่กด Start (IP) ไม่ใช่ตัว lab** — กดจากข้างนอกได้ AWS เสมอ แม้ lab ตั้งเป็น K3s เคส "SkyPilot บน K3s" เกิดได้เฉพาะกดจากเครื่องแลปตอน `LAB_MACHINE_LAUNCH=skypilot` เทสจึงเรียก `_new_sky_session` ด้วย `KUBERNETES` ตรง ๆ

**ยังไม่ได้ทำ:** `curl` endpoint จริงบน server ที่รันอยู่ (เกณฑ์ของ A6 ในแผน) — ครอบด้วย TestClient แล้ว จะเห็นของจริงตอน B3 (deploy flag ปิด ต้องได้ 404) และ F2 (flag เปิด ต้องได้ตารางว่าง)

### 2026-11-11 — B1: ตัวแปร Ansible ของ role `web-service` ✅

**ทำไมต้องมี:** โค้ด A อ่าน `LAB_GATEWAY_*` จาก `.env` แต่ `.env` บน server ไม่มีใครเขียนเอง role `web-service` render จาก `templates/backend.env.j2` ทุกครั้งที่ deploy — ถ้าไม่ต่อสายตรงนี้ backend จะใช้ค่าเริ่มต้นในโค้ด (ปิด) ตลอด และเปิด flag ผ่าน Ansible ไม่ได้

```
group_vars/all.yml (vault_lab_gateway_token) ─┐
roles/web-service/defaults/main.yml          ├─> Ansible ─> .env บน VM ─> Settings (A2)
roles/web-service/templates/backend.env.j2   ┘
```

| ไฟล์ | เพิ่ม |
|---|---|
| `roles/web-service/defaults/main.yml` | `webservice_lab_gateway_enabled: false` / `webservice_lab_gateway_domain: bell-lab.space` / `webservice_lab_gateway_token: "{{ vault_lab_gateway_token \| default('') }}"` (วางก่อนหัวข้อ SIEM) |
| `roles/web-service/templates/backend.env.j2` | `LAB_GATEWAY_ENABLED={{ … \| bool \| string \| lower }}` / `LAB_GATEWAY_DOMAIN` / `LAB_GATEWAY_TOKEN` (ต่อท้ายไฟล์) |
| `roles/web-service/tasks/main.yml` | **เพิ่มเอง (ไม่มีใน runbook)** task `Validate lab gateway settings` ต่อจาก assert ของ SkyPilot token |
| `group_vars/all.yml.example` | ตัวอย่าง `vault_lab_gateway_token` + วิธีสุ่ม (ไฟล์ใน git ให้คนอื่นรู้ว่าต้องตั้ง) |

**ทำไม `| bool | string | lower`:** ค่าที่ส่งด้วย `-e webservice_lab_gateway_enabled=true` เป็น **string** `"true"` ไม่ใช่ bool — `| bool` แปลง `"true"`, `"yes"`, `"1"`, `True` ให้เป็นค่าเดียวกันก่อน แล้ว `| string | lower` ได้ `true` / `false` ที่ pydantic อ่านได้ (role ใช้ `| string | lower` อย่างเดียวกับตัวแปรอื่น — กับ `-e ...=yes` จะได้ `yes` ซึ่ง pydantic ก็รับ แต่ใส่ `| bool` ให้แน่นอนกว่า)

**ทำไมเพิ่ม assert ใน role:** ถ้าเปิด flag แต่ token ว่าง / สั้น validator ของ A2 ทำให้ backend **ไม่ start** แต่ deploy จะไปพังที่ task "Wait for backend to become healthy" หลัง build เสร็จ (หลายนาที) โดย error ไม่บอกสาเหตุ assert นี้หยุดตั้งแต่ task แรก พร้อมบอกวิธีแก้ — แนวเดียวกับ assert ของ `skypilot_backend_token` ที่มีอยู่แล้ว
เช็กเพิ่มว่า token มีแค่ `A-Z a-z 0-9 _ -` เพราะ `#` / ช่องว่าง / quote ใน `.env` ทำให้อ่านค่าผิด (`#` ถูกมองเป็น comment) — `secrets.token_urlsafe` ให้แค่ตัวอักษรชุดนี้อยู่แล้ว

**line ending:** ไฟล์ใน working copy เป็น CRLF (`core.autocrlf=true`, ใน git เป็น LF) เขียนด้วย Python ให้คง CRLF ตามไฟล์เดิม — `git ls-files --eol` ยัง `i/lf w/crlf` ทุกไฟล์

### 2026-11-11 — B2: รหัสลับ `vault_lab_gateway_token` ✅

สุ่มด้วย `secrets.token_urlsafe(48)` (64 ตัว) ใส่ท้าย `ansible/group_vars/all.yml` — ไฟล์นี้ **gitignore** (`.gitignore:195`) ไม่เข้า repo / ค่าไม่ได้แสดงในหน้าจอหรือ log
**ค่าเดียวใช้ 2 ที่:** `LAB_GATEWAY_TOKEN` ของ backend (role `web-service`) และ `X-Gateway-Token` ใน `traefik.yml` (role `lab-gateway` E5) — เก็บที่เดียว จึงตรงกันเสมอ
ถ้าหลุด: สุ่มใหม่ แล้วรันทั้ง 2 role ใหม่ (ช่วงที่ยังไม่ตรงกัน Traefik จะได้ 404 → ใช้ตารางเดิมต่อ ลิงก์ใหม่ยังไม่ขึ้น)

#### ตรวจด้วย Ansible จริง (2.16 ใน WSL) — ไม่แตะเครื่องไหน

playbook ชั่วคราวบน localhost: inventory ปลอม (group `webservice` / `master` / `registry`) + `group_vars/all.yml` จริง + `defaults/main.yml` ของ role → รัน task validate ของ role (ส่วนบนของ `tasks/main.yml`) → render `backend.env.j2` **ทั้งไฟล์**

| เคส | ผล |
|---|---|
| ค่าเริ่มต้น | ✅ `LAB_GATEWAY_ENABLED=false` / `DOMAIN=bell-lab.space` / token 64 ตัว |
| เปิดด้วย bool (`-e '{"…": true}'`) | ✅ `true` |
| เปิดด้วย string (`-e webservice_lab_gateway_enabled=true`) | ✅ `true` |
| เปิด + token ว่าง | ✅ หยุดที่ assert พร้อมข้อความบอกวิธีแก้ |
| เปิด + token มี `#` | ✅ หยุดที่ assert |

แล้วเอา `.env` ที่ render ได้ป้อน `Settings(_env_file=…)` ของ backend: ทั้ง 3 เคสที่ผ่านโหลดได้ ค่าตรง validator A2 ผ่าน — ลบไฟล์ที่ render (มีค่าลับจริง) ทิ้งแล้ว

`web-portal/backend/.env.example`: เพิ่มหัวข้อ 13.1 Lab Gateway ครบ 6 ตัวแปร (ปิดเป็นค่าเริ่มต้น) — `.env` ในเครื่อง Panupong ไม่ต้องแก้ (ค่าเริ่มต้นในโค้ด = ปิด, pytest รีเซ็ต settings เองอยู่แล้ว) หมายเหตุ: `.env` ในเครื่องชี้ SkyPilot / registry ของ Pete (`100.125.244.48`, `100.127.74.48`) ใช้รัน backend บน PC แล้วกด Start ไม่ได้ — ไม่เป็นไรเพราะทางทดสอบคือ B3 บน VM ซึ่งใช้ `.env` จาก Ansible

### 2026-11-11 — ตัดสินใจใช้ master ของตัวเอง + เช็ก `masterlab2` (อ่านอย่างเดียว)

**ตัดสินใจ:** ใช้ `masterlab2` (`100.77.79.61`, k3s + SkyPilot ที่ลงด้วย Ansible + `group_vars/all.yml` ของ Panupong) แทน master ของ Pete — `skypilot_backend_token` ใน `all.yml` เป็นของ `masterlab2` (ไม่ตรงกับ token ใน `.env` ที่ Pete ส่งมา ซึ่งเป็นของ `master` `100.125.244.48`) และ `inventory.yml` ชี้ group `master` ไปที่ `masterlab2` อยู่แล้ว → role `web-service` จะชี้ backend ไป `http://100.77.79.61:30880` เอง
master จำเป็นเฉพาะตอน **กด Start** (SkyPilot API server สั่งเปิด / ปิด EC2) — ตอนเปิดลิงก์ `l-…` ไม่ผ่าน master

เข้าทาง WSL `ssh -i ~/.ssh/id_ed25519 panupong@100.77.79.61` (sudo มีรหัส — VM ทดสอบ) รันแค่คำสั่งอ่าน ค่าลับดูแค่ความยาว / hash

| # | เช็ก | ผล |
|---|---|---|
| 1 | k3s + SkyPilot API server | ✅ node `masterlab2` Ready (k3s v1.35.5) / pod `skypilot-api-api-server` 2/2 Running / NodePort `skypilot-api-tailnet` `30880` / `/api/health` = `healthy` SkyPilot **0.12.3.post1** |
| 2 | `skypilot_backend_token` ใน `all.yml` | ✅ ใช้กับ API server นี้ได้ (token ปลอมได้ 401 ตัวจริงไม่โดนปฏิเสธ) |
| 3 | config ของ SkyPilot (configmap `skypilot-api-config`) | ✅ `aws.vpc_names: vlab-ecr-pull` / `use_internal_ips: true` / `use_ssm: false` / `security_group_name: vlab-lab-instances` (= SG ใน `terraform/security_groups.tf:69`) / `remote_identity: vlab-lab-ecr-pull` (= IAM role ใน `terraform/lab_iam.tf`) |
| 3 | AWS credentials | ✅ secret `aws-credentials` มี key ครบ / access key **ตัวเดียวกับ** `skypilot_aws_access_key_id` ใน `all.yml` (sha256 ตรงกัน) / `sky status` บอก `Enabled Infra: kubernetes/in-cluster, aws` = AWS credentials ใช้ได้ |
| 4 | Tailscale บน master | ✅ `RouteAll: true` (accept-routes) / route `10.10.2.0/24`, `10.10.3.0/24` อยู่ใน table 52 ผ่าน `tailscale0` |
| 4 | ใครประกาศ route `10.10.x` | ✅ **`ip-10-10-1-234` `100.84.123.59` เป็นเครื่องเดียวที่ประกาศ** `10.10.2.0/24` + `10.10.3.0/24` → ยืนยันว่าเป็น `vlab-ts-router` แต่ **offline** |
| 5 | เคย launch แล้วได้ IP อะไร | ⚪ ไม่มี cluster ค้างใน `sky status` ยืนยันจากประวัติไม่ได้ → ยังต้องดูตอน C6 |

**สรุปฝั่ง master: พร้อม** ตัวที่ยังขาดสำหรับ "กด Start lab AWS" คือ **router ต้อง online** (SkyPilot ต้อง SSH เข้า EC2 ผ่าน subnet route ของ router) + backend บน VM (B3)

### B3 (เตรียม) — VM `webserverlab2` + inventory (2026-11-11)

VM ของ Panupong: `webserverlab2` Tailscale `100.124.148.97` / Ubuntu 24.04 / 3 vCPU / RAM 2.9 GB / swap 2.9 GB / disk ว่าง 27 GB / ใส่ SSH key แล้ว (`ssh-copy-id`) / sudo ต้องใส่รหัส → รัน playbook ด้วย `-K`

| ไฟล์ | แก้อะไร | ทำไม |
|---|---|---|
| `ansible/inventory.yml` (gitignore) | เพิ่ม group `webservice` → `webservice-1` `100.124.148.97` | `site.yml` play สุดท้ายใช้ `hosts: webservice` / Tailscale IP นี้ = `<BACKEND_TS_IP>` ใน ACL (E3) และ URL ของ Traefik (E5) |
| `ansible/inventory.yml` | comment `worker-1`, `worker-2` ออก (`hosts: {}`) **ชั่วคราว** | ทั้งสองตัว offline / task "Verify backend sees the real IP" ใน role `web-service` delegate ไป `groups['workers'][0]` ถ้า worker ไม่ตอบ deploy fail / group ว่าง → task ถูกข้าม (`when` เช็กความยาว) |
| `ansible/inventory.yml.example` | `webportal` → `webservice` | ชื่อ group ใน example ไม่ตรงกับ `site.yml` คนที่ก๊อปไปใช้จะได้ play ที่ไม่มี host |

เช็กแล้ว: `ansible-inventory --graph` เห็น `webservice-1` / `--limit webservice --list-hosts` ได้ 1 host / `ansible webservice -m ping` SSH ผ่าน (ติดแค่ sudo password = ต้อง `-K`)

ข้อควรระวังตอนรัน: role `web-service` ต่อ **master** ด้วย (slurp kubeconfig + ใช้ SkyPilot `:30880`) → `masterlab2` ต้องเปิดอยู่ (ตอนเช็ก SSH ไม่ตอบ)

---

## เรื่องที่ค้าง / ต้องถาม

- [ ] **C1** (Panupong): ดู record `*.bell-lab.space` ใน Cloudflare แล้วจดค่าเดิม
- [ ] **C2** (Pete): ยืนยัน backend ยังอยู่ที่ `vlab-web` `100.102.72.39` บน ThinkPad + ตอบคำถามที่ค้างในข้อ 0.1 ของ runbook
- [ ] **C6**: ตอนเทส baseline ดูว่า endpoint ของ lab AWS เป็น `http://10.10.2.x:…` (ยืนยันสมมติฐานของ `upstream_ok` ดูหมายเหตุใต้ A8)
- [x] ~~**router ใน tailnet** คือเครื่องไหน~~ — ยืนยันแล้ว (2026-11-11): `ip-10-10-1-234` `100.84.123.59` เป็นเครื่องเดียวที่ประกาศ route `10.10.2.0/24` / `10.10.3.0/24` (ดูจาก `tailscale status --json` บน `masterlab2`) = `<ROUTER_TS_IP>` / Pete บอกว่า SSH ผ่าน Tailscale IP ได้ (ไม่ต้องใช้ SSM ใน E4)
- [ ] **router offline** (Pete): ต้องเปิดก่อน C6 (กด Start lab AWS — SkyPilot SSH เข้า EC2 ผ่าน router) และ E
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
| A5 ✅ | `build_routes()` | RUNNING อยู่ในตาราง / PENDING, STOPPED, IP นอก ไม่อยู่ |
| A6 ✅ | route `/internal/v1/gateway/routes` | ไม่มี token 404 / token ถูกได้ JSON |
| A7 ✅ | `session_service.py`: token ไหล `_new_sky_session` → `create_fastapi_task` → `_build_aws_task` | `docker run` มี `-e VLAB_PUBLIC_URL_...` / K8s ไม่มี |
| A8 ✅ | `_run_sky_launch`: แยก `endpoints` / `upstreams` | endpoint `https://l-...` / API ไม่คืน `upstreams` |
| A9 ✅ | `main.py`: ซ่อน 2 column ในหน้า admin | หน้า admin ไม่เห็น |
| A10 ✅ | test ทั้งหมด | เก่าไม่พัง + ใหม่ผ่าน |

**B: Ansible web-service** — B1 ✅ ตัวแปร + `backend.env.j2` + assert / B2 ✅ สุ่ม `vault_lab_gateway_token` / B3 deploy ลง **VM ของ Panupong** flag ปิด (ตัดสินใจ 2026-11-11)

**C: Phase 0** — C1 จดค่า DNS `*` / C2 คุยกับ Pete / C3 จดค่า 5 ตัว / C4 เก็บสถานะ router / C5 AMI snapshot / C6 เทส baseline

**D: Cloudflare** (Panupong) — D1 tunnel `vlab-lab-gateway` / D2 hostname + DNS `*` (521 → 1033) / D3 Cache + Configuration Rule / D4 เช็ก `skypilot` ยังใช้ได้

**E: Router** (กับ Pete ช่วงไม่มีคาบ ตามลำดับ) — E1 terraform plan (ต้อง in-place) / E2 apply + ลบ rule มือ / E3 Tailscale tag + ACL / E4 SSH + inventory / E5 role `lab-gateway` / E6 รัน role (tunnel Healthy)

**F: เปิดใช้งาน** — F1 เช็ก Vite ใน music-lab / F2 เปิด flag / F3 เปิดลิงก์บนมือถือ 4G / F4 เทส G1–G12
