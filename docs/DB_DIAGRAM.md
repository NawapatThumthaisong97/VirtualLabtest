# Virtual Lab — Database Diagram

> ER diagram ของ schema v2 (PostgreSQL 17 — จะ implement ด้วย SQLAlchemy 2.0 + Alembic)

```mermaid
erDiagram
  users {
    uuid id PK
    text email UK "จาก Google SSO"
    text name
    text student_id UK "รหัสนักศึกษา (null ได้)"
    text role "student | instructor | admin"
    timestamptz created_at
  }

  courses {
    uuid id PK
    text code UK "เช่น CS217"
    text name
    text lecturer_name "display เท่านั้น"
    text banner_color
    uuid created_by FK
    timestamptz created_at
  }

  enrollments {
    uuid user_id PK, FK
    uuid course_id PK, FK
    text role_in_course "student | ta | instructor"
    timestamptz enrolled_at
  }

  labs {
    uuid id PK
    uuid course_id FK
    text title
    int order_no "unique ต่อ course"
    text doc_url "เอกสารบน R2"
    uuid image_id FK "อ้าง lab_images"
    timestamptz due_at
    text status "draft | published"
    timestamptz created_at
  }

  lab_images {
    uuid id PK
    uuid uploaded_by FK
    uuid course_id FK
    text repository "เช่น skypilot/music-lab"
    text tag "เช่น lab-01"
    text image_digest "sha256 สำหรับลบ image"
    int size_mb
    text status "pending | approved | rejected"
    timestamptz upload_link_expires_at "TTL 24h"
    timestamptz created_at
  }

  lab_progress {
    uuid user_id PK, FK
    uuid lab_id PK, FK
    text status "not_started | in_progress | finished"
    timestamptz started_at
    timestamptz finished_at
    timestamptz updated_at
  }

  sessions {
    uuid id PK
    uuid user_id FK
    uuid lab_id FK "null สำหรับ sandbox/compute"
    text service_type "lab | compute | sandbox | ai_job"
    text k8s_pod_name
    text node_name
    boolean is_remote "รันจากบ้าน"
    boolean is_cloud "SkyPilot burst"
    text sky_cluster_name
    int sky_job_id
    text image_ref "snapshot ตอน launch"
    text status "pending - provisioning - running - stopped/succeeded/failed"
    timestamptz started_at
    timestamptz ended_at
    timestamptz expires_at "countdown ใน Lab Hub"
  }

  usage_records {
    bigint id PK
    uuid session_id FK
    bigint cpu_seconds
    bigint gpu_seconds
    numeric ram_mb_hours
    boolean is_cloud_burst
    numeric est_cost_thb "snapshot - ห้าม recompute"
    timestamptz recorded_at
  }

  quotas {
    uuid id PK
    uuid user_id FK "null ได้"
    uuid course_id FK "null ได้"
    numeric compute_hours_limit
    int storage_mb_limit
    text period "weekly | monthly | semester"
  }

  announcements {
    uuid id PK
    uuid course_id FK "null = global"
    uuid author_id FK
    text message
    timestamptz created_at
  }

  users ||--o{ enrollments : "enrolls"
  courses ||--o{ enrollments : "has members"
  users ||--o{ courses : "created by (admin)"
  courses ||--o{ labs : "contains"
  lab_images ||--o{ labs : "image of"
  users ||--o{ lab_images : "uploads"
  courses ||--o{ lab_images : "attached to"
  users ||--o{ lab_progress : "tracks"
  labs ||--o{ lab_progress : "progress of"
  users ||--o{ sessions : "runs"
  labs ||--o{ sessions : "spawned for"
  sessions ||--o{ usage_records : "metered by"
  users ||--o{ quotas : "limited by"
  courses ||--o{ quotas : "limited by"
  courses ||--o{ announcements : "posts"
  users ||--o{ announcements : "authored by"
```

## อ่าน diagram ยังไง

- `||--o{` = one-to-many (ซ้าย 1 ตัว มีขวาได้หลายตัว)
- `PK` / `FK` / `UK` = primary key / foreign key / unique
- ป้ายกำกับหลังชนิดข้อมูล = ค่าที่เป็นไปได้หรือหมายเหตุสั้น ๆ

## Highlight

- **`sessions` ตารางเดียว** ครอบทุก workload (lab / compute / sandbox / AI job) — แยกประเภทด้วย `service_type`, มี `sky_cluster_name`/`sky_job_id` ผูกกับ SkyPilot
- **`lab_progress` แยกจาก `sessions`** — จบแลปเป็น learning fact ใช้กี่ session ก็ได้
- **`usage_records` เป็น Phase 2** — ตอนนี้ quota คิดจากเวลาเปิด–ปิด session
- **image อ้างด้วย `repository` + `tag`** ไม่ฝัง registry host (Tailscale IP เปลี่ยนได้)
