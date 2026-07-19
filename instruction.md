# Instruction — VirtualLabtest

เอกสารนี้สรุปและแยกขั้นตอนการเตรียมระบบ, ติดตั้ง, และรันส่วนต่าง ๆ ของโปรเจกต์ใน workspace นี้ (paths อ้างอิงเป็น relative จาก root ของ repository)

**วัตถุประสงค์**: ให้คนที่มี repository นี้อยู่แล้วสามารถทำตามทีละขั้นตอนเพื่อตั้งค่าสภาพแวดล้อม พิสูจน์การทำงาน และรันบริการหลักได้

---

## สรุปส่วนประกอบสำคัญใน repository
- Ansible playbooks: `ansible/` — provisioning และการติดตั้งบนเครื่อง/เซิร์ฟเวอร์
- Docker config: `docker/`, รวมถึง Dockerfiles ในหลายโฟลเดอร์ เช่น `music-lab/`, `web-portal/`, `server/`
- music-lab: เพลง/เซิร์ฟเวอร์ตัวอย่างด้วย `docker-compose.yml` (โฟลเดอร์ `music-lab/`)
- web-portal: backend และ frontend (โฟลเดอร์ `web-portal/`) — มี `backend/` (Python app) และ `frontend/` (Vite/React/TS)
- skypilot, scripts, และอื่น ๆ: โฟลเดอร์เสริมที่มีสคริปต์, task และ Dockerfile
- ไฟล์สำคัญ: `credentials.env` (มีค่าคอนฟิก/secret ที่ต้องตั้ง)

---

## ข้อกำหนดล่วงหน้า (Prerequisites)
(เลือกตามว่าคุณจะรันแบบ local บน Windows หรือผ่าน WSL2/Linux)

- ระบบปฏิบัติการ: Windows 10/11 (แนะนำ WSL2 สำหรับ Ansible/บางคำสั่ง) หรือ Linux/macOS
- Docker Desktop (with WSL2 backend on Windows) — `docker`, `docker-compose` หรือ `docker compose`
- Ansible (ถ้าจะใช้ playbooks) — ติดตั้งใน WSL2 / Linux environment
- Python 3.10+ (สำหรับ backend หรือสคริปต์บางตัว)
- Node.js 16+ / npm or Yarn (สำหรับ frontend `web-portal/frontend`)
- Git (repo อยู่แล้ว)
- แนะนำ: PostgreSQL/MySQL หรือ DB ที่ project ใช้ (ถ้ามี) — แต่หลายส่วนสามารถรันผ่าน Docker

ตัวอย่างคำสั่งติดตั้ง (Windows/PowerShell ต้องรันเป็น admin เมื่อจำเป็น):

- Docker Desktop: https://www.docker.com/get-started
- WSL2 (Windows): https://docs.microsoft.com/windows/wsl/install
- Ansible (บน WSL/Ubuntu):

```bash
# บน Ubuntu (WSL2 หรือ Linux)
sudo apt update
sudo apt install -y python3-pip python3-venv
pip3 install --user ansible
```

- Node (Windows / nvm): ติดตั้ง Node 18+ (nvm แนะนำ)

---

## ขั้นตอนเตรียมค่าคอนฟิก (ต้องทำก่อนอื่น)
1. เปิดไฟล์ `credentials.env` ที่รูทโปรเจกต์ และเติมค่าที่จำเป็น (DB credentials, API keys, SECRET keys)
   - ตัวอย่างรูปแบบ (ถ้าไม่มี ให้สร้างตามนี้):

```env
# credentials.env - ตัวอย่าง
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
SECRET_KEY=your_secret_key_here
DEBUG=true
# เพิ่มค่าอื่น ๆ ที่ repo ของคุณต้องการ เช่น CLOUD provider keys
```

2. ตรวจสอบไฟล์คอนฟิกของแต่ละ service (เช่น `web-portal/backend/configs/settings.py` และไฟล์ใน `ansible/`) เพื่อให้แน่ใจว่า environment variable ชื่อเดียวกันถูกเรียกใช้

---

## ขั้นตอนโดยรวม (ลำดับที่แนะนำ)
1. เตรียม environment (ติดตั้ง Docker, WSL2/Ansible, Python, Node)
2. เติมค่าที่ `credentials.env`
3. รัน Ansible (ถ้าต้องการ provision) หรือข้ามไปยังการรันด้วย Docker
4. รัน Docker Compose สำหรับแต่ละบริการ (web-portal, music-lab) หรือ build image ตามลำดับ
5. สร้าง/เตรียมฐานข้อมูล และรัน seed scripts
6. รัน backend และ frontend ตรวจสอบ endpoints และ UI
7. ทดสอบการทำงาน (curl, browser)

---

## คำสั่งตัวอย่างแบบทีละขั้นตอน (สามารถคัดลอกไปรันได้)

### A. Clone / เข้ามาที่ repo (ข้ามถ้าอยู่แล้ว)
```bash
cd /path/to/where/you/keep/repos
git clone <repo-url>
cd VirtualLabtest
```

### B. ตั้งค่า `credentials.env`
- แก้ไฟล์ `credentials.env` ใน root ให้ครบตามที่ระบบต้องการ

### C. ถ้าต้องการใช้ Ansible (provision)
- แนะนำใช้ WSL2/Ubuntu เพื่อรัน Ansible

```bash
# ตัวอย่าง (WSL/Ubuntu)
cd VirtualLabtest/ansible
# ตรวจสอบ inventory ก่อน (อาจต้องแก้ชื่อไฟล์ inventory ให้เหมาะสม)
ansible-playbook -i inventory.yml.example site.yml --ask-become-pass
```

> หมายเหตุ: บน Windows ตรง ๆ อาจไม่สะดวก ติดตั้ง Ansible ใน WSL2 หรือใช้ control node เป็น Linux

### D. รัน `web-portal` (Backend + Frontend)

- Backend (หากต้องการรันแบบ local ไม่ใช้ Docker):

```bash
# ไปที่ backend
cd web-portal/backend
python -m venv venv
# PowerShell
venv\Scripts\Activate.ps1
# bash/WSL
source venv/bin/activate
pip install -r requirement.txt || pip install -r requirements.txt
# ตั้ง env vars (หรือโหลดจาก credentials.env)
# ตัวอย่างรัน
python -m main
# หรือหากมี entrypoint เช่น app/main.py: ปรับตาม README ของ folder
```

- Backend (ด้วย Docker):

```bash
# ที่รูทของ web-portal
cd web-portal
docker compose up --build
# หรือ (ถ้าใช้ docker-compose)
docker-compose up --build
```

- Frontend (Vite):

```bash
cd web-portal/frontend
npm install
# สำหรับ dev
npm run dev
# สำหรับ build production
npm run build
```

### E. รัน `music-lab`

- มี `music-lab/docker-compose.yml` ให้ใช้:

```bash
cd music-lab
docker compose up --build
# หรือ docker-compose up --build
```

- ถ้าต้องการรันโค้ดใน `music-lab/server` โดยตรง:

```bash
cd music-lab/server
python -m venv venv
# activate venv
pip install -r requirements.txt   # ถ้ามีไฟล์ requirements
python server.py
```

### F. Skypilot / other Docker images
- สำหรับโฟลเดอร์ `skypilot/` หรือ `skypilot` ที่มี `Dockerfile` ให้ build และรัน:

```bash
cd skypilot
# build
docker build -t skypilot:local .
# run
docker run --rm -it -p 8080:8080 skypilot:local
```

---

## การเตรียมฐานข้อมูล และ seed (web-portal)
- ตรวจสอบ `web-portal/script/init_db.py` และ `web-portal/script/run_seed.py`

```bash
cd web-portal/script
# ถ้า backend ใช้ venv ให้ activate ก่อน
python init_db.py
python run_seed.py
```

- หากใช้ Docker compose แล้ว container DB จะถูกสร้างและ seed ได้จาก container เอง (เช็ค docker-compose.yml)

---

## การตรวจสอบ (Verify)
- Backend health check (ตัวอย่าง):

```bash
curl http://localhost:8000/health
# หรือ endpoint ที่โปรเจกต์กำหนด
```

- Frontend: เปิดเบราเซอร์ที่ `http://localhost:5173` (ค่าเริ่มต้น Vite) หรือพอร์ตที่ปรากฎจาก `npm run dev`

- ดู logs ของ Docker:

```bash
docker compose logs -f
# หรือ
docker logs -f <container-id>
```

---

## ปัญหาที่พบบ่อย & แนวทางแก้ไข
- ปัญหา: `Ansible` บน Windows ใช้ไม่ได้ -> แก้: ใช้ WSL2 หรือ control node เป็น Linux
- ปัญหา: Port ชนกัน -> ปรับพอร์ตใน `docker-compose.yml` หรือหยุด process ที่ใช้อยู่
- ปัญหา: ขาด environment variables -> ตรวจสอบ `credentials.env` และไฟล์ config
- ปัญหา: DB connect fail -> ตรวจสอบ `DATABASE_URL`, ตรวจสอบว่า DB container หรือ DB service รันแล้ว

---

## ไฟล์อ้างอิงสำคัญ (ตรวจสอบ/แก้ไขตามสถานะของคุณ)
- [web-portal/backend/main.py](web-portal/backend/main.py)
- [web-portal/backend/configs/settings.py](web-portal/backend/configs/settings.py)
- [web-portal/script/init_db.py](web-portal/script/init_db.py)
- [web-portal/script/run_seed.py](web-portal/script/run_seed.py)
- [music-lab/docker-compose.yml](music-lab/docker-compose.yml)
- [ansible/site.yml](ansible/site.yml)

---

## สิ่งที่ควรทำหลังจากนี้ (แนะนำ)
- ตรวจสอบ `credentials.env` เติมค่าจริง
- ตัดสินใจว่าต้องการรันผ่าน Docker (แนะนำ) หรือรัน local (dev)
- รัน `docker compose up --build` สำหรับบริการหลักก่อน
- ถ้าต้อง provision ระบบจริง ให้รัน `ansible` จากเครื่อง Linux/WSL2

---

หากต้องการ ผมช่วยได้:
- สร้างตัวอย่าง `credentials.env.example` ที่ครบถ้วน
- รันคำสั่งตัวอย่างในเครื่องของคุณเพื่อตรวจสอบ (ต้องการสิทธิ์เข้าถึง terminal)
- ปรับคำสั่งให้เหมาะกับ Windows/PowerShell ถ้าจำเป็น

