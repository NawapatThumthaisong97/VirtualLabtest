# Database ณ ปัจจุบัน + Seed

> อ่านจาก `web-portal/backend/app/models/*.py` และ `app/seeds/seed.py` บน branch `feature/sky-aws-launch`
> สถานะ ณ 2026-10-17 (อัปเดตหลังเพิ่มตารางเรียน, branch `experiment/prewarm-daemonset`)
> ยังไม่มี Alembic — schema สร้างด้วย `script/init_db.py` (`create_all`) ตอนเพิ่มตารางใหม่ใช้วิธี drop DB + init + seed

---

## 1. ER Diagram (13 ตาราง)

```mermaid
erDiagram
    users ||--o{ enrollments : "user_id"
    courses ||--o{ enrollments : "course_id"
    users ||--o{ courses : "created_by"
    users ||--o{ lab_images : "uploaded_by"
    courses ||--o{ lab_images : "course_id"
    courses ||--o{ labs : "course_id (CASCADE)"
    lab_images |o--o{ labs : "image_id (RESTRICT)"
    users ||--o{ lab_progress : "user_id"
    labs ||--o{ lab_progress : "lab_id"
    users ||--o{ sessions : "user_id"
    labs |o--o{ sessions : "lab_id"
    lab_images |o--o{ sessions : "lab_image_id"
    sessions ||--o{ usage_records : "session_id"
    users |o--o{ quotas : "user_id"
    courses |o--o{ quotas : "course_id"
    courses |o--o{ announcements : "course_id"
    users ||--o{ announcements : "author_id"
    courses ||--o| course_images : "course_id (unique)"
    users ||--o{ course_images : "created_by"
    courses ||--o{ class_schedules : "course_id"
    lab_images |o--o{ class_schedules : "default_lab_image_id"
    class_schedules |o--o{ class_slots : "schedule_id (null = จองครั้งเดียว)"
    courses ||--o{ class_slots : "course_id"
    labs |o--o{ class_slots : "lab_id"
    lab_images ||--o{ class_slots : "lab_image_id (RESTRICT)"
    class_slots |o--o{ sessions : "class_slot_id (SET NULL)"

    users {
        uuid id PK
        string email UK
        string name
        string student_id UK "nullable"
        string password_hash "nullable"
        enum role "STUDENT / INSTRUCTOR / ADMIN"
        timestamptz created_at
    }
    courses {
        uuid id PK
        string code UK
        string name
        string lecturer_name
        string image_url "nullable"
        string background_key "nullable (preset)"
        string icon_key "nullable (preset)"
        uuid created_by FK
        timestamptz created_at
        timestamptz deleted_at "soft delete"
    }
    course_images {
        uuid id PK
        uuid course_id FK,UK
        string image_url
        uuid created_by FK
        timestamptz created_at
        timestamptz updated_at
    }
    enrollments {
        uuid user_id PK,FK
        uuid course_id PK,FK
        enum role_in_course "STUDENT / TA / INSTRUCTOR"
        timestamptz enrolled_at
    }
    labs {
        uuid id PK
        uuid course_id FK
        string title
        int order_no "unique ต่อ course เมื่อ deleted_at IS NULL"
        text description
        string doc_url "labs/{id}/doc.pdf"
        uuid image_id FK "nullable = lab อ่านอย่างเดียว"
        timestamptz due_at
        enum status "DRAFT / PUBLISHED"
        enum run_target "KUBERNETES (default) / AWS"
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at "soft delete"
    }
    lab_images {
        uuid id PK
        uuid uploaded_by FK
        uuid course_id FK
        string repository "UK (repository, tag)"
        string tag
        string image_digest UK
        int size_mb
        string cpu_requirement "2+"
        string memory_requirement "4+"
        int disk_size "GB"
        int lifespan_minutes "อายุสูงสุดของ lab"
        jsonb exposed_ports "[8080, ...]"
        string entrypoint_script
        string workdir "nullable"
        jsonb env_vars "nullable"
        text description
        enum status "PENDING / APPROVED / REJECTED"
        timestamptz created_at
    }
    lab_progress {
        uuid user_id PK,FK
        uuid lab_id PK,FK
        enum status "NOT_STARTED / IN_PROGRESS / FINISHED"
        timestamptz started_at
        timestamptz finished_at
        timestamptz updated_at
    }
    sessions {
        uuid id PK
        uuid user_id FK
        uuid lab_id FK "nullable"
        uuid lab_image_id FK "nullable"
        enum service_type "LAB / COMPUTE_SERVICE / AI_TRAINING"
        string k8s_pod_name "ยังไม่ได้ใช้"
        string node_name "ยังไม่ได้ใช้"
        bool is_remote
        bool is_cloud "true = AWS"
        string sky_cluster_name
        int sky_job_id
        jsonb endpoints "{port: url}"
        enum status "PENDING / RUNNING / STOPPED / FAILED"
        timestamptz started_at
        timestamptz ended_at
        timestamptz expires_at
        enum end_reason "USER_DELETE / EXPIRED / LOST / LAUNCH_FAILED / STALE_PENDING"
        timestamptz deleted_at "soft delete"
        uuid class_slot_id FK "ใหม่: เปิดในคาบไหน (launch ยังไม่เขียน)"
    }
    class_schedules {
        uuid id PK
        uuid course_id FK
        int weekday "0 = จันทร์ … 6"
        time start_time "เวลาไทย"
        time end_time
        date valid_from
        date valid_until
        uuid default_lab_image_id FK "nullable"
        int expected_seats
        uuid created_by FK
        timestamptz created_at
        timestamptz deleted_at "soft delete"
    }
    class_slots {
        uuid id PK
        uuid schedule_id FK "nullable"
        uuid course_id FK
        uuid lab_id FK "nullable"
        uuid lab_image_id FK
        timestamptz starts_at "UTC"
        timestamptz ends_at
        int expected_seats
        enum run_target "KUBERNETES / AWS"
        enum status "SCHEDULED / PREWARMING / READY / DONE / CANCELLED"
        text note
        uuid created_by FK
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at "soft delete"
    }
    usage_records {
        bigint id PK
        uuid session_id FK
        bigint cpu_seconds
        bigint gpu_seconds
        numeric ram_mb_hours
        bool is_cloud_burst
        numeric est_cost_thb
        timestamptz recorded_at
    }
    quotas {
        uuid id PK
        uuid user_id FK "nullable"
        uuid course_id FK "nullable"
        numeric compute_hours_limit
        int storage_mb_limit
        enum period "WEEKLY / MONTHLY / SEMESTER"
    }
    announcements {
        uuid id PK
        uuid course_id FK "nullable"
        uuid author_id FK
        text message
        timestamptz created_at
    }
```

### Constraint / index ที่ควรรู้

| ตาราง | constraint | ผล |
|---|---|---|
| `labs` | `unique_course_order` (`course_id`, `order_no`) **WHERE `deleted_at IS NULL`** | ลบ lab แล้วใช้เลขลำดับเดิมซ้ำได้ |
| `labs.course_id` | `ON DELETE CASCADE` | ลบ course (hard) → lab หายตาม |
| `labs.image_id` | `ON DELETE RESTRICT` | ลบ image ไม่ได้ถ้ายังมี lab ใช้อยู่ |
| `lab_images` | `uq_repository_tag`, `image_digest` unique | image ซ้ำไม่ได้ |
| `enrollments`, `lab_progress` | composite PK | 1 คน ลง 1 วิชา / มี progress 1 แถวต่อ lab |
| `course_images.course_id` | unique | 1 course มี 1 รูป |
| `sessions` | **ไม่มี** unique กัน PENDING/RUNNING ซ้อน | กันที่ service เท่านั้น (race ยังค้าง ดู `Flow.md`) |
| `class_slots` | `ex_class_slots_no_overlap` EXCLUDE gist (`course_id =`, `tstzrange(starts_at, ends_at) &&`) WHERE ไม่ลบ + ไม่ CANCELLED | slot วิชาเดียวกันห้ามทับกัน (ต้องมี extension `btree_gist` สร้างให้ตอน create_all) |
| `class_slots` / `class_schedules` | CHECK เวลา / วันที่ / weekday 0–6 / seats > 0 | ค่าผิดเข้า DB ไม่ได้ |

Soft delete มี 5 ตาราง: `courses`, `labs`, `sessions`, `class_schedules`, `class_slots`

---

## 2. Seed — persona "Sophia Davis"

`python script/run_seed.py` (ข้ามทั้งหมดถ้ามี user อยู่แล้ว ต้อง drop DB ก่อนถ้าจะ seed ใหม่)

```mermaid
flowchart LR
    subgraph USERS["users (5)"]
        ADMIN["Virtual Lab Admin<br/>ADMIN"]
        KIT["Dr. Kittipong Somsak<br/>INSTRUCTOR"]
        MAR["Dr. Marisa Chandra<br/>INSTRUCTOR"]
        SOP["⭐ Sophia Davis<br/>STUDENT 6709616000"]
        NAT["Nathan Cole<br/>STUDENT 6709616001"]
    end

    subgraph COURSES["courses (3)"]
        SE["SE301<br/>Software Engineer"]
        DO["DEVOPS201<br/>DevOps"]
        CS["CS102<br/>Data Structures<br/>(ตัวคุม filter)"]
    end

    subgraph IMAGES["lab_images (2)"]
        IMG1["skypilot/music-lab:lab-01<br/>✅ image จริง<br/>8080 / 5173 / 8443"]
        IMG2["vlab/devops-toolbox:devops201-lab01<br/>⚠️ placeholder ไม่มี image จริง<br/>3000"]
    end

    subgraph LABS["labs (6)"]
        L1["OOP with Spring Boot<br/>03a18386… (fix id)<br/>PUBLISHED + PDF"]
        L2["Unit 5 Polymorphism (reading)<br/>213f2122… (fix id)<br/>PUBLISHED + PDF ไม่มี image"]
        L3["CI/CD Pipeline<br/>PUBLISHED"]
        L4["Containerize Node.js<br/>PUBLISHED ไม่มี image"]
        L5["Kubernetes Basics<br/>DRAFT"]
        L6["Linked List & Stack<br/>PUBLISHED ไม่มี image"]
    end

    SOP -->|STUDENT| SE
    SOP -->|STUDENT| DO
    KIT -->|INSTRUCTOR| SE
    MAR -->|INSTRUCTOR| DO
    NAT -->|STUDENT| CS
    ADMIN -.->|created_by| CS

    SE --> L1 & L2
    DO --> L3 & L4 & L5
    CS --> L6

    IMG1 --> L1
    IMG2 --> L3

    SESS["sessions (1)<br/>Sophia × OOP lab<br/>RUNNING, K3s, ไม่มี sky_cluster_name"]
    SOP --> SESS
    L1 --> SESS
    SESS --> USAGE["usage_records (1)<br/>2700 cpu-s, 18.5 THB"]

    style SOP fill:#ffd
    style IMG2 fill:#fdd
    style SESS fill:#eef
```

เส้นทับ (enrollment) คือ `role_in_course` · เส้นประคือ `created_by` อย่างเดียว ไม่ได้ลงเรียน

### จำนวนแถวต่อตาราง

| ตาราง | แถว | รายละเอียด |
|---|---|---|
| `users` | 5 | admin 1, instructor 2, student 2 |
| `courses` | 3 | SE301, DEVOPS201, CS102 |
| `course_images` | **0** | ใช้ `background_key` / `icon_key` (preset) แทน |
| `enrollments` | 5 | Sophia 2, instructor 2, Nathan 1 |
| `lab_images` | 2 | APPROVED ทั้งคู่ |
| `labs` | 6 | **ทุกตัว `run_target` = KUBERNETES** (default) |
| `lab_progress` | 2 | Sophia: OOP = IN_PROGRESS, CI/CD = NOT_STARTED |
| `sessions` | 1 | RUNNING, เริ่ม 45 นาทีก่อน, `expires_at` +2 ชม. |
| `usage_records` | 1 | ผูกกับ session ข้างบน |
| `quotas` | 2 | Sophia 50 ชม./เดือน, SE301 500 ชม./เทอม |
| `announcements` | 3 | SE301 2, DEVOPS201 1 |
| `class_schedules` | 1 | SE301 ทุกจันทร์ 09:00–12:00 เทอม 8 สัปดาห์ (เริ่ม 4 สัปดาห์ก่อนวันรัน seed) 40 ที่ |
| `class_slots` | 9 | SE301 8 (ผ่านแล้ว 4 / ยังไม่ถึง 4) + DEVOPS201 จองครั้งเดียวศุกร์ที่จะถึง 13:00–16:00 25 ที่ |

### บัญชี login

| ใคร | email | password |
|---|---|---|
| Sophia (persona) | `sophia.dav@dome.tu.ac.th` / `6709616000` | `sophia6764` |
| คนอื่นทั้งหมด | ตามตารางข้างบน | `labpass123` |

---

## 3. ข้อสังเกต: seed เทียบกับโค้ด session ตอนนี้

| เรื่อง | ผล |
|---|---|
| ไม่มี lab ที่ `run_target = AWS` | เทสเส้น AWS ต้องแก้ DB เอง (`UPDATE labs SET run_target='AWS' ...`) และ image ต้องมีใน ECR — `skypilot/music-lab` ยังไม่มีใน ECR (มีแค่ `vlab/music-lab-ide`) |
| session seed ไม่มี `sky_cluster_name` | reconciler ข้ามแถวนี้ (ตั้งใจ) และ DELETE ได้ไม่พัง แต่ Sophia กด Start lab OOP จะได้ **409** จนกว่าจะลบ session นี้ |
| `endpoints` ของ seed ใช้ key `ide/client/server` | session จริงใช้ key เป็นเลขพอร์ต (`"8080": "http://..."`) — frontend ต้องรองรับทั้งสองแบบ หรือปรับ seed ให้ตรง |
| `expires_at` ของ seed = +2 ชม. แต่ `lifespan_minutes` = 60 | ไม่ตรงกัน แต่ไม่มีผลเพราะไม่มี cluster จริง |
| lab CI/CD ผูก `vlab/devops-toolbox` (placeholder) | กด Start จะ launch แล้วพังที่ pull → `FAILED` / `LAUNCH_FAILED` |
| `end_reason` ไม่มีใน seed | ถูกต้อง เพราะ session ยัง RUNNING |
| `k8s_pod_name`, `node_name` | มีค่าแค่ใน seed โค้ด launch ไม่เคยเขียน |
| `course_images` | มี model แต่ไม่มี seed และไม่มี relationship ฝั่ง `Course` |
