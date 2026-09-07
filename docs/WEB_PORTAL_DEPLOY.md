# Web Portal Deployment Design

> สถานะ: **อนุมัติแล้ว — implement เสร็จ รอ deploy จริง**
> branch: `feature/web-portal-deploy`
> วันที่: 2026-09-04

## 1. เป้าหมาย

Host `web-portal/` (FastAPI + React + Postgres) บนเครื่องแยกที่ `100.68.206.79` แบบ standalone
docker-compose โดยไม่ join k3s cluster

**การเข้าถึง: Tailscale IP ตรงๆ** — ไม่ใช้ domain, ไม่ใช้ Cloudflare Tunnel
เข้าที่ `http://100.68.206.79` จากเครื่องที่อยู่ใน tailnet เดียวกัน

> ถ้าวันหน้าอยากได้ HTTPS หรือเปิดสู่อินเทอร์เน็ต เพิ่ม `tailscale serve` / `tailscale funnel`
> ได้ภายหลังโดยไม่ต้องรื้อ architecture — โครงนี้ไม่ปิดทาง

## 2. Topology ใหม่

ชุด IP ใหม่มาแทนของเดิม**ทั้งหมด** เครื่อง `thinkpad` (100.93.121.17) เลิกเป็น master
กลับไปเป็นแค่เครื่อง control ที่รัน `ansible-playbook`

| Role | Hostname | Tailscale IP | หน้าที่ |
|---|---|---|---|
| master | `master` | 100.81.134.35 | k3s server (control-plane) |
| worker | `worker-1` | 100.73.174.96 | k3s agent — รัน lab workload |
| registry | `registry-host` | 100.86.105.18 | container registry |
| webportal | `webportal` | 100.68.206.79 | **ใหม่** — docker-compose (db + backend + frontend) |

SSH user ของทั้ง 4 เครื่อง: `room111` (become: sudo)
Tailscale: **up ครบทั้ง 4 เครื่องแล้ว** (ยืนยัน 2026-09-04)

```
        ผู้ใช้ในtailnet ── http://100.68.206.79 ──┐
                                                  │
                                         ┌────────▼─────────┐
                                         │  webportal       │  100.68.206.79
                                         │  ┌────────────┐  │
                                         │  │ frontend   │  │  nginx  :80
                                         │  │ backend    │  │  uvicorn :8000
                                         │  │ postgres   │  │  :5432 (internal)
                                         │  └─────┬──────┘  │
                                         └────────┼─────────┘
                                                  │ kubeconfig ผ่าน tailscale0
                                         ┌────────▼─────────┐
                                         │  master (k3s)    │  100.81.134.35:6443
                                         └────────┬─────────┘
                                                  │
                             ┌────────────────────┴──────────────┐
                        worker-1 100.73.174.96          registry 100.86.105.18
```

port ที่เปิดบน webportal (ผูกกับ `tailscale0` เท่านั้น ไม่ใช่ `0.0.0.0`):

| port | service |
|---|---|
| 80 | frontend (nginx) |
| 8000 | backend (uvicorn) |
| — | postgres ไม่ publish ออกนอก container network |

## 3. Gap analysis — สิ่งที่ยังขาดในโค้ดปัจจุบัน

นี่คือส่วนที่สำคัญที่สุด งานนี้**ไม่ใช่แค่เขียน Ansible role** เพราะ artifact สำหรับ deploy ยังไม่มี

| # | สิ่งที่ขาด | สถานะปัจจุบัน | ต้องทำ |
|---|---|---|---|
| G1 | `backend/Dockerfile` | ไม่มี | เขียนใหม่ (python:3.12-slim + `requirement.txt` + uvicorn) |
| G2 | `frontend/Dockerfile` | ไม่มี | เขียนใหม่ (multi-stage: node build → nginx serve) |
| G3 | service ใน compose | มีแค่ `db` (postgres:17-alpine) | เพิ่ม `backend`, `frontend` |
| G4 | compose สำหรับ production | ไฟล์เดียวใช้ dev — เปิด port 5432 ออกนอก, password `password` | แยก `docker-compose.prod.yml` — ปิด port db, ใช้ secret จริง |
| G5 | kubeconfig ให้ backend | `.env.example` ตั้ง `K8S_ENABLED=True`, `KUBECONFIG_PATH=./kubeconfig.yaml` | Ansible ต้อง fetch kubeconfig จาก master แล้ว **แก้ `server:` เป็น `https://100.81.134.35:6443`** (ไม่ใช่ 127.0.0.1) |
| G9 | group `webportal` ใน inventory + play ใน `site.yml` | ไม่มี | เพิ่ม |
| G6 | ~~ค่า R2~~ | ประกาศใน `settings.py` แต่ **ไม่ถูกใช้ที่ไหนเลย** (ไม่มี `boto3`) ไฟล์ใช้ `STORAGE_ROOT` บน filesystem แทน | **ไม่ต้องทำ** — ตัดออกจาก `.env` ที่ render |
| G7 | `SECRET_KEY` | เป็น placeholder | generate ใหม่ เก็บใน Vault |
| G10 | `CORS_ORIGINS_STR` | ชี้ `localhost:3000,localhost:5173` | ต้องเพิ่ม `http://100.68.206.79` ไม่งั้น frontend เรียก API ไม่ได้ |
| G11 | `VITE_API_URL` | ชี้ `http://localhost:8000/api` | ต้องเป็น `http://100.68.206.79:8000/api` — ค่านี้ถูก **bake ตอน build** ไม่ใช่ runtime จึงต้องส่งเป็น build arg |
| G12 | `backend/storage/` | เก็บไฟล์เอกสารแลปบน filesystem | ต้องเป็น volume ไม่งั้นไฟล์หายทุกครั้งที่ rebuild — และต้อง `--exclude` จาก rsync ที่ใช้ `delete: yes` |
| G13 | backend ตายถ้า DB ไม่พร้อม | `lifespan` เรียก `sys.exit(1)` เมื่อ `check_db_connection()` fail | compose ต้องใช้ `depends_on: condition: service_healthy` ไม่ใช่ `depends_on` เปล่า |
| G14 | ชื่อ host ชนชื่อ group | `master`/`webportal` เป็นทั้งชื่อ group และชื่อ host | เปลี่ยนชื่อ host เป็น `master-1` / `webportal-1` |
| G8 | role `web-portal` | ไม่มี | สร้างใหม่ |
| G9 | group `webportal` ใน inventory + play ใน `site.yml` | ไม่มี | เพิ่ม |

### เหตุผลที่ G5 สำคัญ

`backend/kubeconfig.yaml.example` มีอยู่แล้ว แปลว่า backend คุยกับ k3s เพื่อสร้าง lab pod
kubeconfig ที่ k3s เขียนออกมาจะชี้ `server: https://127.0.0.1:6443` เสมอ ถ้า copy ไปเครื่อง
webportal ตรงๆ backend จะเรียกหาตัวเองแล้วพัง — ต้อง rewrite host เป็น Tailscale IP ของ master
และ master ต้องรัน k3s ด้วย `--tls-san` ไม่งั้น TLS cert จะไม่ครอบ IP นั้น

> ✅ [`roles/k3s-server/tasks/main.yml:38`](../ansible/roles/k3s-server/tasks/main.yml) **มี `--tls-san {{ ansible_host }}` อยู่แล้ว** — ไม่ต้องแก้อะไร
> เหลือแค่ฝั่ง webportal ที่ต้อง rewrite `server:` ตอนดึง kubeconfig มา

## 4. การเปลี่ยน `ansible/inventory.yml`

```yaml
all:
  children:
    master:
      hosts:
        master:
          ansible_host: "100.81.134.35"
    workers:
      hosts:
        worker-1:
          ansible_host: "100.73.174.96"
    registry:
      hosts:
        registry-host:
          ansible_host: "100.86.105.18"
    webportal:
      hosts:
        webportal:
          ansible_host: "100.68.206.79"
  vars:
    ansible_user: "room111"
    ansible_become: yes
    ansible_become_method: sudo
```

ย้าย `ansible_user` / `ansible_become` ขึ้นไปเป็น `all.vars` เพราะทั้ง 4 เครื่องใช้ค่าเดียวกัน
ลดการซ้ำและกันพลาดตอนเพิ่มเครื่องใหม่

## 5. Role ใหม่: `ansible/roles/web-portal`

```
roles/web-portal/
├── tasks/main.yml
├── templates/
│   ├── backend.env.j2
│   ├── frontend.env.j2
│   └── docker-compose.prod.yml.j2
└── defaults/main.yml
```

ลำดับ task:

1. ติดตั้ง Docker Engine + compose plugin (จาก official apt repo ไม่ใช่ `docker.io` ของ Ubuntu ซึ่งเก่า)
2. เพิ่ม user `room111` เข้ากลุ่ม `docker`
3. `synchronize` โฟลเดอร์ `web-portal/` ไป `/opt/web-portal` (exclude `node_modules`, `venv`, `.env`)
4. fetch kubeconfig จาก master → rewrite `server:` → วางที่ `/opt/web-portal/backend/kubeconfig.yaml` (mode 600)
5. render `.env` ทั้ง backend/frontend จาก template (ค่ามาจาก Vault)
6. render `docker-compose.prod.yml`
7. `docker compose -f docker-compose.prod.yml up -d --build`
8. health check: `curl -f http://localhost:8000/api/health` (⚠️ ต้องยืนยันว่ามี endpoint นี้จริง — ดูข้อ 9)

## 6. การเปลี่ยน `ansible/site.yml`

```yaml
- name: Provision Virtual-Lab web portal
  hosts: webportal
  become: yes
  roles:
    - { role: common,      tags: ['common'] }
    - { role: tailscale,   tags: ['tailscale'] }
    - { role: web-portal,  tags: ['web-portal'] }
```

วางเป็น play **สุดท้าย** ต่อจาก registry เพราะต้องรอ master สร้าง kubeconfig ก่อน

## 7. Secrets — ต้องแก้ก่อน deploy

### 7.1 ปัญหาที่มีอยู่แล้ว (แยกจากงานนี้ แต่ควรแก้)

`ansible/group_vars/all.yml` มี `cloudflare_tunnel_token` เป็น plaintext ปัจจุบันไฟล์นี้ถูก
gitignore ไว้แล้ว (`.gitignore:190`) **แต่เคยถูก commit มาก่อน** — ยืนยันด้วย:

```bash
# ใส่ 20 ตัวอักษรแรกของ token จาก group_vars/all.yml แทน <TOKEN_PREFIX>
git log --oneline -S '<TOKEN_PREFIX>' --all
# dc964bc Initial skypilot node
# 6b69582 Protecting insecure file system
```

token ยังอยู่ใน git history ดังนั้น**ต้องถือว่ารั่ว** การ gitignore ทีหลังไม่ได้ลบของเก่าออกจาก
history ถ้า repo นี้เคย push ขึ้น remote หรือจะ push ในอนาคต ต้อง revoke แล้วออก token ใหม่

web-portal ไม่ใช้ token นี้ (เลือกทาง Tailscale IP) แต่ SkyPilot ยังใช้อยู่ จึงยังลบทิ้งไม่ได้
— ต้องย้ายเข้า vault แทน

### 7.2 โครงที่เสนอ

```bash
ansible-vault create ansible/group_vars/all/vault.yml
```

```yaml
vault_cloudflare_tunnel_token: "<token ใหม่>"
vault_postgres_password: "<random 32 chars>"
vault_backend_secret_key: "<random 64 chars>"
vault_r2_access_key_id: "..."
vault_r2_secret_access_key: "..."
```

รหัส SSH ไม่ต้องเก็บใน vault เพราะใช้ SSH key แล้ว (ทำใน §8 ขั้นที่ 1)

แล้ว `group_vars/all/main.yml` อ้างถึงแบบ `postgres_password: "{{ vault_postgres_password }}"`

รันด้วย `--ask-vault-pass` หรือ `--vault-password-file`

> รหัส SSH ไม่ถูกเขียนลงไฟล์ใดๆ ที่ git track — และหลังใส่ SSH key แล้วก็ไม่ต้องใช้อีก
> และควรเปลี่ยนไปใช้ SSH key แทน password ตั้งแต่รอบแรก (ดูข้อ 8 ขั้นที่ 1)

## 8. ลำดับการ deploy

```bash
cd ~/document/VirtualLabtest/ansible

# 1. ใส่ SSH key ให้ทั้ง 4 เครื่อง (ทำครั้งเดียว — หลังจากนี้ไม่ต้องใช้ password อีก)
ssh-keyscan -H 100.81.134.35 100.73.174.96 100.86.105.18 100.68.206.79 >> ~/.ssh/known_hosts
for ip in 100.81.134.35 100.73.174.96 100.86.105.18 100.68.206.79; do
  ssh-copy-id room111@$ip
done

# 2. เช็คว่าต่อได้ครบ
ansible all -i inventory.yml -m ping

# 3. cluster ก่อน (master → workers → registry)
ansible-playbook -i inventory.yml site.yml -l master -K
ansible-playbook -i inventory.yml site.yml -l workers -K
ansible-playbook -i inventory.yml site.yml -l registry -K

# 4. web-portal ปิดท้าย
ansible-playbook -i inventory.yml site.yml -l webportal -K --ask-vault-pass

# 5. ตรวจผล
curl -f http://100.68.206.79:8000/docs   # backend ขึ้น
curl -f http://100.68.206.79/            # frontend ขึ้น
```

## 9. คำถามที่ต้องการคำตอบก่อนลงมือ

| # | คำถาม | ทำไมต้องรู้ |
|---|---|---|
| Q4 | Postgres backup? | ข้อมูลอยู่ใน named volume `postgres_data` บนเครื่องเดียว ยังไม่มี backup อัตโนมัติ |

### ปิดแล้ว

- ~~Q1 — R2 credentials?~~ → **ไม่ต้องใช้** โค้ดไม่ได้เรียก R2 เลย ใช้ `STORAGE_ROOT` บน filesystem
- ~~Q2 — domain?~~ → **ไม่ใช้ domain** เข้าผ่าน Tailscale IP `http://100.68.206.79` ตรงๆ
- ~~Q3 — health endpoint?~~ → **มี** `GET /health` (นอก `API_PREFIX`) เช็ค DB ให้ด้วย
- ~~Q5 — Tailscale up หรือยัง?~~ → **up ครบทั้ง 4 เครื่องแล้ว** (2026-09-04)

## 10. ความเสี่ยง

- **R1** — เปลี่ยน master ใหม่แปลว่า k3s cluster เดิมบน `thinkpad` ถูกทิ้ง ข้อมูล/workload ที่ค้างอยู่หายหมด ถ้ามีอะไรต้องเก็บ ต้อง export ก่อน
- **R2** — `flannel_iface: tailscale0` แปลว่าทุก node ต้อง Tailscale online **ก่อน** ติดตั้ง k3s ไม่งั้น k3s จะ start ไม่ขึ้น (ตอนนี้ up ครบแล้ว — ความเสี่ยงนี้ปิดไป)
- **R5** — เข้าผ่าน Tailscale IP แปลว่า **เฉพาะเครื่องใน tailnet เท่านั้นที่เข้าได้** ถ้าต้องให้คนนอก (เช่น นักศึกษาที่ไม่ได้ลง Tailscale) เข้าถึง ต้องเพิ่ม `tailscale funnel` หรือ Cloudflare Tunnel ทีหลัง
- **R6** — ไม่มี HTTPS (http ล้วน) ยอมรับได้เพราะ traffic วิ่งใน WireGuard tunnel ของ Tailscale ซึ่งเข้ารหัสอยู่แล้ว แต่ browser จะขึ้น "Not secure" และ API ที่ต้องใช้ secure context (clipboard, camera) จะใช้ไม่ได้
- **R3** — build frontend บนเครื่อง target ใช้ RAM สูง (Vite + TS) ถ้า VM เล็กกว่า 2GB อาจ OOM — ทางแก้คือ build เป็น image แล้ว push เข้า registry `100.86.105.18` แทน
- **R4** — Postgres ใน compose ใช้ named volume ถ้า `docker compose down -v` จะลบข้อมูลทิ้ง ต้องระวังใน task ของ Ansible อย่าใส่ `-v`

## 11. ขอบเขตที่ **ไม่** รวมในรอบนี้

- CI/CD (auto deploy ตอน push)
- TLS/cert ภายใน (Cloudflare Tunnel จัดการ TLS ขาออกให้แล้ว)
- Postgres backup อัตโนมัติ
- ย้าย web-portal เข้า k3s (ถ้าอนาคตอยากได้ self-heal ค่อยทำ — โครงนี้ไม่ปิดทาง)
