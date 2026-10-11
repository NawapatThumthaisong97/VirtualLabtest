# AWS Lab Flow — เปิด/ปิด lab บน AWS ทั้งระบบ

> ภาพรวมของทุกอย่างที่เกี่ยวกับการ launch lab ไป AWS (PR #88 + branch `infra/ecr-pull-experiment`)
> สถานะ ณ 2026-10-11 แต่ละรูปตอบคำถามเดียว อ่านตามลำดับ 1 → 6

---

## 1. มีใครอยู่ในระบบบ้าง (ชิ้นส่วน)

```mermaid
flowchart LR
    subgraph HOME["ที่บ้าน / เครื่อง ThinkPad"]
        FE["Frontend<br/>(ปุ่ม Start Lab)"]
        BE["Backend FastAPI<br/>session_service.py"]
        DB[("Postgres<br/>labs, sessions")]
        SKY["SkyPilot API server"]
    end

    subgraph AWS["AWS ap-southeast-1 — VPC vlab-ecr-pull"]
        subgraph PUB["Public subnet"]
            ROUTER["Tailscale router<br/>vlab-ts-router"]
        end
        subgraph PRIV["Private subnet (ไม่มี IPv4 ออกเน็ต)"]
            EC2["EC2 ของ lab<br/>m7i-flex.large<br/>AMI vlab-bake r2"]
        end
        ECR[("ECR<br/>vlab/music-lab-ide")]
        EC2API["EC2 API"]
    end

    FE -->|"POST /api/sessions"| BE
    BE <--> DB
    BE -->|"sky.launch / sky.down"| SKY
    SKY -->|"สร้าง/ลบ EC2"| EC2API
    SKY -->|"SSH ผ่าน Tailscale"| ROUTER
    ROUTER --> EC2
    EC2 -->|"docker pull (IPv6)"| ECR
    FE -.->|"เปิด IDE :8080 ผ่าน Tailscale"| ROUTER
```

| ชิ้น | หน้าที่ |
|---|---|
| Backend | รับคำขอ เลือกว่า lab ไป K3s หรือ AWS (`labs.run_target`) สร้าง task ส่งให้ SkyPilot บันทึก session |
| SkyPilot API server | คนที่สั่ง AWS จริง (สร้าง EC2, SSH เข้าไปติดตั้ง, ลบ EC2) |
| Tailscale router | ประตูเดียวเข้า private subnet ทั้ง SkyPilot (SSH) และนักศึกษา (IDE) ต้องผ่านตัวนี้ |
| EC2 ของ lab | 1 เครื่องต่อ 1 session รัน lab เป็น docker container |
| ECR | เก็บ image ของ lab |

---

## 2. ใครใช้กุญแจ (credential) อะไร

```mermaid
flowchart TB
    subgraph KEYS["Credential 3 ตัว"]
        K1["IAM user: Skypilot-IAM<br/>(AWS_PROFILE=skypilot บน ThinkPad)"]
        K2["IAM role: vlab-lab-ecr-pull<br/>(ติดอยู่กับ EC2 ของ lab)"]
        K3["ECR token<br/>(อายุ 12 ชม. ขอใหม่ทุกครั้ง)"]
    end

    K1 -->|"สร้าง / ลบ EC2"| A1["SkyPilot API server"]
    K1 -->|"ขอ ECR token"| A2["Backend (get_ecr_token)"]
    A2 --> K3
    K3 -->|"ส่งเป็น secret ตอน launch"| A3["EC2: docker login + pull"]
    K2 -->|"ลบตัวเองตอนหมดเวลา"| A4["skylet บน EC2 (autostop)"]
```

| ตัว | สิทธิ์ | ห้าม |
|---|---|---|
| `Skypilot-IAM` | EC2 (สร้าง/ลบ), PassRole, ECR pull `vlab/music-lab-ide` | ไม่ใช่ root |
| `vlab-lab-ecr-pull` | ECR pull + **ลบเครื่องที่มี tag `skypilot-cluster-name`** (เพิ่มใหม่) | container ของ lab เอาไปใช้ไม่ได้ (metadata hop limit = 1) |
| ECR token | pull image | ไม่ลง DB ไม่โผล่ใน log (เทสแล้ว) |
| profile `default` บน ThinkPad | **root** | ห้ามใช้กับระบบนี้ |

---

## 3. กด Start Lab → ได้ IDE (เส้นปกติ ~85 วินาที)

```mermaid
sequenceDiagram
    autonumber
    actor U as นักศึกษา
    participant BE as Backend
    participant DB as Postgres
    participant SKY as SkyPilot
    participant EC2 as EC2 ของ lab
    participant ECR as ECR

    U->>BE: กด Start (POST /api/sessions)
    BE->>DB: lab นี้ run_target = AWS ?
    BE->>DB: มี session PENDING/RUNNING อยู่ไหม → ถ้ามี ตอบ 409
    BE->>BE: สร้าง task (AMI, instance type, docker run ...)
    BE->>ECR: ขอ ECR token (Skypilot-IAM)
    BE->>DB: INSERT session = PENDING
    BE->>SKY: sky.launch(task, secret ECR_TOKEN)
    SKY->>EC2: สร้าง EC2 จาก AMI vlab-bake r2 (~30 วิ)
    SKY->>EC2: SSH ผ่าน router, เริ่ม skylet
    SKY-->>BE: ส่ง job แล้ว (job_id)
    Note over BE,EC2: setup ยังไม่เสร็จ! backend ต้องรอ
    EC2->>ECR: docker login + docker pull (~10 วิ)
    EC2->>EC2: docker run lab (code-server :8080)
    loop ทุก 5 วินาที (สูงสุด 10 นาที)
        BE->>SKY: job_status = RUNNING หรือยัง?
    end
    BE->>SKY: ขอ endpoint
    BE->>DB: UPDATE session = RUNNING + endpoint 10.10.2.x:8080
    BE-->>U: 201 + ลิงก์ IDE
    U->>EC2: เปิด IDE ผ่าน Tailscale router
```

---

## 4. ทุกทางที่ session จบได้

```mermaid
flowchart TD
    START(["กด Start"]) --> CHECK{"มี session<br/>PENDING / RUNNING<br/>อยู่แล้ว?"}
    CHECK -->|"ใช่ (PENDING ไม่เกิน 20 นาที)"| E409["409 กำลังเปิดอยู่"]
    CHECK -->|"ไม่"| TOKEN{"ขอ ECR token ได้?"}
    TOKEN -->|"ไม่ได้"| E500A["500<br/>ไม่มี record ไม่มีเครื่อง"]
    TOKEN -->|"ได้"| PENDING["session = PENDING"]
    PENDING --> LAUNCH{"สร้าง EC2 สำเร็จ?"}
    LAUNCH -->|"ไม่"| FAIL
    LAUNCH -->|"ใช่"| SETUP{"pull image ผ่าน?<br/>(รอ job_status)"}
    SETUP -->|"ไม่ (FAILED_SETUP)"| FAIL["session = FAILED<br/>sky.down ลบ EC2<br/>ตอบ 500"]
    SETUP -->|"ใช่"| RUNNING["session = RUNNING<br/>นักศึกษาใช้ IDE"]

    RUNNING --> END1["นักศึกษากดปิด<br/>(DELETE)"]
    RUNNING --> END2["ครบ lifespan_minutes<br/>(autostop)"]

    END1 --> DOWN1["SkyPilot ลบ EC2<br/>(ใช้ Skypilot-IAM)<br/>✅ ~11 วิ"]
    END2 --> DOWN2["skylet บน EC2 ลบตัวเอง<br/>(ใช้ role ของเครื่อง)<br/>✅ ~1.5 นาทีหลังครบเวลา"]
    DOWN2 --> STALE["⚠️ session ใน DB ยัง RUNNING<br/>(ไม่มีใครบอก backend)"]

    style FAIL fill:#fdd
    style DOWN2 fill:#dfd
    style STALE fill:#ffd
    style DOWN1 fill:#dfd
    style RUNNING fill:#dfd
```

- `lifespan_minutes` = **อายุสูงสุด** ของ lab (`wait_for: none`) ครบแล้วลบเลยแม้ยังใช้อยู่
- ถ้า backend ตายกลาง launch session จะค้าง PENDING ครบ 20 นาทีระบบจะเคลียร์ให้ตอนมีคนกด Start ใหม่

---

## 5. autostop ต้องผ่านอะไรบ้าง (เคยติด 3 จุด แก้ครบแล้ว)

```mermaid
flowchart TD
    T(["ครบ lifespan"]) --> S1["skylet บน EC2:<br/>Terminating head node"]
    S1 --> S2["skylet ตั้ง AWS_CONFIG_FILE=/dev/null<br/>(บังคับใช้ role ของเครื่อง)"]

    S2 --> G1{"ด่าน 1: ไปถึง EC2 API ไหม?"}
    G1 -->|"IPv4 ec2...amazonaws.com<br/>private subnet ออก IPv4 ไม่ได้"| X1["❌ ค้าง SYN-SENT ตลอด"]
    G1 -->|"dual-stack ec2...api.aws<br/>(ถ้ามี AWS_USE_DUALSTACK_ENDPOINT=true)"| G2

    G2{"ด่าน 2: role มีสิทธิ์อ่าน VPC / SG / instance ไหม?"}
    G2 -->|"เดิม: มีแค่ ECR หรือแค่ DescribeInstances"| X2["❌ UnauthorizedOperation<br/>(DescribeVpcs)"]
    G2 -->|"ใหม่: Describe 3 ตัว"| G3

    G3{"ด่าน 3: role มีสิทธิ์ลบเครื่องไหม?"}
    G3 -->|"TerminateInstances<br/>เฉพาะ tag skypilot-cluster-name"| OK["✅ EC2 ถูกลบ"]

    style X1 fill:#fdd
    style X2 fill:#fdd
    style OK fill:#dfd
```

| ด่าน | ปัญหา | แก้ที่ | สถานะ |
|---|---|---|---|
| 1 ทางเน็ต | skylet ข้าม `~/.aws/config` เลยไม่ใช้ dual-stack | AMI `ami-0da9046ec7f57f3af` (`vlab-bake-0.12.3.post1-r2`) มี `AWS_USE_DUALSTACK_ENDPOINT=true` ใน `/etc/environment` | ✅ |
| 2 อ่าน | ขาด `DescribeVpcs` / `DescribeSecurityGroups` | `terraform/lab_autostop.tf` (inline policy `skypilot-autostop`) | ✅ |
| 3 ลบ | role มีแค่สิทธิ์ ECR | `terraform/lab_autostop.tf` | ✅ |

เทสแล้ว (2026-10-11): lifespan 1 นาที ได้ 201 เวลา 21:20:39 → EC2 `shutting-down` เวลา 21:22:09
skylet เช็กทุก 1 นาทีและต้องปิด Ray ก่อน เลยช้ากว่า lifespan ราว 1–1.5 นาที

---

## 6. ขั้นต่อไป

autostop ใช้ได้แล้ว งานที่เหลือ

- **session ใน DB ไม่รู้ว่าเครื่องโดน autostop ลบ** ค้าง RUNNING จนมีคนกด Start ใหม่หรือ DELETE (กำลังออกแบบ)
- เปิดพอร์ต 5173 / 8443 ที่ router ถ้าจะใช้ lab ที่มีหลายพอร์ต (`lab_access.tf`)
- push `skypilot/music-lab` ขึ้น ECR ถ้าจะให้ lab OOP ไป AWS
- rule `0.0.0.0/0` ที่ SkyPilot เพิ่มใน SG ของ lab
- `terraform apply` บน Windows ให้ state ตรงกับของจริง (ถ้าใส่ policy ผ่าน Console)
- ลบ root access key ออกจาก ThinkPad

---

## ไฟล์ / branch ที่เกี่ยวข้อง

| อะไร | อยู่ที่ |
|---|---|
| โค้ด launch (backend) | `web-portal/backend/app/services/session_service.py` — branch `feature/sky-aws-launch` (PR #88) |
| รายละเอียด flow ของ API | `docs/Flow.md` — PR #88 |
| Terraform (VPC, router, role, สิทธิ์ autostop) | `terraform/` — branch `infra/ecr-pull-experiment` |
| script สร้าง AMI | `docker/bake/provision-ami.sh` — branch `infra/ecr-pull-experiment` |
| ผลทดลองทั้งหมด | `docs/EXPERIMENT_ECR_PULL_RESULT.md` — branch `infra/ecr-pull-experiment` |
