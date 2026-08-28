# Virtual Lab Local Setup

คู่มือนี้ใช้ PostgreSQL ใน Docker และรัน backend/frontend แบบ local บน Windows

## สิ่งที่ต้องติดตั้ง

- Python 3.11+
- Node.js 20+
- Docker Desktop

ตรวจสอบ:

```powershell
python --version
node --version
npm --version
docker version
```

## 1. เปิดฐานข้อมูลเดิม

ฐานข้อมูลอยู่ใน [docker-compose.yml](docker-compose.yml) ของโฟลเดอร์ `web-portal` โดยมีค่า:

- Container: `virtual_lab_db`
- Image: `postgres:17-alpine`
- Database: `virtual_lab`
- User: `postgres`
- Password: `password`
- Host port: `5432`
- Volume: `web-portal_postgres_data`

เปิด Docker Desktop ก่อน แล้วรันจากโฟลเดอร์ `web-portal`:

```powershell
cd C:\Users\Xplosion97\VirtualLabtest\web-portal
docker compose up -d db
docker compose ps
```

ตรวจ database โดยไม่ต้องติดตั้ง `psql` บน Windows:

```powershell
docker compose exec db psql -U postgres -d virtual_lab -c "SELECT current_database();"
```

คำสั่งจัดการ:

```powershell
docker compose stop db       # หยุดชั่วคราว ข้อมูลยังอยู่
docker compose start db      # เปิดกลับมา
docker compose logs -f db    # ดู log
docker compose down          # ลบ container แต่เก็บ volume
```

คำสั่งนี้จะลบข้อมูลทั้งหมด ห้ามใช้ถ้าไม่ต้องการ reset database:

```powershell
docker compose down -v
```

## 2. ติดตั้งและตั้งค่า backend

เปิด terminal ใหม่:

```powershell
cd C:\Users\Xplosion97\VirtualLabtest\web-portal\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirement.txt
```

แก้ไฟล์ `backend/.env` ให้มีค่า:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/virtual_lab
CORS_ORIGINS_STR=http://localhost:5173
K8S_ENABLED=False
```

สร้างตารางและข้อมูลตัวอย่าง:

```powershell
python script/init_db.py
python script/run_seed.py
```

## 3. รัน backend

ใน terminal backend ที่ activate `.venv` แล้ว:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

ตรวจสอบ:

- Swagger: `http://localhost:8000/docs`
- Courses API: `http://localhost:8000/api/courses`
- Health: `http://localhost:8000/health`

`/api/courses` ควรมีข้อมูลจาก seed อย่างน้อย 2 courses

## 4. รัน frontend

เปิด terminal ใหม่:

```powershell
cd C:\Users\Xplosion97\VirtualLabtest\web-portal\frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

ไฟล์ `frontend/.env` ต้องมี:

```env
VITE_API_URL=http://localhost:8000/api
```

เปิด `http://localhost:5173` แล้วกด card `Lab work` เพื่อไป `/courses`

## 5. Flow ที่ต้องเปิดพร้อมกัน

ต้องมี 3 terminal:

```powershell
# Terminal 1: database
cd C:\Users\Xplosion97\VirtualLabtest\web-portal
docker compose up -d db

# Terminal 2: backend
cd C:\Users\Xplosion97\VirtualLabtest\web-portal\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000

# Terminal 3: frontend
cd C:\Users\Xplosion97\VirtualLabtest\web-portal\frontend
npm run dev
```

ตรวจตามลำดับ:

1. `http://localhost:8000/health` ต้องตอบ `healthy`
2. `http://localhost:8000/api/courses` ต้องมี courses
3. `http://localhost:5173` แล้วกด `Lab work`
4. หน้า `/courses` ต้องแสดงข้อมูลจาก API

ถ้าเจอ connection error ให้ตรวจว่า Docker Desktop ทำงานอยู่ และ port `5432`, `8000`, `5173` ไม่ถูกใช้งานโดยโปรแกรมอื่น

## Course deletion policy

- `DELETE /api/courses/{id}`: soft delete โดยตั้งค่า `deleted_at`
- `DELETE /api/courses/{id}/hard`: hard delete ออกจาก database ถาวร
- `get_all()`: ไม่คืนรายการที่ soft delete แล้ว
- `DELETE /api/labs/{id}`: soft delete

ไม่ควรใช้ hard delete กับ Course ที่มี labs, enrollments หรือ announcements อ้างอิงอยู่

## หยุดระบบ

- กด `Ctrl+C` เพื่อหยุด backend/frontend
- `docker compose stop db` เพื่อหยุด database และเก็บข้อมูลไว้
- `docker compose down -v` ใช้เฉพาะเมื่อต้องการล้าง database แล้วเริ่มใหม่
