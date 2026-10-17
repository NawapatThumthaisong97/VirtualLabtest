# Prompt: เพิ่มตารางตารางเรียน / จองรอบ lab

## บริบท

- โปรเจกต์: Virtual Lab, backend อยู่ที่ `web-portal/backend` (FastAPI + SQLAlchemy + PostgreSQL)
- branch: `feature/sky-aws-launch`
- model อยู่ใน `app/models/*.py`, seed อยู่ใน `app/seeds/seed.py`
- ยังไม่มี Alembic ตอนนี้ schema สร้างด้วย `script/init_db.py` (`create_all`)
- จุดประสงค์ของฟีเจอร์: ให้ระบบรู้ล่วงหน้าว่าวิชาไหนจะใช้ lab image อะไร วันไหน เวลาไหน กี่คน เพื่อเอาไว้ **pre-warm** (pull image และ scale node ไว้ก่อนเริ่มคาบ)
- เวอร์ชันนี้ **ไม่บังคับการจอง** นักศึกษายังเปิด lab นอกคาบได้ตามปกติ

## ก่อนเริ่ม

1. อ่าน model ที่มีอยู่ก่อน (`Course`, `Lab`, `LabImage`, `Session`, `User`) แล้วใช้ convention เดียวกันทุกเรื่อง ได้แก่ uuid PK, `timestamptz`, วิธีประกาศ enum, soft delete ด้วย `deleted_at`, การตั้งชื่อ relationship
2. ถ้าเจออะไรในโค้ดที่ขัดกับ prompt นี้ ให้หยุดแล้วถามก่อน ห้ามเดาเอง

## สิ่งที่ต้องทำ

### 1. ตาราง `class_schedules` (กฎการเรียนประจำสัปดาห์)

| column | type | หมายเหตุ |
|---|---|---|
| id | uuid PK | |
| course_id | uuid FK → courses | NOT NULL |
| weekday | int | 0 = จันทร์ … 6 = อาทิตย์, CHECK 0–6 |
| start_time | time | เวลาไทย (Asia/Bangkok) |
| end_time | time | CHECK `end_time > start_time` |
| valid_from | date | วันเปิดเทอม |
| valid_until | date | CHECK `valid_until >= valid_from` |
| default_lab_image_id | uuid FK → lab_images | nullable |
| expected_seats | int | CHECK > 0 |
| created_by | uuid FK → users | |
| created_at | timestamptz | |
| deleted_at | timestamptz | soft delete |

### 2. ตาราง `class_slots` (รอบจริงแต่ละวัน)

| column | type | หมายเหตุ |
|---|---|---|
| id | uuid PK | |
| schedule_id | uuid FK → class_schedules | nullable (null = จองครั้งเดียว) |
| course_id | uuid FK → courses | NOT NULL |
| lab_id | uuid FK → labs | nullable |
| lab_image_id | uuid FK → lab_images | NOT NULL, `ON DELETE RESTRICT` |
| starts_at | timestamptz | เก็บเป็น UTC |
| ends_at | timestamptz | CHECK `ends_at > starts_at` |
| expected_seats | int | CHECK > 0 |
| run_target | enum | ใช้ enum เดียวกับ `labs.run_target` (KUBERNETES / AWS) |
| status | enum | SCHEDULED / PREWARMING / READY / DONE / CANCELLED, default SCHEDULED |
| note | text | nullable |
| created_by | uuid FK → users | |
| created_at, updated_at | timestamptz | |
| deleted_at | timestamptz | soft delete |

Index / constraint:
- index บน `(starts_at)` และ `(course_id, starts_at)`
- **กันไม่ให้ slot ของวิชาเดียวกันมีเวลาทับกัน** ใช้ exclusion constraint ของ Postgres ด้วย `btree_gist` บน `course_id WITH =` และ `tstzrange(starts_at, ends_at) WITH &&` โดยใส่ `WHERE deleted_at IS NULL AND status <> 'CANCELLED'` ถ้าทำผ่าน `create_all` ไม่ได้ ให้บอกผมก่อนว่าจะทำด้วยวิธีไหน

### 3. แก้ตาราง `sessions`

- เพิ่ม `class_slot_id` uuid FK → class_slots, nullable, `ON DELETE SET NULL`
- โค้ด launch ยังไม่ต้องเขียนค่าลงคอลัมน์นี้ แค่เพิ่มคอลัมน์ไว้ก่อน

### 4. Relationship

- `Course.class_schedules`, `Course.class_slots`
- `ClassSchedule.slots`
- `ClassSlot.sessions`

### 5. ฟังก์ชัน generate slot

- เขียนฟังก์ชันแยกไว้ (เช่นใน `app/services/schedule_service.py`) ที่รับ `ClassSchedule` แล้วสร้าง `class_slots` ให้ทุกวันที่ตรงกับ `weekday` ตั้งแต่ `valid_from` ถึง `valid_until`
- แปลงเวลาไทยเป็น UTC ด้วย `zoneinfo.ZoneInfo("Asia/Bangkok")` ห้าม hardcode +7
- ต้องเรียกซ้ำได้โดยไม่สร้าง slot ซ้ำ (idempotent)

### 6. Seed

เพิ่มลงใน `seed.py` ต่อจากของเดิม:
- SE301 เรียนทุกวันจันทร์ 09:00–12:00 ใช้ `skypilot/music-lab:lab-01`, 40 ที่นั่ง, ช่วงเทอม 8 สัปดาห์ แล้วเรียกฟังก์ชัน generate
- DEVOPS201 จองครั้งเดียว (`schedule_id = null`) วันศุกร์ 13:00–16:00 ใช้ `vlab/devops-toolbox`, 25 ที่นั่ง
- ตั้งค่าวันที่ให้อิงกับวันที่รัน seed เพื่อให้มีทั้ง slot ที่ผ่านไปแล้วและ slot ที่ยังไม่ถึง

## ห้ามทำ (นอก scope)

- ยังไม่ต้องทำ job pre-warm, API endpoint หรือหน้า frontend
- ห้ามเก็บปี พ.ศ. ลง DB เพราะการแปลงเป็นหน้าที่ของ frontend
- ห้ามแก้ logic launch session เดิม

## เรื่อง migration

ตอนนี้ `create_all` จะสร้างตารางใหม่ให้ได้ แต่จะ **ไม่เพิ่มคอลัมน์ `class_slot_id` ลงใน `sessions` ที่มีอยู่แล้ว** ให้เสนอมา 2 ทางว่าจะเอาแบบไหน: (ก) drop DB แล้วรัน init + seed ใหม่ หรือ (ข) ตั้ง Alembic แล้วทำ baseline migration รอผมเลือกก่อนแล้วค่อยลงมือ

## ตรวจงาน

1. รัน `script/init_db.py` แล้วตามด้วย `script/run_seed.py` บน DB ใหม่ ต้องไม่มี error
2. query `class_slots` ของ SE301 ต้องได้ 8 แถว ทุกแถวเป็นวันจันทร์ 09:00 เวลาไทย
3. ลอง insert slot ของ SE301 ที่เวลาทับกับแถวเดิม ต้องโดน constraint ปฏิเสธ
4. เรียกฟังก์ชัน generate ซ้ำ จำนวนแถวต้องเท่าเดิม
5. สรุปให้ผมว่าแก้ไฟล์ไหนบ้าง และ constraint ไหนไปอยู่ที่ระดับ DB ไหนอยู่ที่ระดับโค้ด
