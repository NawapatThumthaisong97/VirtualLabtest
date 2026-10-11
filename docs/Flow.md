# Session Flow — เปิด/ปิด lab ไป K3s หรือ AWS

> อธิบายเส้น `POST /api/sessions` และ `DELETE /api/sessions/{id}` หลัง PR #88
> (`feature/sky-aws-launch`) ตั้งแต่ผู้ใช้กดปุ่มจนได้ endpoint ของ lab และตอนปิด lab

## 1. ภาพรวม

```
frontend (session.ts)
   │ POST /api/sessions {user_id, lab_id}
   ▼
session_route.py ─▶ SessionController ─▶ SessionService.create_session()
                                              │
                         อ่าน labs.run_target ─┤
                                              ├─ KUBERNETES ─▶ _build_k8s_task() ─▶ pod บน K3s
                                              └─ AWS ────────▶ _build_aws_task() ─▶ EC2 + docker run
                                              │
                                              ▼
                                  SkyPilot client (sky.launch)
                                              │ HTTP
                                              ▼
                                  SkyPilot API server ─▶ kubeconfig / AWS credential
```

ไฟล์ที่เกี่ยวข้อง

| ชั้น | ไฟล์ |
|---|---|
| route | `web-portal/backend/app/routes/session_route.py` |
| controller | `web-portal/backend/app/controllers/session_controller.py` |
| service (logic ทั้งหมด) | `web-portal/backend/app/services/session_service.py` |
| ขอ ECR token | `web-portal/backend/app/adapters/ecr_adapter.py` |
| model | `app/models/lab.py` (`run_target`), `app/models/session.py`, `app/models/lab_image.py` |
| config | `app/configs/settings.py`, `backend/.env` |

## 2. ตัวเลือก K3s / AWS อยู่ที่ไหน

- ตัวที่ตัดสินคือ **`labs.run_target`** (`KUBERNETES` | `AWS`) ตั้ง **ราย lab** ทุกคนที่เปิด lab
  เดียวกันไปที่เดียวกัน ไม่มีให้ผู้ใช้เลือก และไม่มี fallback ข้ามกัน
- `sessions.is_cloud` **ไม่ใช่ตัวเลือก** เป็นแค่บันทึกว่า session นี้รันที่ไหน
  (`is_cloud = run_target == AWS`) ไม่มีโค้ดไหนอ่านกลับไปตัดสินใจ
  แต่มีประโยชน์ตอนเปลี่ยน `run_target` ของ lab ทีหลัง เพราะ session เก่ายังบอกได้ว่ารันที่ไหน
- ตอนนี้ตั้ง `run_target` ผ่าน API ไม่ได้ (`LabCreateRequest`/`LabUpdateRequest` ไม่มี field นี้)
  ต้อง `UPDATE` ตรงใน DB หรือแก้ผ่านหน้า SQLAdmin

## 3. `create_session()` ทีละขั้น

```mermaid
sequenceDiagram
    autonumber
    participant FE as frontend
    participant SV as SessionService
    participant DB as Postgres
    participant ECR as AWS ECR
    participant SKY as SkyPilot API server

    FE->>SV: POST /sessions (user_id, lab_id)
    SV->>DB: หา user, lab
    SV->>DB: หา session RUNNING/PENDING ของ user+lab
    opt มี session เดิม
        SV->>SKY: sky.status(cluster เดิม)
        Note over SV: ไม่เจอ/STOPPED/error → ตั้ง STOPPED แล้วไปต่อ<br/>ยังอยู่ → 409 SessionAlreadyExists
    end
    SV->>DB: หา lab_image
    SV->>SV: cluster_name, run_target, build task (dict)
    opt run_target = AWS
        SV->>ECR: get_authorization_token()
    end
    SV->>DB: INSERT session (PENDING)
    SV->>SKY: sky.launch → stream_and_get → endpoints
    alt launch พัง
        SV->>DB: UPDATE FAILED + ended_at
        SV->>SKY: sky.down (ลบเงียบ ๆ)
        SV-->>FE: 500 cluster_operation_error
    else สำเร็จ
        SV->>DB: UPDATE RUNNING + sky_job_id + endpoints
        SV-->>FE: 200 {session_id, endpoints, ...}
    end
```

### 3.1 ตรวจ input
1. หา `User` ไม่เจอ → `UserNotFoundError` (404)
2. หา `Lab` ไม่เจอ → `LabNotFoundError` (404)

### 3.2 กันเปิดซ้ำ
หา session ของ `user_id + lab_id` ที่สถานะ `RUNNING` **หรือ `PENDING`** (PENDING เพิ่มใน PR นี้)
และยังไม่ถูก soft delete ถ้าเจอและมี `sky_cluster_name` จะถาม SkyPilot ว่า cluster ยังอยู่ไหม

| ผล `sky.status` | ทำอะไร |
|---|---|
| ไม่มี record | ตั้ง session เดิมเป็น `STOPPED` แล้วสร้างใหม่ต่อ |
| `STOPPED` / `AUTOSTOPPING` | ตั้ง `STOPPED` แล้วสร้างใหม่ต่อ |
| สถานะอื่น (`INIT`, `UP`) | ตอบ 409 `SessionAlreadyExistsError` |
| เรียกแล้ว error | print warning ตั้ง `STOPPED` แล้วสร้างใหม่ต่อ |

### 3.3 เตรียม image และชื่อ cluster
- ไม่มี `lab.image_id` → `LabImageMissingError` (400) / หา `LabImage` ไม่เจอ → 404
- `_cluster_name()`: เอาส่วนท้ายของ `repository` ทำเป็นตัวเล็ก แทนตัวที่ไม่ใช่ `a-z0-9-` ด้วย `-`
  แล้วต่อ unix time เช่น `skypilot/music-lab` → `music-lab-1791702290`

### 3.4 สร้าง task config
`create_fastapi_task()` คืน `dict` แล้วส่งเข้า `sky.Task.from_yaml_config()` ตรง ๆ
(เดิมต่อ YAML ด้วย f-string ซึ่งพังเมื่อ env มี `:`/`#` หรือ entrypoint หลายบรรทัด)

helper ที่ใช้ร่วมกัน
- `_lab_envs()` — `lab_image.env_vars` แปลงเป็น `str` ทุกค่า + `APP_ENV=staging`
  (copy ใหม่ ไม่แก้ dict ของ ORM เหมือนโค้ดเดิม)
- `_autostop()` — `idle_minutes = lifespan_minutes` (default 60), `down: true`, `wait_for: none`

#### K3s — `_build_k8s_task()`
SkyPilot รัน image ของ lab เป็น pod ตรง ๆ (container mode)

```yaml
name: music-lab-1791702290
resources:
  infra: kubernetes                 # ใช้ current-context ของ kubeconfig (ดูหัวข้อ 6)
  cpus: 2+                          # lab_images.cpu_requirement
  memory: 4+                        # lab_images.memory_requirement
  disk_size: 50
  image_id: docker:100.127.74.48:5001/skypilot/music-lab:lab-01   # DOCKER_REGISTRY_HOST
  ports: [8080, 5173, 8443]         # lab_images.exposed_ports
  autostop: {idle_minutes: 60, down: true, wait_for: none}
envs: {IDE_PASSWORD: musiclab, APP_ENV: staging}
workdir: ...                        # ถ้ามี
run: /bin/bash /run.sh              # lab_images.entrypoint_script
```

#### AWS — `_build_aws_task()`
VM mode: บูต EC2 จาก AMI ที่ bake SkyPilot runtime ไว้แล้ว (~1 นาที) แล้ว `docker run` image
จาก ECR เอง ไม่ใช้ `image_id: docker:` เพราะ container mode ต้องลง runtime ใหม่ทุกครั้ง (~5 นาที)

```yaml
name: music-lab-1791702290
resources:
  infra: aws/ap-southeast-1         # AWS_REGION
  instance_type: m7i-flex.large     # AWS_INSTANCE_TYPE
  disk_size: 30                     # AWS_DISK_SIZE
  image_id: ami-097929ad492bfc681   # AWS_LAB_AMI
  ports: [8080, 5173, 8443]
  autostop: {idle_minutes: 60, down: true, wait_for: none}
setup: |
  echo "$ECR_TOKEN" | sudo docker login -u AWS --password-stdin <ECR_REGISTRY_HOST>
  sudo docker pull <ECR_REGISTRY_HOST>/skypilot/music-lab:lab-01
run: |
  sudo docker run --rm --name lab -p 8080:8080 -p 5173:5173 -p 8443:8443 \
    -e IDE_PASSWORD=musiclab -e APP_ENV=staging <image> /bin/bash /run.sh
```

- ไม่ตั้ง `ECR_REGISTRY_HOST` หรือ `AWS_LAB_AMI` → `ClusterOperationError` ทันที
- env ของ lab ไปเป็น `-e` ของ `docker run` ไม่ใส่ `envs:` เพราะ `envs:` อยู่บน VM ไม่เข้า container
- ทุก argument ผ่าน `shlex.quote`
- `docker run` รัน foreground → SkyPilot นับว่า job ยังรัน autostop เริ่มนับ idle หลัง lab ปิดเท่านั้น
- registry ต้องเป็นชื่อ dual-stack (`...dkr-ecr.<region>.on.aws`) เพราะ private subnet ออกได้แค่ IPv6

### 3.5 ECR token (AWS เท่านั้น)
- `get_ecr_token()` ใช้ boto3 credential chain ของ backend เรียก `ecr:GetAuthorizationToken`
  แล้ว decode `base64("AWS:<password>")` เอาแค่ password (อายุ 12 ชม.)
- ขอ **ก่อน** INSERT session ถ้าขอไม่ผ่านจะไม่มี record ค้าง → `ClusterOperationError`
- ส่งเป็น `secrets_overrides=[("ECR_TOKEN", ...)]` SkyPilot ซ่อนค่าใน log/dashboard
  ไม่อยู่ใน YAML และไม่ลง DB ของเรา
- ต้องขอเองเพราะ SkyPilot login ECR อัตโนมัติได้แค่ชื่อ `.dkr.ecr.` + `.amazonaws.com`

### 3.6 บันทึก PENDING → launch → RUNNING
1. `INSERT` session `status=PENDING`, `sky_cluster_name`, `is_cloud`, `started_at`
   (`sky_job_id`, `endpoints` ยังเป็น `NULL`)
2. `sky.launch()` → `sky.stream_and_get()` (รอจนเสร็จ: K3s ไม่กี่สิบวินาที, AWS ~2.5 นาที
   HTTP request ค้างรอตลอด)
3. `sky.endpoints()` → แปลงเป็น `{"8080": "http://..."}`
4. `UPDATE` เป็น `RUNNING` + `sky_job_id` + `endpoints`

ถ้าข้อ 2–3 พัง: `UPDATE` เป็น `FAILED` + `ended_at` → `_down_quietly()` (`sky.down` แล้วรอ
ถ้าไม่มี cluster ก็ข้าม ถ้าลบไม่ได้แค่ print warning) → `ClusterOperationError` (500)

เหตุผลที่บันทึกก่อน launch: ถ้า launch พังกลางทาง ยังรู้ชื่อ cluster ไว้ตามลบ บน AWS cluster
ที่ไม่มี record คือ EC2 ที่เปิดค้างเสียเงิน

## 4. `delete_session()`

```
หา session ─ ไม่เจอ → 404
   │
   ├─ status RUNNING หรือ PENDING
   │     ├─ มี sky_cluster_name → sky.get(sky.down(name))   ← รอจนลบเสร็จจริง
   │     │       ├─ สำเร็จ              → cluster_stopped = true
   │     │       ├─ ClusterDoesNotExist → ข้าม (autostop ลบไปแล้ว)
   │     │       └─ error อื่น          → 500 (ไม่ลบ session)
   │     └─ ตั้ง STOPPED + ended_at
   │
   └─ soft delete (deleted_at)
```

`sky.down` ใช้ชื่อ cluster อย่างเดียว SkyPilot รู้เองว่าอยู่ K3s หรือ AWS จึงไม่ต้องดู `is_cloud`

## 5. สถานะ session

```
            INSERT
              │
              ▼
          PENDING ──launch พัง──▶ FAILED
              │
       launch สำเร็จ
              ▼
          RUNNING ──DELETE / ตรวจเจอว่า cluster หาย──▶ STOPPED
```

## 6. ใช้ cluster ไหน

- backend **ไม่ได้คุยกับ K3s เอง** ทุกอย่างผ่าน SkyPilot client → SkyPilot API server
  (`~/.sky/config.yaml` → `api_server.endpoint`)
- `infra: kubernetes` ใช้ **current-context** ของ kubeconfig ที่ฝั่ง SkyPilot อ่าน ตอน deploy
  ด้วย Ansible คือ `KUBECONFIG=/app/kubeconfig.yaml` ใน container backend ซึ่ง role
  `web-portal` ดึงมาจาก master แล้วเปลี่ยน `server:` เป็น Tailscale IP ของ master
- 1 master (k3s server) = 1 cluster เครื่องที่บ้านกับเครื่องที่มหาลัยถ้าต่างคนต่างรัน k3s server
  เป็น **2 cluster แยกกัน** และ backend จะใช้ตัวที่ kubeconfig ชี้อยู่ตัวเดียว
- ถ้าอยากให้ SkyPilot ใช้หลาย cluster: ใส่หลาย context ใน kubeconfig แล้วตั้ง
  `kubernetes.allowed_contexts` ใน config ของ SkyPilot → `infra: kubernetes` จะลองทีละ context
  (failover) หรือระบุ `infra: kubernetes/<context>` เพื่อบังคับตัวเดียว (โค้ดตอนนี้ยังไม่ได้ทำ)
- `DOCKER_REGISTRY_HOST` ต้องเป็น registry ที่ node ของ cluster นั้น pull ได้ด้วย

## 7. Config ที่ใช้

| ค่า | ใช้กับ | ที่มา |
|---|---|---|
| `DOCKER_REGISTRY_HOST` | K3s | `.env` (default `100.127.74.48:5001`) |
| `KUBECONFIG` | K3s | env ของ process ที่รัน SkyPilot |
| `AWS_REGION` | AWS | `.env` (default `ap-southeast-1`) |
| `AWS_LAB_AMI` | AWS | `.env` (ต้องตั้ง) |
| `AWS_INSTANCE_TYPE` | AWS | `.env` (default `m7i-flex.large`) |
| `AWS_DISK_SIZE` | AWS | `.env` (default `30`) |
| `ECR_REGISTRY_HOST` | AWS | `.env` (ต้องตั้ง, dual-stack) |
| AWS credential | AWS | boto3 chain ของ backend + ฝั่ง SkyPilot API server |

## 8. ข้อที่ยังมีปัญหา (จากการเทส offline 2026-10-11)

| # | เรื่อง | รายละเอียด |
|---|---|---|
| 1 | AWS: entrypoint หลายบรรทัด | `run` เอา entrypoint ไปต่อท้าย `docker run` ตรง ๆ ถ้ามีหลายบรรทัด บรรทัดแรกเข้า container ที่เหลือรันบน VM (ฝั่ง K3s ไม่มีปัญหานี้) |
| 2 | ชื่อ cluster ขึ้นต้นด้วยตัวเลข | repo เช่น `org/2048-game` ได้ `2048-game-<ts>` ซึ่ง SkyPilot ปฏิเสธ (regex ต้องขึ้นต้นด้วยตัวอักษร) |
| 3 | ตัวกัน PENDING ไม่แน่น | session PENDING มีชื่อ cluster เสมอ เลยไปเข้า `sky.status` ถ้ายังไม่มี record ของ cluster (launch ยังอยู่ในคิว) หรือเรียก status แล้ว error จะถูกตั้งเป็น `STOPPED` แล้วปล่อยให้ launch ซ้ำได้ และถ้า backend ตายระหว่าง launch จะเหลือ PENDING ค้าง |
| 4 | race ของ 2 request พร้อมกัน | ทั้งคู่ผ่านการเช็กก่อนที่อีกตัวจะ INSERT (มีมาตั้งแต่ก่อน PR) |
| 5 | `DB_DIAGRAM.md` | เขียนค่าเป็นตัวเล็ก แต่ใน DB เก็บ `KUBERNETES`/`AWS` |
