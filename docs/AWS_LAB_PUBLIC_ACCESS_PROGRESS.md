# บันทึกความคืบหน้า: เปิด lab บน AWS ให้คนนอก tailnet ใช้ได้

> ทำตาม [AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md](AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md) — doc นี้จดว่า **ทำอะไรไปแล้ว ตัดสินใจอะไร เจออะไรระหว่างทาง**
> เขียนต่อท้ายทุกครั้งที่จบขั้น ห้ามแก้ของเก่า (ถ้าเปลี่ยนใจให้เขียนบันทึกใหม่ว่าเปลี่ยนเพราะอะไร)
> branch: `feature/aws-dns`

---

## สถานะล่าสุด

| ส่วน | ขั้น | สถานะ |
|---|---|---|
| A: โค้ด backend | A1–A10 ✅ | **เสร็จ** (2026-11-11) |
| B: Ansible web-service | B1 ✅ B2 ✅ B3 ✅ (deploy) | B3 เหลือเทส Start AWS → รอ router online (รวมกับ C6) |
| C: เตรียม infra (Phase 0) | C1 ✅ / C2–C6 | C3–C6 รอ Pete + router online |
| D: Cloudflare | D1 ✅ D2 ✅ D3 ✅ D4 ✅ | **เสร็จ** (2026-11-11) — tunnel `vlab-lab-gateway` รอ connector (E6) |
| E: Router | E1–E6 ✅ (2026-11-12) router `t3.small` + tag `tag:vlab-router` + cloudflared/Traefik ลงแล้ว / role `lab-gateway` รันจบ `failed=0` | ถัดไป: เฟส F (Start lab AWS แล้วเปิดลิงก์จากเน็ตนอก tailnet) |
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
| 2 | `skypilot_backend_token` ใน `all.yml` | ❌ **แก้ผลเช็ก (B3)**: ตอนแรกสรุปว่าใช้ได้ แต่ผิด — token นี้ออกวันที่ 2026-10-20 (`iat` ใน token) ก่อน API server ของ `masterlab2` ถูกสร้าง (pod อายุ 41h) = เป็น token ของ server ตัวอื่น / ยิงจาก container backend ได้ **401** → ต้องสร้าง service account ใหม่บน `masterlab2` |
| 3 | config ของ SkyPilot (configmap `skypilot-api-config`) | ✅ `aws.vpc_names: vlab-ecr-pull` / `use_internal_ips: true` / `use_ssm: false` / `security_group_name: vlab-lab-instances` (= SG ใน `terraform/security_groups.tf:69`) / `remote_identity: vlab-lab-ecr-pull` (= IAM role ใน `terraform/lab_iam.tf`) |
| 3 | AWS credentials | ✅ secret `aws-credentials` มี key ครบ / access key **ตัวเดียวกับ** `skypilot_aws_access_key_id` ใน `all.yml` (sha256 ตรงกัน) / `sky status` บอก `Enabled Infra: kubernetes/in-cluster, aws` = AWS credentials ใช้ได้ |
| 4 | Tailscale บน master | ✅ `RouteAll: true` (accept-routes) / route `10.10.2.0/24`, `10.10.3.0/24` อยู่ใน table 52 ผ่าน `tailscale0` |
| 4 | ใครประกาศ route `10.10.x` | ✅ **`ip-10-10-1-234` `100.84.123.59` เป็นเครื่องเดียวที่ประกาศ** `10.10.2.0/24` + `10.10.3.0/24` → ยืนยันว่าเป็น `vlab-ts-router` แต่ **offline** |
| 5 | เคย launch แล้วได้ IP อะไร | ⚪ ไม่มี cluster ค้างใน `sky status` ยืนยันจากประวัติไม่ได้ → ยังต้องดูตอน C6 |

**สรุปฝั่ง master: พร้อม** ตัวที่ยังขาดสำหรับ "กด Start lab AWS" คือ **router ต้อง online** (SkyPilot ต้อง SSH เข้า EC2 ผ่าน subnet route ของ router) + backend บน VM (B3)

### 2026-11-11 — B3: deploy ลง VM `webserverlab2` ✅ (เหลือเทส Start AWS)

VM ของ Panupong: `webserverlab2` Tailscale `100.124.148.97` / Ubuntu 24.04 / 3 vCPU / RAM 2.9 GB / swap 2.9 GB / disk ว่าง 27 GB / ใส่ SSH key แล้ว (`ssh-copy-id`) / sudo ต้องใส่รหัส → รัน playbook ด้วย `-K`

| ไฟล์ | แก้อะไร | ทำไม |
|---|---|---|
| `ansible/inventory.yml` (gitignore) | เพิ่ม group `webservice` → `webservice-1` `100.124.148.97` | `site.yml` play สุดท้ายใช้ `hosts: webservice` / Tailscale IP นี้ = `<BACKEND_TS_IP>` ใน ACL (E3) และ URL ของ Traefik (E5) |
| `ansible/inventory.yml` | comment `worker-1`, `worker-2` ออก (`hosts: {}`) **ชั่วคราว** | ทั้งสองตัว offline / task "Verify backend sees the real IP" ใน role `web-service` delegate ไป `groups['workers'][0]` ถ้า worker ไม่ตอบ deploy fail / group ว่าง → task ถูกข้าม (`when` เช็กความยาว) |
| `ansible/inventory.yml.example` | `webportal` → `webservice` | ชื่อ group ใน example ไม่ตรงกับ `site.yml` คนที่ก๊อปไปใช้จะได้ play ที่ไม่มี host |

เช็กแล้ว: `ansible-inventory --graph` เห็น `webservice-1` / `--limit webservice --list-hosts` ได้ 1 host / `ansible webservice -m ping` SSH ผ่าน (ติดแค่ sudo password = ต้อง `-K`)

**แก้เพิ่มระหว่างรัน B3:** task "Sync web-portal source to target" exclude แค่ `venv` → `web-portal/backend/.venv` ใน WSL (~300 package รวม SkyPilot) ถูก rsync ขึ้น VM (ช้ามาก) และ `.dockerignore` ของ backend ก็ไม่ได้กัน `.venv` → หลุดเข้า image ด้วย / เพิ่ม `--exclude=.venv` ใน `roles/web-service/tasks/main.yml` และ `.venv` ใน `web-portal/backend/.dockerignore` / rsync `--delete` ไม่ลบไฟล์ที่ถูก exclude → ต้อง `rm -rf /opt/web-service/backend/.venv` บน VM เองครั้งเดียว

**ผลรัน B3 รอบแรก:** ผ่าน 36 task (Docker, sync, kubeconfig, .env, build, backend healthy, frontend, schema, seed, RBAC, query DB) / fail ที่ "Verify backend reaches the central SkyPilot API server" — network ถึง (`/api/health` จาก container ได้ `healthy`) แต่ `skypilot_backend_token` โดน **401** (ดูข้อ 2 ในตารางเช็ก master) → สร้าง service account `vlab-backend` บน dashboard ของ `masterlab2` แล้วใส่ token ใหม่ใน `all.yml` แล้วรันซ้ำ (ไม่ต้อง seed อีก)

**แก้แล้ว (2026-11-11):** สร้าง service account `vlab-backend` (Admin) ในแท็บ **Service Accounts** ของ dashboard `masterlab2` (ไม่ใช่แท็บ Users — user ธรรมดาไม่มี token) / ใส่ใน `all.yml` แล้ว / ยิง `/api/health` พร้อม token ได้ `user = vlab-backend (sa-1620…)` / token หมดอายุ **2027-11-11** (1 ปี) — ครบแล้วต้องสร้างใหม่

**ผลรัน B3 รอบสุดท้าย (2026-11-11):** `ok=38 changed=7 failed=0` / เช็กหลัง deploy:

| เช็ก | ผล |
|---|---|
| `GET /api/internal/v1/gateway/routes` ไม่มี token / token มั่ว | **404** ทั้งคู่ (flag ปิด = ซ่อน endpoint) ✅ |
| `/health` | `healthy` / `database: connected` ✅ |
| frontend `http://100.124.148.97/` | 200 ✅ |
| `backend/.env` บน VM | `LAB_GATEWAY_ENABLED=false` / `LAB_GATEWAY_DOMAIN=bell-lab.space` / token ยาว ≥32 ✅ |
| migration | `alembic current` = `20261111_01 (head)` (มี `gateway_token`, `upstreams`) ✅ |
| backend ↔ SkyPilot `masterlab2` | task "Verify backend reaches the central SkyPilot API server" ผ่าน ✅ |
| กด Start lab AWS ได้ `10.10.2.x` | ⏳ ยังเทสไม่ได้ — router (`100.84.123.59`) offline รอ Pete (= C6) |

**เจอระหว่างทาง — DNS ใน pod ของ `masterlab2` พัง:** `cloudflare-tunnel` CrashLoopBackOff + Cloudflare ขึ้น Down / สาเหตุ role `k3s-server` เขียน DNS ของเครื่อง **ณ ตอนรัน** (`192.168.1.1` เน็ตบ้าน) ลง `/etc/rancher/k3s/resolv.conf` ตายตัว พอ PC ย้ายเน็ต (VirtualBox NAT ได้ DNS ตาม PC → `172.20.10.1`) CoreDNS ยังส่งไป `192.168.1.1` → timeout / กระทบ SkyPilot ด้วย (ต้อง resolve `ec2.*.amazonaws.com`) / แก้ด่วน: `ansible-playbook ... --limit master --tags k3s-server -K` → pod resolve ได้ cloudflared Running / task สุดท้ายของ role (`Store registry push credentials for scan Jobs`) fail เพราะ `all.yml` ไม่มี `registry_users` — ใช้กับระบบสแกน image ที่ปิดอยู่ ไม่เกี่ยว Phase 1 / **ยังค้าง:** เปลี่ยนเน็ตอีกจะพังอีก — ทางถาวรคือให้ role override DNS เป็น `1.1.1.1` / `8.8.8.8` ได้

**เจอระหว่างทาง — `masterlab2` ค้างทั้ง VM (2 รอบ):** อาการ "SkyPilot down" ไม่ใช่ pod พัง / kernel log `clocksource: Long readout interval ... 157319597175` (11:00:02) = VM ถูกหยุดไป ~157 วินาที → k3s `i/o timeout` ที่ `:6443` → `NodeNotReady` / ข้างใน VM ไม่มี OOM, swap ไม่ถูกใช้, CPU idle 93% → น่าจะมาจาก **PC** (RAM ไม่พอเมื่อเปิด 2 VM + WSL + Docker Desktop หรือเครื่อง sleep) / รอบสองระหว่าง restart k3s ping ไม่ได้เลย (Tailscale `tx 8580 rx 0`) ต้อง reset VM / หลังบูต SkyPilot ใช้ 1–2 นาทีกว่าจะ `2/2 Running` (probe `connection refused` ช่วงแรกเป็นปกติ) / ป้องกัน: Power → plugged in → sleep = Never, ดู RAM ใน Task Manager, ถ้าไหวให้ master 4 GB (SkyPilot request 2Gi limit 4Gi ใช้จริง ~1.6Gi แต่ VM มี ~2.7 GB)

ข้อควรระวังตอนรัน: role `web-service` ต่อ **master** ด้วย (slurp kubeconfig + ใช้ SkyPilot `:30880`) → `masterlab2` ต้องเปิดอยู่

### 2026-11-11 — C1 + D1–D4: Cloudflare (ประตูหน้าของลิงก์ lab) ✅

**ส่วนนี้ทำอะไร:** เตรียมทางเข้าฝั่ง internet ให้ลิงก์ `https://l-<token>-<port>.bell-lab.space` — นักศึกษานอก tailnet พิมพ์ลิงก์นี้แล้วต้องวิ่งไปถึง router ใน AWS ได้ โดย **ไม่เปิดพอร์ตใดๆ ของ router สู่ internet** (router เป็นฝ่ายต่อออกไปหา Cloudflare เอง)

```
นักศึกษา (4G / บ้าน)
   │ https://l-abc...-5173.bell-lab.space
   ▼
Cloudflare edge ── DNS `*` (Proxied) → Cache Rule / Configuration Rule ทำงานตรงนี้
   │ tunnel `vlab-lab-gateway` (router ต่อออกมาเอง tcp 7844)
   ▼
[router EC2]  cloudflared ──► 127.0.0.1:8081 Traefik ──► lab EC2 10.10.2.x:5173
   └──────────── ส่วน E (ยังไม่ได้ทำ รอ Pete) ────────────┘
```

ทั้งหมดทำบน dashboard Cloudflare (Panupong เจ้าของ zone) ไม่แตะเครื่องไหน และ **ยังไม่มีผลกับผู้ใช้** จนกว่า E6 จะลง cloudflared บน router + F2 เปิด flag

#### C1 — จดค่า DNS `*` เดิมก่อนแก้

- **ทำไม:** ขั้น D2 ต้องลบ / แก้ record นี้ ถ้ามีอะไรพังต้องถอยกลับได้
- **ผล:** `*` = A `198.54.117.242` Proxied — เช็ก RDAP แล้ว IP อยู่ในช่วง `198.54.112.0/20` ของ **Namecheap, Inc.** = ค่าเริ่มต้นตอนจดโดเมน (หน้า parking) ไม่ได้ชี้เครื่องเรา (ตอน 2026-11-09 `l-test-8080` ได้ 521 เพราะ server Namecheap ไม่รู้จัก hostname นี้)
- hostname ที่ใช้งานจริงมี record ของตัวเองทุกตัว (`skypilot`, `pete-skypilot`, `focus-skypilot`, `skypilot-masterlabtop`, `skypilot-bigboss`, `skypilot-film`, `www`) → record ที่ระบุชื่อตรงชนะ `*` เสมอ แก้ `*` จึงไม่กระทบใคร
- **ถอยกลับ:** ลบ `*` ตัวใหม่ → สร้าง A `*` → `198.54.117.242` Proxied

#### D1 — สร้าง tunnel `vlab-lab-gateway`

- **tunnel คืออะไร:** ท่อที่ **cloudflared ฝั่งเรา dial ออกไปหา Cloudflare** แล้ว Cloudflare ส่ง request ของผู้ใช้กลับมาตามท่อนั้น → router ไม่ต้องมี inbound port / ไม่ต้องรู้ public IP / เปลี่ยน IP ก็ไม่พัง
- **ทำไมสร้างใหม่ ไม่ใช้ tunnel เดิม:** tunnel `skypilot-*` เป็นของ SkyPilot dashboard แต่ละคน แยกกันทำให้ลบ / ปิด / หมุน token ของ lab gateway ได้โดยไม่กระทบ SkyPilot
- **token** (`vault_lab_gateway_tunnel_token` ใน `all.yml`) = กุญแจที่ cloudflared ใช้พิสูจน์ว่าเป็น connector ของ tunnel นี้ ใครได้ token ไปก็รับ traffic ของ tunnel ได้ → เก็บใน `all.yml` (gitignore) / role `lab-gateway` (E5) จะเขียนลงไฟล์ env สิทธิ์ 0600 บน router
- **ไม่รันคำสั่ง `docker run ...` ที่ dashboard ให้มา** เพราะ cloudflared ต้องอยู่บน router (ไม่ใช่ PC) และให้ Ansible ลงแบบ systemd + ปักเวอร์ชัน
- tunnel id `de38c1ed-9bf2-4705-b31a-0f4419b8565f`

#### D2 — Published application `*.bell-lab.space` → `HTTP 127.0.0.1:8081`

- **ทำหน้าที่:** บอก Cloudflare ว่า request ที่ host ตรง `*.bell-lab.space` ให้ส่งเข้า tunnel นี้ แล้ว cloudflared ปลายทางส่งต่อไปที่ `127.0.0.1:8081`
- **ทำไม `*` (wildcard):** ลิงก์ lab สุ่มชื่อใหม่ทุก session (`l-<token>-<port>`) สร้าง record ทีละตัวไม่ทัน → ใช้ `*` ตัวเดียวรับทุกชื่อ แล้วให้ Traefik แยกเองว่าชื่อไหนไป EC2 ตัวไหน (จากตาราง `build_routes()` ของ backend)
- **ทำไม `127.0.0.1:8081`:** cloudflared กับ Traefik อยู่บน router เครื่องเดียวกัน คุยผ่าน localhost / Traefik จะผูกพอร์ต `8081` ไว้ที่ `127.0.0.1` เท่านั้น (E5) → คนนอกยิงตรงเข้า Traefik ไม่ได้ ต้องผ่าน Cloudflare อย่างเดียว
- **ทำไม `HTTP` ไม่ใช่ HTTPS:** ช่วง cloudflared → Traefik อยู่ในเครื่องเดียว / HTTPS ฝั่งนักศึกษา Cloudflare ถือ cert `*.bell-lab.space` ให้ (Universal SSL ครอบแล้ว)
- **ต้องลบ A `*` ก่อน:** record A เปลี่ยน type เป็น tunnel ไม่ได้ และชื่อเดียวกันมีได้แบบเดียว
- **ผ่านเมื่อ:** `curl https://l-test-8080.bell-lab.space/` เปลี่ยนจาก **521** (ไปหา server Namecheap) เป็น **`error code: 1033`** (ถึง tunnel ใหม่แล้ว แต่ยังไม่มี cloudflared ต่ออยู่ — ปกติจนถึง E6) ✅

#### D3 — Rule 2 ตัวสำหรับ `l-*`

wildcard `*` แบบ Proxied ได้ setting ทั้ง zone มาด้วย ซึ่งเหมาะกับเว็บทั่วไป แต่ **ทำ lab พัง** เพราะ lab เป็น dev server (Vite / code-server) ที่ไฟล์เปลี่ยนตลอดและใช้ JavaScript / WebSocket หนัก → ทำ rule ยกเว้นเฉพาะลิงก์ lab

เงื่อนไขของทั้งสอง rule: `http.request.full_uri wildcard "https://l-*.bell-lab.space/*"` = จับเฉพาะ host ที่ขึ้นต้น `l-` (ลิงก์ lab) / `skypilot.*` และตัวอื่นไม่โดน (รันบุ๊คเขียนเป็น `starts_with(http.host, "l-") and ends_with(...)` ผลเท่ากัน แต่แบบ wildcard กรอกผ่านช่อง builder ได้เลย)

| Rule | ตั้งอะไร | ถ้าไม่ตั้งจะเกิดอะไร |
|---|---|---|
| **Cache Rule** `lab gateway no cache` | **Bypass cache** | Cloudflare เก็บไฟล์ `.js` / `.css` ไว้ที่ edge → นักศึกษาแก้โค้ดแล้ว Vite ส่งไฟล์ใหม่ แต่ได้ไฟล์เก่าจาก cache / HMR ไม่อัปเดต / ร้ายสุด: lab ของคนหนึ่งถูก cache แล้วส่งให้อีกคนที่ได้ URL เดียวกัน |
| **Configuration Rule** `lab gateway no rewrite` | ปิด **Rocket Loader** | Rocket Loader เขียน `<script>` ใหม่ให้โหลดแบบ async → ลำดับ script ของ Vite / code-server เพี้ยน หน้าขาวหรือ error |
| | ปิด **Email Obfuscation** | Cloudflare แทนข้อความที่หน้าตาเหมือนอีเมลใน HTML ด้วย script ของตัวเอง → เนื้อหา lab / โค้ดตัวอย่างเพี้ยน |
| | ปิด **Automatic HTTPS Rewrites** | เปลี่ยนลิงก์ `http://` ใน HTML เป็น `https://` → ลิงก์ภายใน lab ที่ตั้งใจเป็น http (หรือไปหา host อื่น) เสีย |

- dashboard เตือน **"This rule may not apply to your traffic"** เพราะเช็กแค่ว่ามี record ชื่อ `l-.bell-lab.space` ตรงตัวไหม (ไม่มี) → เลือก **Ignore and deploy** ถูกแล้ว เพราะ traffic `l-*` วิ่งผ่าน `*` ที่ Proxied อยู่ / **ไม่** เลือก "Create a new proxied DNS record" (จะได้ record เกินที่ไม่ใช้)
- ยังไม่ได้ดู: **Bot Fight Mode** (ถ้าเปิด อาจ challenge request ของ Vite / WebSocket — Free plan ยกเว้นราย hostname ไม่ได้ ต้องเทส G2 / G4 ตอน F4) และ **WebSockets = On** (ค่าเริ่มต้น)

#### D4 — เช็กว่าของเดิมไม่พัง

- `skypilot.bell-lab.space` ตอบ HTTP 530 (= error 1033) **เหมือนก่อนแก้** — tunnel `skypilot-new-master` ไม่มี connector อยู่แล้วเดิม ไม่เกี่ยวกับการแก้ `*` ✅

### 2026-11-11 — E1 + E3 (เตรียม): Terraform + Tailscale ACL ให้ Pete รัน ✅ (เขียนเสร็จ ยังไม่ apply)

**ทำไมเราเขียน แต่ Pete รัน:** Terraform state อยู่ในเครื่อง Pete (`terraform/providers.tf` ไม่มี remote backend) และ tailnet เป็นของ Pete (ต้องใช้ API token ของ admin) → เราเตรียมไฟล์บน branch ให้ Pete รันอย่างเดียว

#### E1 — Terraform (แก้ 2 ไฟล์ / เปิดเพิ่มอย่างเดียว ไม่ปิดของเดิม)

| ไฟล์ / resource | เปลี่ยน | ทำไม |
|---|---|---|
| `router.tf` `aws_instance.ts_router` | `t3.micro` → **`t3.small`** | RAM 1 GB → 2 GB ให้พอ Tailscale + cloudflared + Traefik |
| | + `credit_specification { cpu_credits = "unlimited" }` | T3 เป็น unlimited อยู่แล้ว เขียนให้เห็นว่าตั้งใจ — credit หมดกลางคาบ = CPU ถูกบีบ = proxy ช้าทั้งห้อง |
| `security_groups.tf` `ts_router_lab_web` (egress router → lab) | `8080` → **`3000–9999`** | Traefik ต้องส่งต่อไปได้ทุกพอร์ตที่ backend ยอมแจกลิงก์ (`LAB_GATEWAY_PORT_MIN..MAX`) / ครอบ rule 5173 / 8443 ที่ Pete เคยเพิ่มด้วยมือ |
| `ts_router_cloudflared` (**ใหม่**, egress tcp 7844 → 0.0.0.0/0) | | cloudflared ต่อ tunnel แบบ `--protocol http2` ใช้ tcp 7844 (udp 7844 ครอบด้วย `ts_router_udp_all`, tcp 443 ด้วย `ts_router_https` อยู่แล้ว) |
| `lab_web_from_router` (**ใหม่**, ingress lab ← router tcp 3000–9999) | | SkyPilot เปิด ingress ให้เองตาม `ports:` ของ task แต่เป็นราย cluster / ช่วงที่รัน → rule นี้ทำให้ gateway ไม่ต้องพึ่งพฤติกรรมนั้น |

- ไม่ต้องแก้ `variables.tf`: ขนาดเครื่อง / พอร์ตในโปรเจกต์นี้เขียนตรงในไฟล์อยู่แล้ว / ตัวแปรมีแค่ค่าที่ต่างตามคนรัน (`region`, `aws_profile`, `ssh_public_key_path`)
- เช็กแล้ว (ใน WSL บนสำเนาไฟล์ ไม่แตะ state / `.terraform` ของใคร): `terraform fmt -check` ✅ / `terraform init -backend=false && terraform validate` ✅ (Terraform v1.17.1)
- **plan ที่ Pete ต้องเห็น:** `aws_instance.ts_router` **update in-place** (`instance_type`, `credit_specification`) / `ts_router_lab_web` replace (เปลี่ยนพอร์ต = สร้างใหม่ ปกติ) / `ts_router_cloudflared`, `lab_web_from_router` create — **ถ้า router ขึ้น `must be replaced` ให้หยุด** (router ใหม่ = Tailscale หาย)
- **ผลข้างเคียง:** เปลี่ยน instance type = router stop/start ไม่กี่นาที → lab AWS ของทุกคนเข้าไม่ได้ช่วงนั้น (EC2 ไม่ตาย) / public IP ของ router อาจเปลี่ยน (ไม่มีผล: Tailscale + cloudflared ต่อออกเอง)

#### E3 — Tailscale ACL + tag (แก้ `.example` 2 ไฟล์)

| เพิ่มอะไร | ทำหน้าที่ |
|---|---|
| `vlab-tags.tsv.example`: `100.84.123.59 tag:vlab-router` | `tailscale-acl.sh apply` ติด tag ให้ router ผ่าน API |
| `tagOwners`: `tag:vlab-router` | ประกาศ tag (ไม่ประกาศ = validate ไม่ผ่าน) |
| กฎ 5: `tag:vlab-router` → `100.124.148.97:8000` tcp | ให้ Traefik ดึงตาราง route จาก backend ของ Panupong — ช่องทางเดียวที่ router เริ่มคุยใน tailnet ได้ |
| `autoApprovers.routes` `10.10.2.0/24`, `10.10.3.0/24` → `tag:vlab-router` | route ของ router ยัง approved หลังติด tag (ไม่งั้น SkyPilot ของ **ทุก master** เข้า EC2 ไม่ได้) |
| test ของ `tag:vlab-router` | accept `100.124.148.97:8000` / deny `:22`, `:5432` ของ backend + ssh / k3s / SkyPilot ของ server, ssh / lab ของ worker, push registry — Tailscale รัน test ทุกครั้งที่ validate ไม่ผ่าน = ไม่ยอม save |

**ทำไมติด tag:** ตอนนี้ router เป็นเครื่องของ Pete = `autogroup:member` → ได้ `*:*` แต่ router เป็นเครื่องเดียวที่รับ traffic จาก internet (cloudflared) ถ้าถูกเจาะผ่าน Traefik / cloudflared จะกระโดดไปทุกเครื่องใน tailnet ได้ / ติด tag แล้ว router ทำได้แค่ที่เขียนไว้

**ไม่พังของใคร:**
- ACL มีแต่ `accept` → เพิ่มกฎไม่ปิดของเดิม / เครื่องไม่ติด tag (`masterlab2`, `webserverlab2`, เครื่อง Pete, backend ของ Pete) ยัง `*:*` ตามกฎ member
- master ทั้งของ Pete และ Panupong ไป EC2 ผ่าน subnet route: ต้นทางคือ master (member / `tag:vlab-server`) router แค่ส่งต่อ → ไม่ต้องมีกฎ src router
- SSH เข้า router ยังได้ (ต้นทาง member)
- **ข้อจำกัด:** Traefik ดึงตารางจาก backend ได้ตัวเดียว (URL ใน `traefik.yml`) = backend ที่เปิด `LAB_GATEWAY_ENABLED` ได้ทีละตัว / backend อื่นปล่อย flag ปิด ทำงานเหมือนเดิม / ย้าย backend = แก้ IP ในกฎ 5 + test + URL ใน role

**สิ่งที่ Pete ต้องทำตอน apply:** ไฟล์จริง (`tailscale/vlab-acl.hujson`, `vlab-tags.tsv`) อยู่ในเครื่อง Pete (gitignore) และ script **ทับ policy ทั้งก้อน** → Pete ต้อง **ต่อส่วนที่เพิ่มเข้าไฟล์ของตัวเอง** (ดู `git diff` ของ `.example`) ห้าม `cp .example` ทับ / ถ้าไฟล์ Pete มี `autoApprovers` อยู่แล้วให้รวม key `routes` เข้าด้วยกัน
- เช็กแล้ว: HuJSON ของ `.example` parse ได้ (keys `tagOwners`, `acls`, `autoApprovers`, `ssh`, `tests`) — validate + test จริงทำโดย `tailscale-acl.sh plan` ของ Pete (ต้องใช้ API)

#### ขั้นตอนของ Pete (~1 ชม. ตอนไม่มีใครเปิด lab AWS ค้าง / ตามลำดับ)

1. **AMI snapshot** router แบบ **`--no-reboot`** (C5) + จดค่าข้อ 0.2 / 0.3 ของรันบุ๊ค (C3 / C4) — ค่าเริ่มต้นของ AWS ตอนสร้าง AMI คือ **reboot เครื่อง** ไม่ติ๊ก No reboot = router ดับไม่กี่นาที
2. `git fetch origin && git checkout feature/aws-dns && git pull` → `cd terraform && terraform plan -out gateway.tfplan` → อ่าน plan ตามด้านบน (มีอย่างอื่นโผล่ = ทักก่อน) → `terraform apply gateway.tfplan` / state อยู่เครื่อง Pete (gitignore) สลับ branch ไม่หาย / เช็กแล้ว: `origin/main` ไม่มีการแก้ `terraform/` / `tailscale/` ที่ branch นี้ไม่มี → plan ไม่ย้อนงานใคร
3. ลบ rule 5173 / 8443 ที่เพิ่มด้วยมือ (คำสั่งในรันบุ๊ค 1B.4) → `terraform plan` อีกรอบต้อง `No changes`
4. ต่อส่วนที่เพิ่มใน `.example` (ดูด้วย `git diff origin/main -- tailscale/...`) เข้า `tailscale/vlab-acl.hujson` + `vlab-tags.tsv` ของตัวเอง → `./script/tailscale-acl.sh plan` (validate + test + diff) → `apply`
5. เช็ก: admin console router มี `tag:vlab-router` + route ยัง approved / บน `masterlab2` `tailscale status` ยังเห็น route / บน router `nc -zv -w3 100.124.148.97 8000` ได้ และ `nc -zv -w3 100.77.79.61 22` ไม่ได้ / SSH เข้า router ยังได้
6. เทส R1–R3 (รันบุ๊ค 1F.3)

#### เจอทีหลัง: SSH เข้า router หลังติด tag + สิทธิ์ของเรา (กระทบ E4)

- **Tailscale IP = แค่ทาง (network) ไม่ใช่การยืนยันตัวตน** ปลายทางยังต้อง auth อีกชั้น ขึ้นกับว่า router ใช้ SSH แบบไหน:

| router ใช้ | Pete หลังติด tag | เรา (Panupong) |
|---|---|---|
| **sshd ปกติ** (ผ่าน Tailscale IP) | เข้าได้ (ต้นทาง member → กฎ `*:*`) | ต้องมี **public key ของเรา** ใน `~ubuntu/.ssh/authorized_keys` → ส่ง `~/.ssh/id_ed25519.pub` ให้ Pete ใส่ |
| **Tailscale SSH** (`tailscale up --ssh`) | **เข้าไม่ได้** — ส่วน `"ssh"` ของ policy อนุญาตแค่ `autogroup:self` เครื่องติด tag ไม่ใช่ self ของใคร | ตอนนี้ก็เข้าไม่ได้ (router เป็น self ของ Pete ไม่ใช่ของเรา) |

- ถ้าเป็น Tailscale SSH ต้องเพิ่มในส่วน `"ssh"` ของไฟล์จริง: `{"action": "accept", "src": ["autogroup:admin"], "dst": ["tag:vlab-router"], "users": ["ubuntu", "root"]}` (+ ใส่บัญชีของ Panupong ใน `src` ถ้าไม่ใช่ admin) / ทางสำรองเข้า router คือ SSM
- เช็กตอน router เปิด: `ssh ubuntu@100.84.123.59` → เข้าได้ = รัน Ansible ได้ / `Permission denied (publickey)` = sshd ขาด key / ขึ้นลิงก์ login หรือ `tailnet policy does not permit` = Tailscale SSH ขาดกฎ
- user `ubuntu` บน EC2 sudo ไม่ต้องใช้รหัส → รัน role บน router ไม่ต้อง `-K`
- ถาม Pete แล้วใน PDF (ข้อ 4)

#### เอกสารส่ง Pete

ทำ PDF 4 หน้า (HTML → PDF ด้วย Edge headless ฟอนต์ Leelawadee UI) อธิบายงาน lab gateway + diagram, ตาราง Terraform / Tailscale ว่าแก้อะไรใช้ทำอะไร, ทำไมไม่พังของใคร, ขั้นตอน checklist 5 ข้อ (รวม AMI `--no-reboot`, คำเตือน "must be replaced = หยุด" / "ห้าม cp .example ทับ"), วิธีถอยกลับ, คำถาม 4 ข้อ (router เริ่มต่อเครื่องอื่นไหม / พอร์ต 3000–9999 / public IP เปลี่ยน / ใช้ sshd หรือ Tailscale SSH) — ไม่มี token / รหัสในเอกสาร / ไฟล์อยู่นอก repo (ไม่ commit)

### 2026-11-12 — E1 apply เอง (state ย้ายขึ้น S3) ✅

**ทำไมเราทำเองได้:** เดิม state อยู่ในเครื่อง Windows ของ Pete เครื่องเดียว ใคร plan จากเครื่องอื่น Terraform จะไม่เห็นของเดิมแล้วพยายามสร้างใหม่หมด (42 resource) Pete เลยเปิด PR `chore/terraform-s3-state` (merge แล้ว):
- `backend.tf`: state อยู่ที่ S3 `vlab-tfstate-568318158381` key `aws/terraform.tfstate` + `use_lockfile` (ตอน apply เขียนไฟล์ `.tflock` ใน S3 กันสองคน apply พร้อมกัน ไม่ต้องมี DynamoDB) → ต้องใช้ Terraform ≥ 1.10 (เรามี 1.17.1 ใน WSL)
- `experiment.tf`: `aws_key_pair.pete` ignore `public_key` ไม่งั้นรันจากเครื่องเราจะลบ key pair แล้วสร้างใหม่จาก `~/.ssh/id_ed25519.pub` ของเรา
- bucket สร้างด้วยมือ (ไม่อยู่ใน Terraform กัน `destroy` ลบ state ตัวเอง) / IAM user ของเราคือ `Dev-mawn`

**ขั้นตอนที่ทำ (WSL):**
1. `git merge origin/main` เข้า `feature/aws-dns` (ได้ `backend.tf` / ไม่ชนกับ `router.tf` / `security_groups.tf`)
2. ใช้ key เดิมของ Windows (profile `default` = `Dev-mawn` เช็กด้วย `aws sts get-caller-identity`) — Terraform ใน WSL หา `~/.aws` ของ Linux เลยชี้ไฟล์ Windows ด้วย `export AWS_SHARED_CREDENTIALS_FILE=/mnt/c/Users/Panup/.aws/credentials` + `AWS_CONFIG_FILE=/mnt/c/Users/Panup/.aws/config`
3. `terraform init -reconfigure -backend-config="profile=default"` (`-reconfigure` = ตั้ง backend ใหม่ตาม `backend.tf` ไม่ย้าย/ไม่ทับ state / ห้ามใช้ `-migrate-state` หรือ `state push`)
4. `terraform plan -var aws_profile=default -out gateway.tfplan` → **`2 to add, 2 to change, 0 to destroy`** ตรงตามที่เขียน (router `t3.micro → t3.small` in-place / egress `ts_router_lab_web` 8080 → 3000–9999 / + egress 7844 / + lab ingress 3000–9999 จาก router) / `credit_specification` ไม่ขึ้นเพราะเป็น `unlimited` อยู่แล้ว / `public_ip → null` เพราะ router stopped
5. **AMI สำรอง** `vlab-ts-router-before-gateway` (`ami-0cea83b0b6deedcd8`, snapshot `snap-0d337b828a87a1e27` 8 GB) สร้างตอน router stopped (ไม่ต้อง No reboot) → ลบหลังเทส F ผ่าน (ดูเรื่องค้าง)
6. `terraform apply gateway.tfplan` → **`2 added, 2 changed, 0 destroyed`** (router แก้ 25 วินาที)

**เช็กผ่าน AWS CLI หลัง apply:** router `t3.small` / credits `unlimited` / rule ใหม่ `sgr-01fb84998047577ee` (7844) + `sgr-02ed6e740e90fc3c1` (lab ← router 3000–9999) / `sgr-0e758343bf22fd55a` = 3000–9999

**เจอระหว่างทาง:**
- **router ถูก start เอง:** เปลี่ยน instance type ต้อง stop → แก้ → start และ AWS provider start ให้หลังแก้เสมอ แม้เดิมจะ stopped → router `running` ตั้งแต่ 22:05 UTC / public IP ใหม่ `13.212.8.84` (เดิม `13.229.183.32` — ไม่มี Elastic IP, Tailscale ไม่ได้ใช้ IP นี้) / ใน tailnet `ip-10-10-1-234` `100.84.123.59` กลับมา online
- **rule ที่เพิ่มด้วยมือ (Terraform ไม่รู้จัก ไม่ลบให้):**
  - router SG egress `sgr-0214b0ed415e3f4bc` (5173) + `sgr-03918a3d7ae1ed40f` (8443) → อยู่ในช่วง 3000–9999 แล้ว ซ้ำ → **ลบแล้ว (E2)** ด้วย `aws ec2 revoke-security-group-egress --security-group-rule-ids ...` / egress ที่เหลือ: 443, 80, udp ทั้งหมด, 22 → lab, 7844, 3000–9999 → lab
- **E2 เช็ก (ต่อด้านล่าง):** `terraform plan` รอบสอง = ไม่มี resource change (`-detailed-exitcode` = 0) มีแค่ output `router_public_ip "" → "13.212.8.84"` (state ยังจำ IP ตอน stopped / ค่า output ไม่ใช่ของจริงบน AWS ไม่ต้อง apply)
  - lab SG ingress 5173 / 8443 / 8080 จาก `0.0.0.0/0` ไม่มี description → น่าจะเป็น SkyPilot เปิดตาม `ports` ของ task (ไม่ใช่ของเรา **ไม่ลบ**) / ผลจริงเข้าได้แค่จากใน VPC เพราะ lab อยู่ private subnet ไม่มี public IPv4 และ rule เป็น IPv4 อย่างเดียว

### 2026-11-12 — E3 Tailscale ACL + tag router / E4 SSH เข้า router ✅

**ก่อนทำ:** ลอง `ssh ubuntu@100.84.123.59` ได้ `tailscale: tailnet policy does not permit you to SSH to this node` = router ใช้ **Tailscale SSH** (ตอบคำถามข้อ 4 ที่ถาม Pete) → ส่ง public key ให้ Pete ไม่ช่วย ต้องแก้ที่ policy / Pete ให้ role Admin ใน tailnet `minecopper.55@gmail.com` กับ `panupong.suttikasem@gmail.com` แล้ว

**ทำไมไม่ cp `.example`:** `tailscale-acl.sh` ส่ง `tailscale/vlab-acl.hujson` ขึ้นไป **ทับ policy ทั้งก้อน** และ policy จริงมีของที่ `.example` ไม่มี (grant `tag:friend-master` → `10.10.2.0/24`, `10.10.3.0/24` ของฟิลม์ / คอมเมนต์ IP ของ cluster Pete) → copy policy จริงจาก JSON editor มาเป็น `vlab-acl.hujson` แล้วเพิ่มของเรา / `vlab-tags.tsv` ใส่แค่ router บรรทัดเดียว (`.example` มี IP ของ cluster อื่น ใส่ไป = ติด tag ผิดเครื่อง) / ทั้งสองไฟล์ + `tailscale/backup/` gitignore ไม่ commit เก็บไว้ใช้ rollback / แก้ครั้งหน้า

**ที่เพิ่ม (5 จุด ไม่แตะของเดิม):**

| เพิ่ม | ทำหน้าที่ |
|---|---|
| `tagOwners` `tag:vlab-router` | ต้องประกาศ tag ก่อนติดให้เครื่อง |
| acls ข้อ 5 router → `100.124.148.97:8000` | ติด tag แล้ว router ไม่ใช่ member (ไม่ได้ `*:*`) → Traefik ดึงตาราง route จาก backend ไม่ได้ = 404 ทุกลิงก์ / ให้แค่ 8000 |
| `autoApprovers` `10.10.2.0/24` / `10.10.3.0/24` | route ยัง approved หลังติด tag (SkyPilot / master ของฟิลม์ยังเข้า EC2 ได้) |
| `ssh` accept `autogroup:admin` → `tag:vlab-router` users `ubuntu`, `root` | เครื่องติด tag ไม่ใช่ `autogroup:self` ของใคร กฎ check เดิมใช้ไม่ได้ / accept ไม่ใช่ check เพราะ Ansible ต่อ ssh หลายรอบ |
| tests router | accept `:8000` / deny backend `:22` `:5432`, server `:22` `:6443`, worker `:22` `:8080`, registry `:5001` |

**ขั้นตอน (WSL, root ของ repo):** `sudo apt install -y jq` → API access token อายุ 1 วัน (Settings → Keys, script ถามแบบไม่ขึ้นจอ) → `./script/tailscale-acl.sh plan` (backup `acl-20261112-051551` / validate + tests ผ่าน / diff มีแต่ `+` 5 จุด / tag: `ip-10-10-1-234` → `tag:vlab-router`) → `apply` (backup `tailscale/backup/acl-20261112-051655.hujson` = จุด rollback)

**เช็กก่อน apply ว่าใครพึ่ง route AWS:** `masterlab2`, `ThinkPad`, PC ทีม = ไม่ติด tag (member `*:*`) / `master`, `vlab-web` = `tag:vlab-server` (`*:*`) / master ฟิลม์ = grant เดิม → ไม่มีใครเสียสิทธิ์

**ผลหลัง apply:**
- router `ip-10-10-1-234` tag = `tag:vlab-router` online / PrimaryRoutes ยังเป็น `10.10.2.0/24`, `10.10.3.0/24` ✅ (autoApprovers ทำงาน)
- **E4:** `ssh ubuntu@100.84.123.59` เข้าได้ ✅ (2 vCPU, RAM 1905 MB = `t3.small` จริง) / เพิ่ม group `aws_router` → `aws-router-1` `100.84.123.59` `ansible_user: ubuntu` ใน `inventory.yml` (gitignore) / `ansible -i inventory.yml aws_router -m ping` = `pong` ✅
- ยังไม่ได้เทส router → backend `:8000` (`webserverlab2` ปิดอยู่) → เช็กตอนลง E5
- **ถอยกลับ:** `./script/tailscale-acl.sh rollback tailscale/backup/acl-20261112-051655.hujson` + เอา tag ออกจาก router ใน console
- เพิ่มกฎ ssh admin → `tag:vlab-router` ลง `tailscale/vlab-acl.hujson.example` ด้วย (ตอน E3 เตรียม มีแค่ใน PDF ของ Pete)

### 2026-11-12 — E5: Ansible role `lab-gateway` ✅

**role นี้ทำอะไร:** ลง 2 service บน router ให้ลิงก์ `l-<token>-<port>.bell-lab.space` วิ่งถึง lab ได้

| service | ทำหน้าที่ |
|---|---|
| `cloudflared-lab` | ต่อ tunnel `vlab-lab-gateway` ออกไปหา Cloudflare (ขาออก tcp 7844 / `--protocol http2` เพราะ SG ไม่ได้เปิด udp 7844 ของ QUIC) → Cloudflare ส่ง `*.bell-lab.space` เข้ามาที่ `127.0.0.1:8081` ตาม Published application (D2) / router ไม่ต้องเปิดพอร์ตขาเข้าเลย |
| `traefik` | ฟัง `127.0.0.1:8081` (localhost อย่างเดียว เข้าได้ทาง cloudflared เท่านั้น) / ทุก 5 วิ ดึงตาราง route จาก `http://100.124.148.97:8000/api/internal/v1/gateway/routes` พร้อม header `X-Gateway-Token` → ส่งต่อ Host ที่รู้จักไป `10.10.2.x:<port>` / Host ที่ไม่รู้จัก = 404 |

**ไฟล์:** `ansible/roles/lab-gateway/` (`defaults`, `tasks`, `handlers`, `templates/traefik.yml.j2`, `traefik.service.j2`, `cloudflared-lab.service.j2`) ตามโครงในรันบุ๊ค 1E.4 / `site.yml` เพิ่ม play `aws_router` (ไม่รัน `common` / `tailscale` เพราะ Tailscale ของ router ตั้งด้วยมือ ห้าม role ไปแตะ flag subnet route) / `inventory.yml.example` เพิ่ม group `aws_router` / `all.yml.example` เพิ่ม `vault_lab_gateway_tunnel_token`

**ตัดสินใจ / ต่างจากรันบุ๊ค:**
- ปักเวอร์ชันที่ออกมา ≥ 2 สัปดาห์ (ณ 2026-11-12): **Traefik `3.7.16`** (2026-10-20, เช็ก sha256 จากไฟล์ checksums ของ release) / **cloudflared `2026.10.5`** (2026-10-27, sha256 `149d1ec4…ac0ed` จาก release) / binary ไม่ใช้ Docker = ประหยัด RAM และไม่ไปแก้ iptables ของ router
- URL backend ดึงจาก `hostvars` ของ group `webservice` (IP + `webservice_api_port`) → เปลี่ยนเครื่อง backend แก้ inventory ที่เดียว
- เพิ่ม `assert` ตอนต้น: token ≥ 32 ตัว + มี tunnel token (ลืมใส่ = หยุดก่อนแตะเครื่อง) / `no_log` ทุก task ที่มี token
- เพิ่มเช็ก `cloudflared` ต่อ Cloudflare ได้ (`Registered tunnel connection` ใน journal)
- จำกัด RAM: Traefik 384M / cloudflared 256M (`MemoryMax`) กัน gateway กิน RAM จน Tailscale (ทางเข้า AWS ของทั้งทีม) ล่ม

**เช็กตอนท้ายของ role (กันพัง router):** Traefik ตอบ 404 กับ host มั่ว / log ไม่มี provider error (= ดึงตาราง route ได้ — backend ปิด, token ไม่ตรง หรือ ACL `:8000` ไม่เปิด จะ fail ตรงนี้) / `tailscale status` ยังขึ้น / `ip_forward = 1` / chain `FORWARD` ของ iptables เหมือนก่อนลง

**เช็กแล้ว:** `ansible-playbook site.yml --syntax-check` ผ่าน / `--list-tasks --limit aws_router --tags lab-gateway` ได้ 21 task / ยังไม่ได้รันกับเครื่องจริง: router ถูก stop (User initiated 2026-11-12 08:22 UTC) และต้องเปิด `webserverlab2` (backend) ด้วย

### 2026-11-12 — E6: รัน role จริง ✅ + บั๊กที่เจอระหว่างทาง

ลำดับ error ที่เจอ (แต่ละรอบไปได้ไกลกว่าเดิม = เส้นทางทีละช่วงใช้ได้):

| รอบ | error ที่ขั้น "traefik can read routes" | สาเหตุ / แก้ |
|---|---|---|
| 1 | `context deadline exceeded` | VM `webserverlab2` ปิด (offline 16 ชม.) → เปิด VM / ตอนนี้ service ลงครบแล้ว: `traefik` + `cloudflared-lab` active, tunnel 4 connections, `curl https://l-test-8080.bell-lab.space/` = **404** (เดิม 1033) = อินเทอร์เน็ต → Cloudflare → tunnel → Traefik ใช้ได้, RAM เหลือ 1455 MB |
| 2 | `received non-ok response code: 404` | **ต่อ backend ได้แล้ว** (ACL ข้อ 5 router → `:8000` ใช้ได้จริง) แต่ backend ยัง `LAB_GATEWAY_ENABLED=false` (flag ปิด / token ผิด = 404 เหมือนไม่มี endpoint) → ใส่ `webservice_lab_gateway_enabled: true` เป็น host var ของ `webservice-1` ใน `inventory.yml` (ไม่ใช้ `-e` กันรันครั้งหน้าลืมแล้ว flag กลับเป็น false) → รัน `--limit webservice --tags web-service -K` (รอบแรก fail ที่อ่าน kubeconfig เพราะ `masterlab2` ปิด → เปิดแล้วผ่าน `failed=0`) |
| 3 | ผ่าน แต่ขั้น "cloudflared connected" fail | **บั๊กของ role:** นับ `Registered tunnel connection` ใน journal 3 นาทีล่าสุด รันซ้ำโดยไม่ restart = บรรทัดเก่าเกินช่วง → 0 ทั้งที่ `/ready` ตอบ `readyConnections: 4` → แก้ให้ปัก `--metrics 127.0.0.1:20241` (`lab_gateway_cloudflared_metrics`) แล้วเช็ก `GET /ready` = 200 + `readyConnections > 0` |
| 4 | `cannot decode configuration data: routers cannot be a standalone element` | **บั๊กของ backend (A5):** ไม่มี lab AWS รัน → `build_routes` คืน `{"http": {"routers": {}, "services": {}}}` ซึ่ง Traefik 3.7 decode ไม่ได้ (ตารางไม่อัปเดต) / ลองกับ traefik v3.7.16 จริงใน WSL (HTTP server ปลอมส่ง body): `{"http":{"routers":{},...}}` ❌, `{"http":{}}` ❌, **`{}` ✅**, ตาราง 1 route ✅ → แก้ `build_routes` คืน `{}` เมื่อไม่มี route (รวมกรณีทุกพอร์ตถูกข้าม) + แก้ test (`test_empty`, `test_empty_table`, helper `router_names`, เพิ่ม `test_only_bad_upstreams_is_empty`) |

- test: Docker Desktop ในเครื่องปิด → รันบน `webserverlab2` แทน (เครื่องทดสอบ): สร้าง DB แยก `virtual_lab_test` ใน `virtual_lab_db` (ของแอปคือ `virtual_lab` ไม่แตะ / conftest บังคับชื่อลงท้าย `_test`) → `docker run --rm --network host -v /opt/web-service/backend:/src:ro virtual-lab-backend python -m pytest -p no:cacheprovider` (image มี pytest 8.3.4) → **`test_lab_gateway.py` ผ่าน 84/84** / ทั้งชุด (ยกเว้น `tests/monitor`) 647 ผ่าน 5 fail = `test_auth_infra.py` ทั้ง 5 + `tests/monitor` collect ไม่ได้ เพราะใช้ `Path(__file__).parents[4]` หาไฟล์ `k8s/` ระดับ repo ซึ่ง VM มีแค่ `backend/` (ไม่เกี่ยวกับงานนี้)
- รอบ 5 (`--tags lab-gateway` หลัง deploy backend ใหม่): **"traefik can read routes" ผ่าน** ✅ (บั๊ก `{}` หาย) / "cloudflared connected" ยัง fail ทั้งที่ `/ready` = `{"status":200,"readyConnections":4}` — cloudflared ตอบ `content-type: text/plain` → `uri` ไม่สร้าง `.json` → แก้เป็น `content | from_json` (ลองเงื่อนไขกับ body ตัวอย่างแล้ว: 4 connections = true, 503/0 = false)
- **รอบ 6: `ok=21 changed=0 failed=0`** ✅ ผ่านทุกเช็ก (404 host มั่ว / ดึง route ได้ / tunnel ต่อ / tailscale up / ip_forward=1 / FORWARD chain ไม่เปลี่ยน) / RAM router เหลือ 1452 MB (เกณฑ์ ≥ 800) Traefik ใช้ ~14 MB cloudflared ~15 MB / `https://l-test-8080.bell-lab.space/` = 404 จาก Traefik
- เกณฑ์ R1–R4 ของรันบุ๊ค (เทสจริงกับ lab) ทำในเฟส F

### 2026-11-12 — F0: Vite ใน music-lab ไม่รับ hostname ของ gateway ❌ (ต้องแก้ image)

**ทำไมต้องเช็ก:** Vite ≥ 5.4.12 (แพตช์ความปลอดภัย ม.ค. 2025) ตอบ "Blocked request. This host is not allowed" ถ้า Host ไม่ใช่ localhost / IP / ที่อยู่ใน `server.allowedHosts` → ลิงก์ `l-<token>-5173.bell-lab.space` เปิดไม่ได้ (G4)

**ผล:**
- `music-lab/client/package.json` = `"vite": "^5.4.0"` ไม่มี lockfile → build เมื่อไหร่ได้ 5.4 ล่าสุดตอนนั้น / image ใน ECR `vlab/music-lab-ide:lab-01` push 2026-10-11 → ได้ 5.4.x ที่มีการบล็อกแน่นอน
- `vite.config.js` ไม่มี `allowedHosts` (มีแค่ `host: true` ซึ่งเป็น boolean ไม่ถูกนับเป็น host ที่อนุญาต)
- **env `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` ที่ backend ส่ง (A7) ใช้ไม่ได้:** โหลด vite จาก npm มา grep แล้ว 5.4.11 / 5.4.12 / 5.4.21 (ล่าสุดของ 5.4) / 6.0.9 ไม่มีชื่อนี้ใน `dist` เลย — `getAdditionalAllowedHosts` ใน 5.4.21 อ่านแค่ `server.host` (string), `hmr.host`, `preview.host`, `server.origin` → ข้อสมมติในรันบุ๊ค D10 ผิดสำหรับ 5.4
- `vite.config.js` ถูก bake อยู่ใน image (`skypilot/Dockerfile`: `COPY client/ /app/client/`) → แก้แล้วต้อง build + push ECR ใหม่ (`build-images.yml` บนเครื่อง registry → `ecr-sync`) / เครื่อง `register` offline 5 วัน และ `all.yml` เราไม่มี `registry_users`
- กระทบแค่พอร์ต 5173 (Vite) — 8443 (code-server) / 8080 (server) ไม่เกี่ยว เทส G1–G3, G5–G9, G11 ทำต่อได้

### 2026-11-12 — F1–F3 + เทสที่ไม่ต้องเปิด lab ✅

ก่อนเทส VM `webserverlab2` ค้างอีกรอบ (SSH timeout, `tailscale status` `rx 0`, Traefik `Provider error` 19 ครั้ง / 2 นาที) → reset ใน VirtualBox แล้วกลับมาปกติ / ระหว่าง backend ล่ม ลิงก์ที่ไม่มี lab ยังได้ 404 จาก Traefik (ใช้ตารางล่าสุด)

| เทส | ทำยังไง | ผล |
|---|---|---|
| F1 เปิด flag | `webservice_lab_gateway_enabled: true` ใน inventory (ทำตอน E6) / `.env` บน VM = `LAB_GATEWAY_ENABLED=true`, `LAB_GATEWAY_DOMAIN=bell-lab.space` | ✅ |
| F2 ตาราง route | `curl` endpoint พร้อม token จาก WSL | `{}` ✅ (ไม่มี lab AWS) / แก้รันบุ๊ค 1F.2 ให้เป็น `{}` แล้ว |
| G8 ไม่มี / ผิด token | `curl` ไม่ใส่ header / `X-Gateway-Token: wrong` | 404 / 404 ✅ |
| G6 token มั่ว | `https://l-aaaaaaaaaaaaaaaa-8443.bell-lab.space/` จากอินเทอร์เน็ต | 404 ✅ |
| R1 router ยัง route | `tailscale status` บน router / master เห็น PrimaryRoutes ของ router | `10.10.2.0/24`, `10.10.3.0/24` ✅ |
| Traefik หลัง backend กลับมา | `journalctl -u traefik` 15 วิล่าสุด | `Provider error` 0 ✅ |
| G9 router เข้าเครื่องอื่นไม่ได้ | จาก router `/dev/tcp` ไป master `:22` `:6443`, backend `:22` `:5432`, backend `:8000` | blocked ×4, **`:8000` OPEN** ✅ ตรง ACL |

**เตรียมเทสที่ต้องเปิด lab (R2, G1–G5, G11):** DB บน VM มี user 5 / course 3 / lab 6 แต่ **ทุก lab เป็น `run_target = KUBERNETES`** ไม่มี lab AWS / lab "OOP with Spring Boot" ใช้ image `skypilot/music-lab:lab-01` ซึ่งมีใน ECR (`skypilot/music-lab:lab-01` push 2026-10-19) / config AWS ของ backend ครบ (`ECR_REGISTRY_HOST`, `AWS_LAB_AMI`, `AWS_INSTANCE_TYPE=m7i-flex.large`) → ต้องเปลี่ยน lab นี้เป็น `AWS` ก่อน Start
- เปลี่ยนแล้ว (2026-11-12, DB ของ VM ทดสอบ): `update labs set run_target='AWS' where id='03a18386-1558-4bcf-9399-4b79cc1ae22b'` / ports ของ image = 8080, 5173, 8443 (อยู่ในช่วง 3000–9999 ทั้งหมด) / **คืนค่า:** `update labs set run_target='KUBERNETES' where id='03a18386-…'`

### 2026-11-12 — R2 + G1 + G2/G4 รอบแรก: Start lab บน AWS ผ่าน gateway ✅ (5173 ติด Vite ตามคาด)

- กด Start ไม่ได้ทีแรก: "User already has a running session" = session ตัวอย่างจาก seed (`36b6b716…`, pod `lab-se301-sophia`, endpoints `localhost`, หมดอายุ 2026-11-11 แต่ยัง RUNNING) → ตั้งเป็น STOPPED ใน DB ทดสอบ
- login ด้วย user seed `sophia.dav@dome.tu.ac.th` (รหัสตาม `app/seeds/seed.py`)
- หน้ารอ lab ไม่ใช่ WebSocket: frontend ส่ง HTTP request เดียว backend ถือไว้จน lab พร้อมแล้วตอบ (`LabDetail.tsx`) / `setInterval` ใน `LabLoader.tsx` แค่ animation → ระหว่างรอห้ามรีเฟรช
- ระหว่างรอ PC เข้าเว็บไม่ได้ชั่วคราว: VM ปกติ แต่ Tailscale ฝั่ง PC เห็น VM `offline` / relay → กลับมาเอง / Traefik มี `Provider error` ช่วงนั้น (ล่าสุด 15:19:04 UTC) หลังจากนั้น 0
- **R2 ✅** launch ผ่าน: cluster `music-lab-1794496777` (`m7i-flex.large` 2 vCPU / 8 GB — Pete ตั้งไว้ใน commit `72f9a12` เพราะบัญชี AWS free plan สร้างได้แค่บางชนิด, ~$0.12/ชม.) / image `skypilot/music-lab:lab-01`
- **G1 ✅** หน้าเว็บแสดงลิงก์ `https://l-<token>-{5173,8080,8443}.bell-lab.space` / ตาราง route บน router ได้ 3 router → `http://10.10.2.73:{5173,8080,8443}`
- 8443 (code-server) ✅ เปิดหน้า login ของ code-server ผ่าน gateway ได้ / รหัส = `musiclab` (ค่าเริ่มของ `music-lab/skypilot/run.sh` `${IDE_PASSWORD:-musiclab}` backend ไม่ได้ส่ง `IDE_PASSWORD`) — **ข้อสังเกตความปลอดภัย:** ทุก lab รหัสเดียวกันและอยู่ใน repo → กุญแจจริงเหลือแค่ token ในลิงก์ (80 bit) ควรสุ่มรหัสต่อ session ภายหลัง
- 8080 ✅ ได้หน้า "Not Found — The requested URL was not found on the server" = หน้า 404 ของ Flask (server ของ music-lab) ตอบเอง → gateway ส่งถึงแล้ว แค่ `/` ไม่มี route (API อยู่ `/api/...`) / ถ้า gateway ไม่รู้จัก host จะได้ 404 ข้อความสั้นของ Traefik ไม่ใช่หน้านี้
- 5173 ❌ **"Blocked request. This host ("l-…-5173.bell-lab.space") is not allowed"** ตรงกับที่คาดใน F0 → รอแก้ `allowedHosts` + build image

### 2026-11-12 — สรุปปัญหาทั้งหมดตอนรัน Ansible (B3 → E6)

รายละเอียดของแต่ละข้ออยู่ในบันทึก B3 / E3 / E6 ด้านบน ตารางนี้ไว้ดูภาพรวม

| # | ช่วง | อาการ | สาเหตุ | แก้ | ประเภท |
|---|---|---|---|---|---|
| 1 | B3 | playbook ไม่เจอเครื่อง web | `site.yml` ใช้ group `webservice` แต่ `.example` เขียน `webportal` | เปลี่ยนชื่อ group | config |
| 2 | B3 | rsync copy `.venv` ของเครื่องเราไป VM | sync task / `.dockerignore` ไม่ตัด `.venv` | `--exclude=.venv` + `.dockerignore` | บั๊ก role `web-service` |
| 3 | B3, E6 | `DEPRECATION WARNING: The connection's stdin object is deprecated` | คำเตือนของ Ansible รุ่นนี้ตอน rsync | ไม่ต้องแก้ | ปกติ |
| 4 | B3 | "Verify backend reaches SkyPilot" ได้ 401 | token ออกโดย server ตัวอื่น (2026-10-20) | Service Account ใหม่บน `masterlab2` | config |
| 5 | B3 | pod บน master resolve ชื่อไม่ได้ (SkyPilot / cloudflared ล่ม) | role `k3s-server` ฝัง DNS ของเน็ตตอนติดตั้ง (`192.168.1.1`) | รัน `--tags k3s-server` ใหม่ / **ทางถาวรยังค้าง** | บั๊ก role `k3s-server` |
| 6 | B3 | VM master ค้างตอน restart k3s | VM ค้าง ~157 วิ (RAM ของ PC / sleep) | reset VM | สภาพแวดล้อม |
| 7 | B3 | task scan ของ `k3s-server` fail | `all.yml` ไม่มี `registry_users` | **ยังค้าง** (ไม่เกี่ยวงานนี้) | config |
| 8 | E4 | SSH เข้า router ไม่ได้ (`tailnet policy does not permit`) | router ใช้ Tailscale SSH (ดู ACL ไม่ดู key) | กฎ `ssh` admin → `tag:vlab-router` | config |
| 9 | E6 | `--check` fail ที่ `Install traefik binary` (`Source ... does not exist`) | โหมดซ้อมไม่ดาวน์โหลดจริง ขั้นแตกไฟล์เลยหาไฟล์ไม่เจอ | ไม่ต้องแก้ | ปกติ |
| 10 | E6 | `context deadline exceeded` | VM backend ปิด | เปิด VM | สภาพแวดล้อม |
| 11 | E6 | backend ตอบ 404 | `LAB_GATEWAY_ENABLED=false` | host var `webservice_lab_gateway_enabled: true` | config |
| 12 | E6 | web-service อ่าน kubeconfig ไม่ได้ | VM master ปิด | เปิด VM | สภาพแวดล้อม |
| 13 | E6 | "cloudflared connected" fail ทั้งที่ tunnel ต่อ | นับบรรทัด log ช่วง 3 นาที รันซ้ำแล้วบรรทัดเก่าเกินช่วง | ถาม `/ready` ตรง ๆ | บั๊ก role `lab-gateway` (ขั้นเช็ก) |
| 14 | E6 | Traefik `routers cannot be a standalone element` | ไม่มี lab → backend คืน `{"http":{"routers":{}}}` Traefik 3.7 decode ไม่ได้ | คืน `{}` + แก้ test | **บั๊ก backend (A5)** |
| 15 | E6 | `/ready` ตอบ 200 แต่ยัง fail | cloudflared ตอบ `text/plain` → `uri` ไม่สร้าง `.json` | `content \| from_json` | บั๊ก role `lab-gateway` (ขั้นเช็ก) |
| 16 | E6 | รัน test ที่ใช้ DB ในเครื่องไม่ได้ | Docker Desktop ปิด | รันบน `webserverlab2` กับ DB แยก `virtual_lab_test` (84/84) | สภาพแวดล้อม |

**แยกประเภท:** บั๊กในโค้ดแอปมี **ตัวเดียว (#14)** — ระบบพังจริง (ตาราง route ไม่อัปเดต) / #13, #15 เป็นบั๊กในขั้นเช็กของ role ระหว่างนั้น cloudflared / tunnel ทำงานปกติ ไม่กระทบใคร / ที่เหลือเป็น config, เครื่องปิด หรือพฤติกรรมปกติของ Ansible

**บทเรียน:**
- เช็กก่อนรันว่า master / web / router ขึ้นใน `tailscale status` — 3 รอบ fail เพราะเครื่องปิด (#10, #12, รวมถึง router ถูก stop ระหว่างวัน)
- เช็กท้าย role คุ้ม: #14 ไม่มี unit test ตัวไหนจับได้ (test เช็กแค่ว่า backend คืนรูปแบบที่เราคิดเอง ไม่เคยลองกับ Traefik จริง) แต่ role จับได้ → ต่อไปรูปแบบที่ส่งให้โปรแกรมอื่นอ่าน ให้ลองกับโปรแกรมตัวจริงด้วย
- เช็กต้องถูกทั้งรอบแรก (เพิ่ง restart) และรอบรันซ้ำ (ไม่ restart) — #13 / #15 ผ่านแค่กรณีแรก
- error ที่เปลี่ยนทุกรอบ = คืบหน้า: timeout → 404 → decode error = ผ่าน network → ACL → token → รูปแบบข้อมูล ทีละช่วง

---

## เรื่องที่ค้าง / ต้องถาม

- [x] **C1** (2026-11-11): record `*.bell-lab.space` เดิม = **A `198.54.117.242` Proxied** TTL Auto (IP เดียวกับ root `bell-lab.space` = หน้า parking ของ Namecheap ไม่มีอะไรใช้จริง) / ไม่มี AAAA ของ `*` / hostname ที่ใช้งานมี record ของตัวเองหมด: `skypilot` (Tunnel `skypilot-new-master`), `pete-skypilot`, `focus-skypilot`, `skypilot-masterlabtop` (Tunnel), `skypilot-bigboss`, `skypilot-film` (CNAME `*.cfargotunnel.com`), `www` (CNAME parking) → แก้ `*` ไม่กระทบตัวไหน / **ถอยกลับ:** ลบ `*` ที่ชี้ tunnel แล้วสร้าง A `*` → `198.54.117.242` Proxied
- [ ] **C2** (Pete): ยืนยัน backend ยังอยู่ที่ `vlab-web` `100.102.72.39` บน ThinkPad + ตอบคำถามที่ค้างในข้อ 0.1 ของ runbook
- [ ] **C6**: ตอนเทส baseline ดูว่า endpoint ของ lab AWS เป็น `http://10.10.2.x:…` (ยืนยันสมมติฐานของ `upstream_ok` ดูหมายเหตุใต้ A8)
- [x] ~~**router ใน tailnet** คือเครื่องไหน~~ — ยืนยันแล้ว (2026-11-11): `ip-10-10-1-234` `100.84.123.59` เป็นเครื่องเดียวที่ประกาศ route `10.10.2.0/24` / `10.10.3.0/24` (ดูจาก `tailscale status --json` บน `masterlab2`) = `<ROUTER_TS_IP>` / Pete บอกว่า SSH ผ่าน Tailscale IP ได้ (ไม่ต้องใช้ SSM ใน E4)
- [ ] **router offline** (Pete): ต้องเปิดก่อน C6 (กด Start lab AWS — SkyPilot SSH เข้า EC2 ผ่าน router) และ E
- [ ] **DNS ของ k3s บน `masterlab2`** ฝังค่า DNS ของเน็ตตอนรัน → เปลี่ยนเน็ต PC แล้ว pod resolve ไม่ได้ (SkyPilot launch AWS fail + cloudflared ล่ม) / ทางด่วน: รัน `--limit master --tags k3s-server -K` ใหม่ / ทางถาวร: เพิ่มตัวแปร override เป็น `1.1.1.1` / `8.8.8.8` ใน role `k3s-server` / `k3s-agent`
- [ ] `inventory.yml`: เอา comment `worker-1` / `worker-2` ออกเมื่อ worker กลับมา online (ไม่งั้น task whoami ไม่ได้เช็ก)
- [ ] `all.yml` ไม่มี `registry_users` → task "Store registry push credentials for scan Jobs" ของ `k3s-server` fail (ระบบสแกน image — ไม่เกี่ยว Phase 1) ใส่เมื่อจะใช้ scan
- [ ] SkyPilot service account `vlab-backend` บน `masterlab2`: token หมดอายุ **2027-11-11** / token ถูกส่งในแชตแล้ว → ถ้าใช้ master นี้ต่อจริงให้สร้างใหม่แล้วลบตัวเก่า / ลบ **user** `vlab-backend` (แท็บ Users รหัส `1234`) ที่สร้างผิดแท็บ
- [x] **D1** (2026-11-11): สร้าง tunnel `vlab-lab-gateway` id `de38c1ed-9bf2-4705-b31a-0f4419b8565f` (CNAME target = `de38c1ed-9bf2-4705-b31a-0f4419b8565f.cfargotunnel.com`) / token ใส่ใน `all.yml` เป็น `vault_lab_gateway_tunnel_token` แล้ว (gitignore) — token ถูกส่งในแชต ถ้าจะใช้จริงระยะยาวให้ refresh token ใน dashboard
- [x] **D2** (2026-11-11): ลบ A `*` เดิม แล้วเพิ่ม Published application ใน tunnel: `*.bell-lab.space` → `HTTP 127.0.0.1:8081` (= Traefik บน router ที่ E5 จะผูกไว้ localhost อย่างเดียว) / `curl https://l-test-8080.bell-lab.space/` ได้ **`error code: 1033`** (เดิม 521) = ถึง tunnel ใหม่แล้ว ยังไม่มี connector ✅
- [x] **D3** (2026-11-11): Cache Rule `lab gateway no cache` = **Bypass cache** / Configuration Rule `lab gateway no rewrite` = ปิด Rocket Loader, Email Obfuscation, Automatic HTTPS Rewrites / เงื่อนไขทั้งคู่ `http.request.full_uri wildcard "https://l-*.bell-lab.space/*"` (ใช้แทน `starts_with(http.host, "l-") and ends_with(...)` ในรันบุ๊ค ผลเท่ากัน กรอกผ่าน builder ได้) / dashboard เตือน "may not apply" เพราะไม่มี record ชื่อ `l-` ตรงตัว → Ignore and deploy (ทราฟฟิกวิ่งผ่าน `*` ที่ Proxied อยู่แล้ว) / ยังไม่ได้เช็ก Bot Fight Mode + WebSockets
- [x] **D4** (2026-11-11): `skypilot.bell-lab.space` ตอบ HTTP 530 (= error 1033 เหมือนก่อนแก้ — tunnel `skypilot-new-master` ไม่มี connector อยู่แล้วเดิม) ไม่ได้รับผลจากการแก้ `*` ✅
- [x] ~~**รอ Pete**~~ (2026-11-12): Pete ให้ Admin → เรา apply ACL เอง / ข้อ 4 = Tailscale SSH / ที่ยังไม่ได้คำตอบ: 4 คำถาม (router เริ่มต่อเครื่องอื่นไหม / พอร์ต 3000–9999 / public IP เปลี่ยน / sshd หรือ Tailscale SSH) — **AMI + Terraform apply เราทำเองแล้ว** เพราะ Pete ย้าย state ขึ้น S3 (PR `chore/terraform-s3-state`, 2026-11-12)
- [ ] **ลบ AMI สำรอง** `vlab-ts-router-before-gateway` หลังเทส F ผ่าน: Deregister AMI **และ** Delete snapshot (snapshot ≈ $0.05/GB/เดือน ไม่ลบ = เสียเงินต่อ)
- [x] **E4** (2026-11-12) ทำผ่านกฎ Tailscale SSH แทน key — ให้ Pete ใส่ public key ของเรา (`~/.ssh/id_ed25519.pub`) ใน `~ubuntu/.ssh/authorized_keys` ของ router หรือเพิ่มกฎ Tailscale SSH → `ssh ubuntu@100.84.123.59` ต้องเข้าได้ → เพิ่ม group `aws_router` ใน inventory
- [ ] **C2** ไม่จำเป็นแล้วสำหรับการเทส (backend อยู่บน VM ของ Panupong) — ยังต้องถาม Pete เรื่องพอร์ต 3000–9999 และ public IP ของ router
- [x] ~~ลบ `FILM.md` ออกจาก repo~~ — ย้าย checklist (สถานะ + เกณฑ์ผ่าน A–F) มาไว้ที่ "แผนขั้นย่อยของเฟส 1" ท้าย doc นี้แล้ว (2026-11-11)
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

**B: Ansible web-service** (dev)

| ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|
| B1 ✅ | ตัวแปรใน `web-service/defaults` + `backend.env.j2` + `all.yml.example` + assert ใน `tasks/main.yml` | render ด้วย Ansible จริงได้ค่าถูก 5 เคส |
| B2 ✅ | สุ่ม `vault_lab_gateway_token` ใส่ `group_vars/all.yml` | ยาว 64 ตัวอักษร |
| B3 ✅ (deploy) | deploy ลง VM ของ Panupong `webserverlab2` `100.124.148.97` **flag ปิด** | `curl` ได้ 404 ✅ / กด Start AWS ได้ `10.10.2.x` → เทสพร้อม C6 (รอ router) |

**C: เตรียม infra (Phase 0)**

| ขั้น | ทำอะไร | ใคร |
|---|---|---|
| C1 ✅ | จดค่า DNS `*.bell-lab.space` เดิม (A `198.54.117.242` Proxied) | Panupong |
| C2 | ~~ยืนยัน backend อยู่ที่ `vlab-web`~~ (ไม่จำเป็นแล้ว ใช้ VM ของ Panupong) — ยังต้องถามเรื่องพอร์ต 3000–9999 + public IP ของ router | Panupong + Pete |
| C3 | จดค่า 5 ตัวในข้อ 0.2 ของรันบุ๊ค (IP, instance ID, SG ID) | Pete |
| C4 | เก็บสถานะ router (ข้อ 0.3) | Pete |
| C5 | AMI snapshot ของ router | Pete |
| C6 | เทส baseline: กด Start AWS แล้วจดเวลา + ยืนยัน endpoint `10.10.2.x` | dev (router ต้อง online) |

**D: Cloudflare** (Panupong)

| ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|
| D1 ✅ | tunnel `vlab-lab-gateway` + token ลง `all.yml` | tunnel ขึ้นใน dashboard |
| D2 ✅ | Published application `*` → `HTTP 127.0.0.1:8081` + DNS `*` ชี้ tunnel | `curl l-test-8080...` 521 → **1033** |
| D3 ✅ | Cache Rule + Configuration Rule ของ `l-*` | rule ขึ้นใน dashboard |
| D4 ✅ | เช็ก `skypilot.bell-lab.space` | เหมือนเดิม |

**E: Router** (กับ Pete ช่วงไม่มีคาบ **ตามลำดับ**)

| ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|
| E1 ✅ | Terraform: `router.tf` (`t3.small` + cpu credits unlimited) + `security_groups.tf` (router → lab 3000–9999, egress 7844, lab รับ 3000–9999 จาก router) แล้ว `plan` | router ขึ้น **update in-place** (ขึ้น replace = หยุด) |
| E2 ✅ | `terraform apply` + ลบ rule 5173 / 8443 ที่เพิ่มด้วยมือ | R1–R3 ผ่าน + plan รอบสอง `No changes` |
| E3 ✅ | Tailscale: tag `tag:vlab-router` + ACL router → backend `:8000` + autoApprovers แล้ว `plan` / `apply` | router มี tag, route ยัง approved, R1–R3 ผ่าน |
| E4 ✅ | SSH key ให้ router + group `aws_router` ใน inventory | `ansible aws_router -m ping` ผ่าน |
| E5 ✅ | role `lab-gateway` (cloudflared + Traefik ปักเวอร์ชัน + sha256) | `--check --diff` ผ่าน |
| E6 ✅ | รัน role จริง | tunnel **Healthy**, RAM เหลือ ≥ 800MB, R1–R4 ผ่าน |

**F: เปิดใช้งาน**

| ขั้น | ทำอะไร | ผ่านเมื่อ |
|---|---|---|
| F1 | เช็ก Vite ใน image music-lab (ข้อ 1F.0) | รองรับ env — ไม่รองรับต้องแก้ `vite.config.js` แล้ว build ใหม่ |
| F2 | เปิด flag `-e webservice_lab_gateway_enabled=true` | `curl` ตาราง route ได้ `{"routers":{}}` |
| F3 | กด Start AWS แล้วเปิดลิงก์ `l-...` บนมือถือ 4G | เปิด lab ได้ |
| F4 | เทส G1–G12 จดผลลงข้อ 9 ของรันบุ๊ค | G1–G11 ผ่าน → ตั้ง flag `true` ถาวร |
