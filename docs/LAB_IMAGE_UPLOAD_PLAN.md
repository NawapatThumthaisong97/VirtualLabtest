# Container Image Upload: แผนปรับปรุงแบ่งเป็น Phase

> ที่มา: issue "Container Image Upload: แผนปรับปรุง" ของ Pete (ส่วนที่ 1 UX/UI และส่วนที่ 2.1-2.5)
> และคอมเมนต์เรื่อง Redis ใต้ issue
> เอกสารนี้แตกแผนนั้นเป็นงานที่ทำได้จริง บอกว่าแต่ละข้อต้องแก้ไฟล์ไหน แตะ infra ไหม และตรวจยังไงว่าเสร็จ
> เขียนตามโค้ด ณ 2026-11-18 (branch `feature/aws-dns`) อ่านคู่กับ [archive/LAB_IMAGE_SCAN_GUIDE.md](archive/LAB_IMAGE_SCAN_GUIDE.md)

## สารบัญ

| ข้อ | เรื่อง |
|---|---|
| 0 | [สรุปสั้น](#0-สรุปสั้น) |
| 1 | [ปัญหาที่แผนนี้แก้](#1-ปัญหาที่แผนนี้แก้) |
| 2 | [หลักที่ใช้ทุก Phase](#2-หลักที่ใช้ทุก-phase) |
| 3 | [Phase 1: ฟอร์มและการอัปโหลด](#3-phase-1-ฟอร์มและการอัปโหลด) |
| 4 | [Phase 2: รันเหมือนกันทุกที่ และแจ้งเมื่อพร้อมจริง](#4-phase-2-รันเหมือนกันทุกที่-และแจ้งเมื่อพร้อมจริง) |
| 5 | [Phase 3: scanner อ่าน config ของ image](#5-phase-3-scanner-อ่าน-config-ของ-image) |
| 6 | [Phase 4: แยก port บนเครื่องออกจาก port ของ app](#6-phase-4-แยก-port-บนเครื่องออกจาก-port-ของ-app) |
| 7 | [Phase 5: Smoke test ก่อน approve](#7-phase-5-smoke-test-ก่อน-approve) |
| 8 | [เรื่องที่ไม่ทำ: Redis](#8-เรื่องที่ไม่ทำ-redis) |
| 9 | [เรื่องที่ต้องตัดสินใจ](#9-เรื่องที่ต้องตัดสินใจ) |
| 10 | [ก่อนเริ่มงาน](#10-ก่อนเริ่มงาน) |

---

## 0. สรุปสั้น

| Phase | เรื่อง | ข้อใน issue | แก้ตรงไหน | Ansible | K8s manifest | Terraform | ขนาด |
|---|---|---|---|---|---|---|---|
| 1 | ฟอร์มอัปโหลด + อัปโหลดไม่หลุดเมื่อเปลี่ยนหน้า | ส่วนที่ 1, คอมเมนต์ Redis | frontend, schema, migration | – | – | – | เล็ก-กลาง |
| 2 | ห้องแลปกับ AWS รันเหมือนกัน, port จาก EXPOSE, readiness | 2.2, 2.5, ครึ่งแรกของ 2.1 | backend | – | – | – | เล็ก-กลาง |
| 3 | scanner อ่าน Cmd / Entrypoint / WorkingDir | ครึ่งหลังของ 2.1 | runner, backend, frontend | รัน role เดิมซ้ำ | – | – | เล็ก |
| 4 | port บนเครื่องแลปไม่ชนกัน (**ข้าม** ดูข้อ 6) | 2.4 | backend, migration | – | – | – | กลาง |
| 5 | smoke test ก่อน approve | 2.3 | backend, runner | **แก้ 2 role** | **ไฟล์ใหม่** | – | ใหญ่ |

- **ไม่มี Phase ไหนต้องแก้ Terraform** (มีเงื่อนไข ดูข้อ 6.6 และ 4.4)
- **ไม่มี Phase ไหนต้องเพิ่ม Redis** (ข้อ 8)
- Phase 1 + 2 ให้ประโยชน์ประมาณ 80% ของทั้งหมด ถ้ามีเวลาน้อยทำแค่นี้ก็พอ
- ทำ Phase ละ 1 branch / 1 PR ทุก Phase deploy แยกกันได้และถอยกลับได้ทีละอัน

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
  └──── ประโยชน์มากสุด ────┘     └─ ทำเมื่อพร้อม ─┘    └─ ตัดสินใจทีหลัง (มีทางเลือกที่ถูกกว่า)
```

---

## 1. ปัญหาที่แผนนี้แก้

| # | อาการ | สาเหตุในโค้ดตอนนี้ | แก้ใน Phase |
|---|---|---|---|
| 1 | อาจารย์ต้องกรอก Entrypoint ทุกครั้ง และค่าที่ระบบใส่ไว้ให้ใช้กับ image ส่วนใหญ่ไม่ได้ | ฟอร์มบังคับกรอก ([LabImageForm.tsx:375](../web-portal/frontend/src/components/instructor/LabImageForm.tsx#L375)), ค่าเริ่มต้น `/bin/bash /run.sh` และ port `8080, 5173, 8443` ([:95-97](../web-portal/frontend/src/components/instructor/LabImageForm.tsx#L95-L97)), schema `min_length=1` ([lab_image_schema.py:57](../web-portal/backend/app/schemas/lab_image_schema.py#L57)), คอลัมน์ `NOT NULL` ([lab_image.py:61](../web-portal/backend/app/models/lab_image.py#L61)) | 1 |
| 2 | ระหว่างอัปโหลด (~3 นาที) อาจารย์ต้องค้างอยู่หน้าเดิม เปลี่ยนหน้าแล้วอัปโหลดหยุด | สถานะการอัปโหลดเก็บไว้ใน component ([LabImageTab.tsx:99](../web-portal/frontend/src/components/instructor/LabImageTab.tsx#L99), [CreateLabModal.tsx:98](../web-portal/frontend/src/components/lab-builder/CreateLabModal.tsx#L98)) พอ component ถูกปิด การอัปโหลดก็หายไปด้วย | 1 |
| 3 | image ที่ตั้ง `ENTRYPOINT` ไว้ (เช่น code-server) เปิดในห้องแลปได้ แต่บน AWS พัง | AWS เอา `/bin/bash -c "<entrypoint>"` ไปต่อท้าย `docker run <image>` ([session_service.py:270](../web-portal/backend/app/services/session_service.py#L270)) ทำให้คำสั่งกลายเป็น argument ของ ENTRYPOINT เดิม ส่วนห้องแลปใช้ `command:` ซึ่งทับ ENTRYPOINT จริง ([warm_pod_service.py:118](../web-portal/backend/app/services/warm_pod_service.py#L118)) | 2 |
| 4 | นักศึกษาได้ลิงก์ตั้งแต่ app ยังไม่พร้อม กดเข้าไปเจอหน้า error | ห้องแลป: pod ไม่มี readinessProbe จึงถือว่า Ready ทันทีที่ container เริ่ม / AWS: `_wait_job_running` รอแค่ให้ job เป็น RUNNING ([session_service.py:859](../web-portal/backend/app/services/session_service.py#L859)) | 2 |
| 5 | lab สองตัวที่ใช้ port 8080 เปิดบนเครื่องเดียวกันไม่ได้ (ตัวที่สอง Pending) | `hostPort` = `containerPort` ([warm_pod_service.py:94](../web-portal/backend/app/services/warm_pod_service.py#L94)) | 4 |
| 6 | image ที่สแกนผ่านอาจเปิดไม่ขึ้นเลย และกว่าจะรู้ก็ตอนนักศึกษากดเปิดในคาบ | การสแกนตรวจแค่ความปลอดภัย ไม่ได้ลองรัน | 5 |

---

## 2. หลักที่ใช้ทุก Phase

1. **ช่องว่าง = ใช้ค่าจาก image** ระบบไม่เดาค่าแทนอาจารย์ และไม่เอาค่าที่อ่านจาก image ไปเขียนทับช่องที่อาจารย์กรอกเอง
2. **ห้องแลปกับ AWS ต้องรันแบบเดียวกัน** ถ้าเปิดในห้องแลปได้ บน AWS ก็ต้องเปิดได้ ทั้งสองที่ต้องใช้ `/bin/sh -c` ทับ entrypoint เหมือนกัน
3. **สถานะอยู่ใน Postgres** ไม่เพิ่ม middleware ใหม่ ([ARCHITECTURE.md](../ARCHITECTURE.md) CONSTRAINT 2) งานเบื้องหลังใช้ reconciler loop แบบที่ scan ใช้อยู่แล้ว
4. **backend ไม่รู้รหัสของ registry** (หลักข้อ 6 ของ scan guide) งานไหนต้อง push หรือลบใน registry ต้องทำใน pod ที่ mount Secret `registry-push`
5. **ทุก Phase ต้องมีเทส** โดยเฉพาะ manifest ที่สร้างจากฟังก์ชันล้วน (`build_*`) ซึ่งเทสได้โดยไม่ต้องมี cluster

---

## 3. Phase 1: ฟอร์มและการอัปโหลด

> ทำแล้ว รายละเอียดทุกจุดที่แก้และเหตุผลอยู่ใน [LAB_IMAGE_UPLOAD_WORKING.md](LAB_IMAGE_UPLOAD_WORKING.md)

### 3.1 เป้าหมาย
- อาจารย์ที่มี Dockerfile ถูกต้อง (มี `EXPOSE` และ `CMD`) กรอกแค่ไฟล์, repository:tag, description, CPU/RAM, lifespan ก็อัปโหลดได้
- ระหว่างอัปโหลด อาจารย์ไปหน้าอื่นในเว็บได้ และถ้าจะปิดแท็บระบบจะเตือนก่อน

### 3.2 ฟอร์ม (frontend)
ไฟล์: [LabImageForm.tsx](../web-portal/frontend/src/components/instructor/LabImageForm.tsx), [CreateLabModal.tsx](../web-portal/frontend/src/components/lab-builder/CreateLabModal.tsx)

| ช่อง | ตอนนี้ | หลังแก้ |
|---|---|---|
| ไฟล์ .tar, Repository / Tag, Description, CPU / Memory, Lifespan | อยู่ในฟอร์มหลัก | เหมือนเดิม |
| Entrypoint | บังคับกรอก, ค่าเริ่มต้น `/bin/bash /run.sh` | ย้ายเข้า **Advanced** (พับไว้), ว่างได้, placeholder "ว่าง = ใช้ค่าจาก image", hint "คำสั่งต้องรันค้าง ห้ามจบเอง" |
| Exposed ports | ค่าเริ่มต้น `8080, 5173, 8443` | Advanced, ว่างได้, hint "ว่าง = ใช้ EXPOSE ของ image" และ "app ต้อง bind 0.0.0.0 ไม่ใช่ 127.0.0.1" |
| Working directory | ค่าเริ่มต้น `/workspace` (ใน CreateLabModal) | Advanced, ว่างได้, hint "ใช้ path เต็ม" |
| Environment variables | – | Advanced, ว่างได้, hint "ห้ามใส่รหัสผ่านจริง" (scanner FAIL ถ้าเจอ secret ระดับ HIGH ใน ENV) |

ตารางนี้ใส่ไว้ในหน้าช่วยเหลือหรือ tooltip ของ Advanced ได้เลย:

| สถานการณ์ | ต้องกรอกไหม |
|---|---|
| Dockerfile มี `EXPOSE` และ `CMD` ถูกต้องแล้ว | ไม่ต้องกรอกเลย |
| ไม่มี `EXPOSE` หรืออยากเปิดแค่บาง port | กรอก Exposed ports |
| อยากรันคำสั่งอื่นแทน `CMD` ของ image | กรอก Entrypoint เช่น `/bin/bash /run.sh` |
| app ต้องใช้ค่า config | กรอก Environment |

### 3.3 Backend: ให้ entrypoint ว่างได้
- [lab_image_schema.py:57](../web-portal/backend/app/schemas/lab_image_schema.py#L57): `entrypoint_script: str | None = Field(None, max_length=255)` แปลง `""` เป็น `None`
- schema ตัวที่ใช้ตอบกลับ ([:131](../web-portal/backend/app/schemas/lab_image_schema.py#L131)): เปลี่ยนเป็น `str | None`
- [lab_image.py:61](../web-portal/backend/app/models/lab_image.py#L61): `nullable=True` และเอา `default` ออก
- **migration ใหม่:** `ALTER TABLE lab_images ALTER COLUMN entrypoint_script DROP NOT NULL` ข้อมูลเดิมไม่ต้องแปลง image เก่าที่มี `/bin/bash /run.sh` ก็รันแบบเดิมต่อไป
- [session_service.py:224](../web-portal/backend/app/services/session_service.py#L224) (`_build_k8s_task` ทางเก่าที่ผ่าน SkyPilot) ยังใช้ `or "/bin/bash /run.sh"` อยู่ ต้องตัดสินใจว่าจะลบทางนี้ทิ้ง หรือคงไว้แล้วจดว่าทางนี้ทับ CMD เสมอ (SkyPilot ต้องมี `run`) ห้องแลปตอนนี้ใช้ direct pod / warm pod เป็นหลัก ([session_service.py:800](../web-portal/backend/app/services/session_service.py#L800))
- frontend ที่แสดง `entrypointScript` ([LabImageTab.tsx:241](../web-portal/frontend/src/components/instructor/LabImageTab.tsx#L241)) ต้องรับ `null` แล้วแสดงว่า "ใช้ค่าจาก image"

### 3.4 อัปโหลดต่อได้เมื่อเปลี่ยนหน้า
ไฟล์ .tar วิ่งจาก browser ขึ้น R2 ตรง ๆ ผ่าน presigned PUT ([labImage.ts:117-133](../web-portal/frontend/src/services/labImage.ts#L117-L133)) server ไหนก็ส่งไฟล์แทน browser ไม่ได้ จึงต้องแก้ที่ frontend

1. **`UploadProvider` (React context) ระดับแอป** ห่อไว้เหนือ router เก็บรายการอัปโหลด `{id, fileName, repository, tag, progress, status, error}` และเรียก `labImageService.uploadArchive` จากตรงนี้แทน component
2. **แถบ progress ลอยที่มุมจอ** แสดงทุกการอัปโหลดที่ยังไม่จบ มองเห็นจากทุกหน้า กดแล้วไปหน้า Lab Image ได้
3. **`beforeunload`** ถ้ายังมีการอัปโหลดค้าง ให้ browser ถามก่อนปิดหรือ reload แท็บ
4. `LabImageTab` และ `CreateLabModal` เปลี่ยนเป็นเรียก `startUpload(...)` จาก context แล้วปิด modal ได้ทันที
5. หน้า Lab Image ดึงสถานะใหม่เองอยู่แล้ว ([LabImageTab.tsx:74](../web-portal/frontend/src/components/instructor/LabImageTab.tsx#L74)) พออัปโหลดเสร็จ แถวจะเปลี่ยนเป็น QUEUED → RUNNING → PASSED เอง

**ข้อจำกัดที่ยังอยู่:** reload หรือปิดแท็บแล้ว การอัปโหลดหายไป (ไฟล์อยู่ในหน่วยความจำของแท็บ) ถ้าอยากให้อัปโหลดต่อจากจุดเดิมได้เมื่อเน็ตหลุด ต้องเปลี่ยนไปใช้ multipart upload ของ R2 ซึ่งต้องแก้ backend (ออก presigned URL ทีละ part) และ worker งานนี้ไม่อยู่ในแผนรอบนี้ ทำเพิ่มทีหลังได้

### 3.5 เทส
- backend: สร้าง image โดยไม่ส่ง `entrypoint_script` แล้วได้ `None` ส่ง `""` แล้วได้ `None` และ manifest ของ pod ไม่มี `command`
- frontend: อัปโหลดแล้วเปลี่ยนหน้า แถบ progress ยังเดินต่อ / ปิดแท็บระหว่างอัปโหลดต้องมีคำเตือน

### 3.6 Deploy
backend: `alembic upgrade head` แล้ว restart / frontend: build ใหม่ ไม่ต้องแตะ infra

### 3.7 เสร็จเมื่อ
อัปโหลด image ของ code-server (มี ENTRYPOINT) โดยไม่กรอก Advanced เลย แล้ว lab เปิดได้ในห้องแลป

---

## 4. Phase 2: รันเหมือนกันทุกที่ และแจ้งเมื่อพร้อมจริง

> ทำแล้ว (ยังต้องลองบนเครื่องจริง) รายละเอียดอยู่ใน [LAB_IMAGE_UPLOAD_WORKING.md](LAB_IMAGE_UPLOAD_WORKING.md) ส่วน Phase 2

### 4.1 AWS ใช้ `--entrypoint` (ข้อ 2.2)
ไฟล์: [session_service.py:255-293](../web-portal/backend/app/services/session_service.py#L255-L293) (`_build_aws_task`)

```
ตอนนี้:  docker run ... <image> /bin/bash -c '<entrypoint>'
          → ถ้า image มี ENTRYPOINT คำสั่งนี้กลายเป็น argument ของมัน (พัง)
หลังแก้: docker run ... --entrypoint /bin/sh <image> -c '<entrypoint>'
          → ทับ ENTRYPOINT จริง เหมือน command: ["/bin/sh","-c",...] ของห้องแลป
```
- entrypoint ว่าง: ไม่ใส่ `--entrypoint` และไม่ต่ออะไรท้าย image (เหมือนเดิม)
- ใช้ `/bin/sh` ไม่ใช้ `/bin/bash` ให้ตรงกับห้องแลป (image เล็กอย่าง busybox/alpine ไม่มี bash) entrypoint ที่เขียนว่า `/bin/bash /run.sh` ก็ยังรันได้ เพราะ sh แค่ไปเรียก bash อีกต่อ
- ไม่ต้องแก้ AMI หรือ Terraform

### 4.2 Port จาก EXPOSE (ครึ่งแรกของ 2.1)
runner ส่ง `summary.image.exposedPorts` มาให้อยู่แล้ว ([runner.py:369-383](../scan-runner/runner.py#L369-L383)) จึงไม่ต้องแก้ scanner
- ใน `_collect` ([scan_reconciler.py:215-217](../web-portal/backend/app/services/scan_reconciler.py#L215-L217)) ตอน PASS: ถ้า `image.exposed_ports` ว่าง ให้แปลง `"8080/tcp"` → `8080` (เอาเฉพาะ tcp) แล้วบันทึกก่อน `approve_image`
- ถ้าทั้งอาจารย์ไม่กรอก และ image ก็ไม่มี EXPOSE: ยัง approve ได้ แต่เพิ่ม warning "ไม่พบ port: lab จะไม่มีลิงก์ให้นักศึกษา" ลง `scan_summary.warnings` ให้หน้าเว็บแสดง
- หลังจากนี้ ถ้าอาจารย์แก้ port ในหน้าแก้ไข ค่าที่อาจารย์กรอกชนะเสมอ

### 4.3 Readiness ในห้องแลป (ข้อ 2.5)
ไฟล์: [warm_pod_service.py:100-125](../web-portal/backend/app/services/warm_pod_service.py#L100-L125) (`_lab_container` ใช้ทั้ง warm pod และ direct pod)
```yaml
readinessProbe:
  tcpSocket: { port: <port แรกใน exposed_ports> }
  periodSeconds: 2
  failureThreshold: 90      # รอได้ ~3 นาที (เท่ากับ DIRECT_POD_READY_TIMEOUT)
```
- probe เดียวเช็กได้ port เดียว ถ้าจะเช็กทุก port ใช้ `exec` ไม่ได้ เพราะ image อาจไม่มี nc หรือ bash ทางเลือกคือ `startupProbe` + `readinessProbe` ของ port แรก (ส่วนใหญ่ port แรกคือ app หลัก) หรือให้ backend เช็ก port อื่นเพิ่มเองหลัง Ready ข้อนี้ต้องตัดสินใจ (ข้อ 9)
- direct pod รอ `is_ready` อยู่แล้ว ([session_service.py:802-810](../web-portal/backend/app/services/session_service.py#L802-L810)) เพิ่ม probe แล้วจะรอ app ที่พร้อมจริงทันที ไม่ต้องแก้ตรงนั้น
- warm pod (DaemonSet): pod ที่ยังไม่ Ready ต้องไม่ถูกแจกให้นักศึกษา ต้องตรวจโค้ดตอนเลือก warm pod ว่าเช็ก Ready ด้วยหรือไม่
- NetworkPolicy `vlab-lab-isolation` ปิดขาเข้าทั้งหมด แต่ kube-router ยังปล่อย traffic จากเครื่องตัวเอง ([lab-isolation-networkpolicy.yaml:7-11](../k8s/lab-isolation-networkpolicy.yaml#L7-L11)) probe ของ kubelet จึงควรผ่าน **ต้องลองบนเครื่องจริง** ที่เปิด `LAB_ISOLATION_ENABLED`

### 4.4 Readiness บน AWS (ข้อ 2.5)
ตอนนี้ `run` เป็น `docker run` แบบ foreground และ backend รอแค่ให้ job เป็น RUNNING ซึ่งเกิดทันทีที่ setup จบ

**วิธีที่เสนอ: ย้ายการเปิด container และการรอ port ไปไว้ใน `setup`**
```bash
# setup
echo "$ECR_TOKEN" | sudo docker login ...
sudo docker pull <image>
sudo docker run -d --name lab <args> <image> [...]
ip=$(sudo docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' lab)
for port in <ports>; do
  for i in $(seq 1 90); do
    [ "$(sudo docker inspect -f '{{.State.Running}}' lab)" = true ] || { sudo docker logs --tail 50 lab; exit 1; }
    timeout 1 bash -c "</dev/tcp/$ip/$port" && break
    sleep 2
  done || exit 1
done
# run
sudo docker logs -f lab & sudo docker wait lab
```
- ทำไมต้องใส่ใน `setup`: `_wait_job_running` ([session_service.py:859](../web-portal/backend/app/services/session_service.py#L859)) จะคืนค่าก็ต่อเมื่อ setup จบแล้ว job เป็น RUNNING การรอ port ใน setup จึงทำให้ "RUNNING = app พร้อม" โดยไม่ต้องแก้ตรงนั้น ถ้า app ไม่ขึ้น setup จะล้มเป็น `FAILED_SETUP` แล้ว `create_session` ลบเครื่องให้เองตามที่ทำอยู่แล้ว
- **ต้องเช็กที่ IP ของ container ไม่ใช่ `127.0.0.1:<port>`** เพราะ docker-proxy รับ TCP บน host port ได้ทันทีแม้ app ข้างในยังไม่ฟัง การเช็ก localhost จึงผ่านตลอด
- เอา `--rm` ออก ไม่งั้น container ที่ล้มจะหายไปพร้อม log (VM ถูกลบเมื่อ session จบอยู่แล้ว)
- ต้องเพิ่มเวลาของ `JOB_START_TIMEOUT` ให้ครอบช่วงรอ app (~3 นาที)
- เช็กบน VM เองจึง**ไม่ต้องแก้ Terraform** ถ้าให้ backend เช็กผ่าน router แทน port ที่อยู่นอก 3000-9999 จะโดน SG บล็อก ([security_groups.tf:138](../terraform/security_groups.tf#L138))
- prelaunch (เครื่องที่เปิดรอไว้ ดู [AWS_PRELAUNCH.md](AWS_PRELAUNCH.md)) ต้องตรวจว่าใช้ task เดียวกันหรือไม่ ถ้าใช้ก็ได้ readiness ไปด้วยเลย

### 4.5 เทส
- `test_task_builder.py`: AWS + entrypoint มี `--entrypoint /bin/sh` และ `-c` อยู่หลัง image / ไม่มี entrypoint ไม่มีทั้งสองอย่าง / setup มี loop รอ port ครบทุกตัว
- `test_direct_pod.py` / `test_warm_pod.py`: container มี `readinessProbe` ที่ port แรก / ไม่มี port ไม่มี probe
- reconciler: PASS + ports ว่าง + EXPOSE `["8080/tcp","53/udp"]` → `[8080]` / ports ที่อาจารย์กรอกไม่ถูกทับ / ไม่มีทั้งคู่ → มี warning

### 4.6 Deploy
restart backend อย่างเดียว

### 4.7 เสร็จเมื่อ
- image code-server ที่กรอก entrypoint เปิดได้ทั้งห้องแลปและ AWS
- image ที่ app ใช้เวลา 30 วินาทีกว่าจะขึ้น: session เป็น RUNNING หลัง app ขึ้นแล้ว ไม่ใช่ก่อน
- image ที่ app ล้มทันที: session ขึ้น FAILED พร้อมเหตุผล (ไม่ค้าง RUNNING)

---

## 5. Phase 3: scanner อ่าน config ของ image

> ทำแล้ว (ยังต้องรัน Ansible บน rn และลองสแกนจริง) รายละเอียดอยู่ใน [LAB_IMAGE_UPLOAD_WORKING.md](LAB_IMAGE_UPLOAD_WORKING.md) ส่วน Phase 3

### 5.1 ทำไม
ใน Phase 1 ช่องว่างแปลว่า "ใช้ค่าจาก image" แต่อาจารย์ยังมองไม่เห็นว่าค่านั้นคืออะไร Phase นี้ทำให้หน้า Lab Image แสดงได้ว่า "image นี้จะรัน: `code-server --bind-addr 0.0.0.0:8080`" และเตือนเมื่อ image ไม่มีคำสั่งให้รันเลย ซึ่งแปลว่า container จะจบทันที

**ค่าที่อ่านได้ใช้แสดงผลและเตือนเท่านั้น ห้ามเขียนลง `entrypoint_script`** เพราะเราจะเอาไปรันผ่าน `sh -c` ซึ่งทำงานไม่เหมือนกับที่ image รันเอง (exec form, ENTRYPOINT + CMD รวมกัน) ปล่อยว่างไว้ให้ Docker/K8s ใช้ค่าของ image เองดีกว่า

### 5.2 Runner ([runner.py](../scan-runner/runner.py))
- ใน `step_validate` ส่วนที่อ่าน config (บรรทัด ~369-383) เพิ่ม `entrypoint` (list), `cmd` (list), `workingDir` ลงใน `summary.image` ทุกค่าผ่าน `clip()` และจำกัดจำนวน element
- warning ใหม่: `image has no ENTRYPOINT or CMD` และ `image has no EXPOSE`
- `encode_result` ตัดผลให้ไม่เกิน 3,500 ไบต์ ต้องเพิ่ม `image.cmd` / `image.entrypoint` ไว้ในลำดับการตัดก่อนที่จะลบ `image` ทั้งก้อน
- เทส: เพิ่ม test ของ `step_validate` (หรือแยกฟังก์ชันล้วน `image_info(config)`) โดยใช้ config JSON ตัวอย่าง และ test ของ `encode_result` ที่ค่า cmd ยาวมาก

### 5.3 ขึ้นเวอร์ชันเป็น 1.2.0 (ต้องแก้ให้ตรงกัน 4 ที่)
| ที่ | ไฟล์ |
|---|---|
| `RUNNER_VERSION` | `scan-runner/runner.py` |
| `ARG RUNNER_VERSION` | `scan-runner/Dockerfile` |
| `scan_runner_version` | `ansible/roles/scan-runner-image/defaults/main.yml` |
| `SCAN_RUNNER_VERSION` | `web-portal/backend/app/configs/settings.py` |

ห้าม push ทับ 1.1.0 (immutable artifact)

### 5.4 Backend + frontend
- `_summary_from` ([scan_reconciler.py:338](../web-portal/backend/app/services/scan_reconciler.py#L338)) เก็บ `summary` ทั้งก้อนอยู่แล้ว ไม่ต้องแก้
- หน้า Lab Image ([LabImageTab.tsx:239-243](../web-portal/frontend/src/components/instructor/LabImageTab.tsx#L239-L243)): ช่องที่อาจารย์เว้นว่าง ให้แสดงค่าจาก `scanSummary.image` พร้อมป้าย "จาก image"

### 5.5 Deploy (ลำดับสำคัญ)
1. `ansible-playbook -i inventory.yml site.yml -K --limit rn --tags scan-runner` เพื่อ build และ push `vlab/scan-runner:1.2.0`
2. ตรวจ: `curl http://<rn>:5001/v2/vlab/scan-runner/tags/list` ต้องมี `1.2.0`
3. แล้วค่อย deploy backend ที่มี `SCAN_RUNNER_VERSION=1.2.0` ถ้าสลับลำดับ Job จะ `ErrImagePull`

### 5.6 เสร็จเมื่อ
อัปโหลด image แล้วหน้า Lab Image แสดงคำสั่งและ workdir ที่มาจาก image และ image ที่ไม่มี CMD ขึ้น warning

---

## 6. Phase 4: แยก port บนเครื่องออกจาก port ของ app

> **ตัดสินใจข้าม (2026-11-19)** การใช้งานจริงคือ ห้องแลป: 1 เครื่อง = 1 นักศึกษา = 1 lab และ AWS: 1 EC2 = 1 lab
> port จึงไม่ชนกันในการใช้งานปกติ กรณีขอบที่ยังชนได้มีแค่ในห้องแลป:
> - นักศึกษาวิชาอื่นนั่งเครื่องที่ warm pod ของวิชาที่มีคาบจองไว้ แล้วเปิด lab ที่ใช้ port เดียวกัน → ได้ error "เครื่องเต็ม" ทันที (`pod_problem` จับ Unschedulable)
> - คาบติดกัน: warm pod ของคาบถัดไปรอ (Pending) จน lab ของคาบก่อนปิด แล้วขึ้นเอง
>
> ทั้งสองกรณีไม่พังเงียบ ถ้าเจอบ่อยจริงค่อยกลับมาทำตามแผนข้างล่าง

### 6.1 ปัญหา
pod ของ lab ใช้ `hostPort` เท่ากับ port ของ app ([warm_pod_service.py:94](../web-portal/backend/app/services/warm_pod_service.py#L94)) เครื่องหนึ่งจึงเปิด lab ที่ใช้ 8080 ได้ทีละตัวเท่านั้น lab ตัวที่สองจะ Pending (`pod_problem` จับได้ว่า Unschedulable)

### 6.2 วิธีแก้
```
Lab A:  เครื่อง :20001  →  app :8080
Lab B:  เครื่อง :20002  →  app :8080   ✅ ไม่ชนกัน
```
- ตอน APPROVED ระบบจองเลข port บนเครื่องจากช่วง `LAB_HOST_PORT_MIN`–`MAX` (20000–29999) **ทีละ port ของ app** (image ที่มี 2 port ได้ 2 เลข)
- app ข้างในยังฟัง 8080 เหมือนเดิม และอาจารย์ไม่ต้องรู้เรื่องนี้เลย

### 6.3 สิ่งที่ต้องแก้
| ส่วน | รายละเอียด |
|---|---|
| ตารางใหม่ `lab_image_host_ports` | `host_port INT PRIMARY KEY`, `lab_image_id FK ON DELETE CASCADE`, `container_port INT`, unique `(lab_image_id, container_port)` ใช้ PK กันเลขซ้ำแทนการ lock เอง ถ้าสองคนจองพร้อมกัน ตัวที่ชนจะได้ IntegrityError แล้วลองเลขถัดไป |
| migration | สร้างตาราง + **backfill** ให้ image ที่ APPROVED อยู่แล้วทุกตัว |
| จองเลข | ใน `approve_image` ([lab_image_service.py:307](../web-portal/backend/app/services/lab_image_service.py#L307)) หาเลขว่างตัวแรกในช่วง ถ้าเต็มให้ approve ไม่ผ่านพร้อมข้อความที่ชัดเจน |
| แก้ port หลัง approve | ถ้าอาจารย์แก้ `exposed_ports` ให้คืนเลขที่ไม่ใช้แล้ว และจองเลขให้ port ใหม่ |
| คืนเลข | reject / ลบ image → CASCADE คืนเลขเอง |
| pod | `_host_port()` รับ `(container_port, host_port)` แล้วสร้าง `{"containerPort": 8080, "hostPort": 20001}` (ยังผูก `127.0.0.1` เมื่อเปิด isolation) |
| ลิงก์ | endpoints ([warm_pod_service.py:403-409](../web-portal/backend/app/services/warm_pod_service.py#L403-L409)) เปลี่ยนเป็น `{"8080": "http://<host>:20001"}` key ยังเป็น port ของ app หน้าเว็บจึงไม่ต้องแก้ |
| warm pod | DaemonSet ใช้ `_lab_container` เดียวกัน ได้เลขใหม่ไปด้วยเลย ต้องสร้าง DaemonSet เดิมใหม่ครั้งหนึ่งหลัง deploy |

### 6.4 เรื่องที่ต้องระวัง
- **app ที่สร้าง URL เต็มเอง** (เช่น Vite HMR ที่ต่อ websocket กลับมาที่ `:5173`) อาจพัง เพราะ browser เห็น `:20001` แต่ app คิดว่าตัวเองอยู่ที่ `:5173` เป็นปัญหาเดียวกับที่เจอตอนทำ lab gateway (ดู [AWS_LAB_GATEWAY.md](AWS_LAB_GATEWAY.md) เรื่อง Vite) ทางแก้คือส่ง env `VLAB_PUBLIC_URL_<port>` เข้า container เหมือน `gateway_envs`
- image ตัวเดียวกันยังเปิดบนเครื่องเดียวกันได้แค่ 1 ตัว เพราะเลขผูกกับ image ไม่ได้ผูกกับ session ห้องแลปนั่งเครื่องละคน ข้อนี้จึงรับได้
- ช่วง 20000–29999 รองรับได้ 10,000 port ถ้าทุก image มี 3 port จะได้ประมาณ 3,300 image

### 6.5 ไม่ต้องแก้ infra เพราะ
- ไม่ชนกับ NodePort ของ K3s (30000–32767)
- Ansible ไม่มี ufw หรือ iptables ที่ปิด port บน worker
- ถ้าเปิด `LAB_ISOLATION_ENABLED` port จะผูกกับ `127.0.0.1` จึงไม่ผ่าน Tailscale อยู่แล้ว ถ้าไม่เปิด ACL ก็ให้ `autogroup:member` เข้าได้ทุก port อยู่แล้ว (จะเพิ่ม test ใน `vlab-acl.hujson` ว่า worker → worker:20001 ต้อง deny ก็ได้)

### 6.6 AWS ไม่ใช้ Phase นี้
บน AWS หนึ่ง session ได้ VM หนึ่งเครื่อง port จึงไม่มีทางชนกัน คง `-p 8080:8080` ไว้เหมือนเดิม
**ถ้าวันหนึ่งจะใช้ 2xxxx บน AWS ด้วย** ต้องแก้ Terraform 2 rule ([security_groups.tf:134-141](../terraform/security_groups.tf#L134-L141) และ [:157-164](../terraform/security_groups.tf#L157-L164)) และ `LAB_GATEWAY_PORT_MIN/MAX` ([settings.py:259](../web-portal/backend/app/configs/settings.py#L259)) ซึ่งไม่คุ้ม

### 6.7 เทส
- จองเลขแล้วไม่ซ้ำ / เต็มแล้ว approve ไม่ผ่าน / ลบ image แล้วเลขกลับมาว่าง / แก้ port หลัง approve
- manifest: `containerPort != hostPort`, endpoints ชี้ไปที่ host port

### 6.8 เสร็จเมื่อ
เปิด lab 2 ตัวที่ใช้ 8080 บนเครื่องเดียวกันได้พร้อมกัน และลิงก์ของแต่ละตัวพาไปถูก lab

---

## 7. Phase 5: Smoke test ก่อน approve

### 7.1 ทำไม
การสแกนตรวจว่า image **ปลอดภัยไหม** แต่ไม่ได้ตรวจว่า **เปิดได้จริงไหม** image ที่สแกนผ่านยังพังตอนรันได้หลายแบบ
- คำสั่งรันจบเอง container ปิดทันที
- app ฟัง `127.0.0.1` ข้างนอกเข้าไม่ได้
- port ที่กรอกไม่ตรงกับที่ app ฟังจริง
- เรียกไฟล์ที่ไม่มีใน image หรือขาด env

ถ้าไม่มี smoke test เราจะรู้ว่าพังก็ตอนนักศึกษากดเปิดในคาบเรียน ซึ่งพังพร้อมกันทั้งห้อง

### 7.2 ทางเลือกที่ถูกกว่า (แนะนำให้ทำก่อน)
**ปุ่ม "ทดลองเปิด"** ในหน้า Lab Image ให้อาจารย์เปิด lab ของตัวเองผ่านระบบ launch ที่มีอยู่ หลังจบ Phase 2 ระบบจะรอให้ app พร้อมจริงก่อน ถ้าเปิดไม่ขึ้นอาจารย์จะเห็นเหตุผลทันที
- ข้อดี: ไม่ต้องแก้ Ansible, K8s หรือ registry
- ข้อเสีย: ขึ้นกับว่าอาจารย์กดลองหรือเปล่า ระบบไม่ได้รับประกันเอง

ทำ Phase 5 เต็มรูปแบบเมื่ออยากให้**ทุก** image ที่ approve ผ่านการลองเปิดมาแล้วแน่นอน

### 7.3 Flow ใหม่
```
สแกน PASS ──► push เข้า rn:5002/staging/<repo>:<tag>      (แทนที่จะเข้า vlab/ ตรง ๆ)
                 │
                 ▼
         smoke pod ใน namespace vlab-smoke (config เดียวกับ lab จริง)
         เช็ก: ① รันค้างได้ครบ 30 วินาที ② restartCount = 0 ③ ทุก port ตอบ
                 │
       ┌─────────┴──────────┐
     ผ่าน                  ไม่ผ่าน
       │                     │
 promote Job:           บันทึกเหตุผล + log ท้าย ๆ ให้อาจารย์ดู
 copy staging → vlab/   เก็บ staging ไว้ 7 วัน (แก้แล้วอัปใหม่ได้)
 → APPROVED             แล้ว drop Job ลบ staging + reject แถว
 → ecr-sync ส่งขึ้น ECR
```

### 7.4 ทำไมต้องมี namespace ใหม่ `vlab-smoke`
namespace คือ "ห้อง" ใน Kubernetes ที่แต่ละห้องตั้งกฎของตัวเองได้
- ห้อง `vlab-scan` ใช้ Pod Security ระดับ `restricted` ([scan-namespace.yaml:10](../k8s/scan-namespace.yaml#L10)) ซึ่ง**ห้าม pod รันเป็น root** แต่ lab image ส่วนใหญ่รันเป็น root (scanner ขึ้น warning "image runs as root" อยู่บ่อย ๆ) ถ้าเปิดในห้องนี้ K8s จะปฏิเสธตั้งแต่ยังไม่เริ่ม smoke test จะล้มทุกครั้ง ทั้งที่ image ไม่ได้เสีย
- quota ของ `vlab-scan` (4 CPU / 6Gi) ก็ถูกกำหนดไว้สำหรับ scanner ไม่ใช่สำหรับ lab

ไฟล์ใหม่ `k8s/smoke-namespace.yaml`:

| resource | ค่า | ทำไม |
|---|---|---|
| Namespace + Pod Security `baseline` | ยอมให้รันเป็น root ได้ แต่ยังห้าม privileged, hostPath, hostNetwork, **hostPort** | ให้เหมือนตอน lab จริงรันมากที่สุด แต่ยังกันของอันตราย (smoke pod ไม่ใช้ hostPort อยู่แล้ว) |
| `ResourceQuota` | เช่น 2 pods, limits 4 CPU / 8Gi | กัน smoke กินเครื่อง |
| NetworkPolicy `default-deny-ingress` | ปิดขาเข้า | probe ของ kubelet ยังผ่าน (kube-router ปล่อย traffic จากเครื่องตัวเอง) |
| NetworkPolicy `restrict-egress` | ดูข้อ 9 | เป็นโค้ดที่ยังไม่ผ่านการตรวจ |
| `PriorityClass` | ใช้ `vlab-scan` เดิม (-100, ไม่แย่งใคร) | ไม่เบียด lab ของนักศึกษา |

smoke pod ใส่ `nodeSelector` ให้ลง master เหมือน Job สแกน เพื่อไม่ไปแย่งเครื่องที่นักศึกษาใช้ และ master pull จาก `:5001` ได้ตาม ACL อยู่แล้ว

### 7.5 Ansible
| role | แก้อะไร | ทำไม |
|---|---|---|
| `k3s-server` (tag `scan`) | เพิ่ม task apply `k8s/smoke-namespace.yaml` ต่อจากที่ apply `scan-namespace.yaml` ([tasks/main.yml:157](../ansible/roles/k3s-server/tasks/main.yml#L157)) | ไม่พิมพ์ `kubectl apply` เองบนเครื่อง ลงเครื่องใหม่แล้วได้ครบเหมือนเดิม |
| `registry` | เพิ่ม systemd timer รัน `registry garbage-collect --delete-untagged` วันละครั้งตอนตี 3 โดยหยุด `camp-registry-push` ระหว่าง GC แล้วตรวจ `/v2/` หลังเปิดคืน | ลบ manifest ผ่าน API แล้ว blob ยังอยู่บนดิสก์ ตอนนี้ไม่มี GC เลย และการ GC ขณะมีคน push อยู่อาจทำ blob ที่กำลังเขียนเสีย |
| `ecr-sync` | ไม่ต้องแก้ ถ้าชื่อ staging ไม่ขึ้นต้นด้วย `vlab/` ([defaults/main.yml:23](../ansible/roles/ecr-sync/defaults/main.yml#L23) `^vlab/`) เพิ่ม `^staging/` ใน exclude ไว้กันพลาดก็ได้ | **ถ้าตั้งชื่อเป็น `vlab/staging/...` image ที่ยังไม่ผ่าน smoke จะขึ้น ECR ซึ่งเป็น IMMUTABLE ลบทับไม่ได้** |
| `scan-runner-image` | รันซ้ำเพื่อ build 1.3.0 | runner มีคำสั่งใหม่ |

### 7.6 Runner (ขึ้นเป็น 1.3.0, แก้ 4 ที่ตามข้อ 5.3)
- `publish`: ไม่ต้องแก้โค้ด backend แค่ส่ง `REPOSITORY=staging/<repo>` ต้องตรวจว่า `RE_REPOSITORY` รับชื่อนี้ได้
- **คำสั่งใหม่ `promote`**: `skopeo copy docker://<push>/staging/<repo>@<digest> docker://<push>/<repo>:<tag>` ใช้ authfile แบบเดียวกับ `step_push` เขียน digest ลง termination log แล้วลบ staging (`skopeo delete`)
- **คำสั่งใหม่ `drop`**: `skopeo delete docker://<push>/staging/<repo>@<digest>` ใช้ตอนครบ 7 วันหรือตอนอาจารย์อัปไฟล์ใหม่
- ทั้งสองคำสั่งรันเป็น Job ใน `vlab-scan` (มี Secret `registry-push` และ egress ไป :5002 อยู่แล้ว) เพราะ **backend ไม่รู้รหัส registry**
- skopeo policy ([policy.json](../scan-runner/policy.json)) ตอนนี้ยอมแค่ `docker-archive` / `oci-archive` ต้องเพิ่ม `docker` transport **เฉพาะ registry ของเรา** ให้ promote/drop ใช้ได้

### 7.7 Backend
| ส่วน | รายละเอียด |
|---|---|
| model + migration | คอลัมน์ใหม่ `smoke_status` (`NOT_STARTED / QUEUED / RUNNING / PASSED / FAILED / ERROR`), `smoke_summary` JSONB, `smoke_pod_name`, `smoke_finished_at`, `staging_digest` แยกจาก `scan_status` เพื่อไม่ให้ logic เดิมของ scan พัง |
| `scan_job_service` | `REPOSITORY` เป็น `staging/...` |
| `scan_reconciler._collect` | PASS → `staging_digest` + `smoke_status=QUEUED` (**ยังไม่ approve**, ยังไม่ลบ tar) |
| `smoke_service.py` (ใหม่) | `build_smoke_pod(image)` ใช้ `_lab_container` ของ Phase 2 (ได้ readinessProbe และ entrypoint แบบเดียวกับ lab จริง) แต่ไม่มี hostPort, image ชี้ `staging@digest`, `restartPolicy: Always` เพื่อนับ restart |
| ขั้นใน reconciler | `QUEUED` → สร้าง pod / `RUNNING` → Ready และ `restartCount == 0` ต่อเนื่อง 30 วินาที และทุก port ตอบ = ผ่าน; เกิน ~3 นาทีหรือ CrashLoop = ไม่ผ่าน (เก็บ log ท้าย ๆ ที่ผ่าน `clip` แล้วลง `smoke_summary`) → ลบ pod |
| promote | smoke ผ่าน → สร้าง promote Job → อ่านผล → `image_digest` + `approve_image` + ลบ tar จาก R2 |
| เก็บกวาด | `_reject_expired` ต้องสั่ง drop Job ก่อน reject ด้วย / อาจารย์อัปไฟล์ใหม่ระหว่างทาง → etag ไม่ตรง → drop staging เดิม |
| RBAC | backend ตอนนี้ใช้ kubeconfig ของทีมจาก WSL จึงสร้าง pod ใน namespace ใหม่ได้เลย ถ้าย้าย backend เข้า cluster (`k8s/auth/`) ต้องเพิ่ม Role ใน `vlab-smoke` และ `vlab-scan` |

**"ทุก port ตอบ" เช็กยังไง:** readinessProbe เช็กได้ port เดียว port ที่เหลือให้ reconciler เช็กเอง backend อยู่ใน tailnet และคุยกับ pod IP ตรง ๆ ไม่ได้ ทางที่ง่ายที่สุดคือใส่ readinessProbe ให้ port แรก แล้วใช้ `startupProbe` หรือ container เสริม (sidecar จาก image ของ scanner ซึ่งมี python3) เช็กทุก port ผ่าน `localhost` ภายใน pod

### 7.8 เทส
- manifest ของ smoke pod: namespace, ไม่มี hostPort, image เป็น digest, มี probe, ไม่มี service account token
- reconciler: ผ่าน / restart / timeout / etag เปลี่ยนระหว่าง smoke / ครบ 7 วัน → สั่ง drop แล้ว reject
- runner: `promote` และ `drop` ใช้ authfile และลบทิ้งใน `finally` (แบบเดียวกับ `test_push.py`)

### 7.9 Deploy (ลำดับสำคัญ)
1. Ansible `--limit rn --tags scan-runner,registry` → runner 1.3.0 + GC timer
2. Ansible `--limit mn --tags scan` → namespace `vlab-smoke`
3. ตรวจ: `kubectl get ns vlab-smoke --show-labels`, `kubectl -n vlab-smoke get networkpolicy,resourcequota`
4. `alembic upgrade head` แล้ว deploy backend
5. image ที่อยู่ระหว่างสแกนตอน deploy ยังไหลแบบเดิม (push เข้า `vlab/` ตรง) ไม่ต้อง migrate

### 7.10 เสร็จเมื่อ
- image ที่ CMD จบเอง → สแกน PASS, smoke FAILED พร้อม log, ไม่ถูก approve, ไม่ขึ้น ECR
- image ที่ดี → APPROVED, มีใน `vlab/` บน `:5001/v2/_catalog`, ขึ้น ECR, ไม่มีอะไรค้างใน `staging/`

---

## 8. เรื่องที่ไม่ทำ: Redis

คำถามใน issue: "ควรมี Redis ไหม เพราะตอนอัปโหลดต้องรอค้างหน้าเดิม 3 นาที"

**ไม่ต้องมี**
- **เวลาที่รอคือช่วงที่ไฟล์วิ่งจาก browser ขึ้น R2** ผ่าน presigned URL ไฟล์อยู่บนเครื่องอาจารย์ Redis หรือ server ตัวไหนก็ส่งแทนไม่ได้ ข้อนี้แก้ที่ frontend ใน Phase 1 (ข้อ 3.4)
- **การสแกนรันเป็น background อยู่แล้ว** (webhook → `QUEUED` → reconciler → K8s Job) ไม่ต้องมีใครมารับช่วงต่อ

งานที่ปกติคนเอา Redis มาทำ ระบบเรามีตัวทำแทนอยู่แล้ว:

| ปกติใช้ Redis ทำ | ระบบเราใช้ |
|---|---|
| คิวงาน | แถว `QUEUED` ใน Postgres + reconciler |
| worker | K8s Job |
| lock กันงานซ้อนเมื่อมี backend หลายตัว | `pg_try_advisory_lock` |
| กันกด Launch ซ้ำ | partial unique index ([thesis/scaling-redis-notes.md](../thesis/scaling-redis-notes.md)) |
| แจ้งสถานะไปหน้าเว็บ | polling |

ถ้าเพิ่ม Redis เราได้ service ใหม่ที่ต้องลง ต้องตั้งรหัส ต้องตั้ง ACL และต้องดูแลตอนมันล่ม และถ้า Redis restart แล้วข้อมูลหาย งานในคิวจะหายไปด้วย ซึ่งผิดหลัก "สถานะอยู่ใน DB" ที่ทำให้ backend ล่มแล้วกลับมาทำต่อได้

Redis จะจำเป็นก็ต่อเมื่อรัน backend หลาย replica แล้วต้องการ **rate limit** ร่วมกัน (ตามที่ทีมสรุปไว้ในโน้ตเดียวกัน)

**ของค้างที่ลบได้:** `REDIS_URL` ใน [settings.py:114](../web-portal/backend/app/configs/settings.py#L114) และ [.env.example:98](../web-portal/backend/.env.example#L98), `redis==5.2.1` ใน [requirement.txt:42](../web-portal/backend/requirement.txt#L42) ไม่มีโค้ดไหนใช้เลย (ทำรวมกับ Phase 1 ได้)

---

## 9. เรื่องที่ต้องตัดสินใจ

| # | คำถาม | ตัวเลือก | ข้อเสนอ |
|---|---|---|---|
| 1 | ทางเก่า `_build_k8s_task` (SkyPilot บน K3s) ยังใช้อยู่ไหม | ลบ / คงไว้ | ถ้าไม่มีใครใช้ให้ลบ จะได้ไม่มีทางที่สามที่รันไม่เหมือนชาวบ้าน |
| 2 | readiness เช็กกี่ port | port แรกอย่างเดียว / ทุก port | Phase 2 เช็ก port แรกก่อน ส่วนทุก port เก็บไว้ทำใน Phase 5 |
| 3 | Phase 5 ทำเต็ม หรือทำแค่ปุ่ม "ทดลองเปิด" | เต็ม / ปุ่ม | ทำปุ่มก่อน ใช้ไปสักพักแล้วค่อยตัดสินใจ |
| 4 | smoke pod ออกอินเทอร์เน็ตได้ไหม | ปิดหมด / 80+443 ยกเว้นช่วงภายใน (แบบ `vlab-scan`) | 80+443: lab จริงออกเน็ตได้ (`pip`, `npm`) ถ้าปิดหมด image ที่ติดตั้งของตอนเริ่มจะ smoke ไม่ผ่านทั้งที่ใช้งานจริงได้ |
| 5 | smoke รันที่ master หรือ worker | master / worker | master: ไม่แย่งเครื่องนักศึกษา แต่ต้องดูว่า master มี CPU/RAM พอ |
| 6 | ช่วง host port | 20000–29999 / ช่วงอื่น | 20000–29999 |

---

## 10. ก่อนเริ่มงาน

- [ ] เปิด Docker Desktop และ container `virtual_lab_db` ตอนนี้เทส backend ที่ใช้ DB ถูก skip ทั้งหมด (รันล่าสุด: 197 passed, 2 failed, **510 skipped**; 2 ตัวที่ fail คือเทส SIEM ที่ต้องใช้ Docker รัน Vector ไม่เกี่ยวกับงานนี้)
- [ ] รันเทสให้ผ่านครบก่อนแก้อะไร (ดูตัวเลข skipped ทุกครั้ง)
- [ ] แยก branch ใหม่จาก `main` ต่อ Phase เช่น `feature/lab-image-upload-p1`
- [ ] อ่าน [archive/LAB_IMAGE_SCAN_GUIDE.md](archive/LAB_IMAGE_SCAN_GUIDE.md) ข้อ 1, 2, 4, 6 ก่อนเริ่ม Phase 3 และ 5
