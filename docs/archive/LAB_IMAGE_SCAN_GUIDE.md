# Lab Image Scan: การทำงานของระบบทั้งหมด

เอกสารนี้อธิบายโค้ดที่ใช้จริงของ pipeline สแกน lab image ตั้งแต่อาจารย์อัปโหลดไฟล์จนถึง image ขึ้น ECR
เหตุผลด้านดีไซน์อยู่ใน `LAB_IMAGE_SCAN_ARCHITECTURE.md` และรายละเอียด threat model ของ image อยู่ใน `SCAN_RUNNER_IMAGE.md`

| ส่วน | ไฟล์ | รันที่ไหน |
|---|---|---|
| webhook ตั้งคิว | `web-portal/backend/app/services/lab_image_service.py` (`handle_upload_event`) | backend |
| Reconciler | `web-portal/backend/app/services/scan_reconciler.py` | backend (background task) |
| สร้าง Job | `web-portal/backend/app/services/scan_job_service.py` | backend (reconciler เรียก) |
| Scanner image | `scan-runner/` (`Dockerfile`, `runner.py`, `policy.json`) | Pod ใน namespace `vlab-scan` |
| Namespace / NetworkPolicy | `k8s/scan-namespace.yaml` (apply โดย role `k3s-server`) | K3s |
| Build scanner image | `ansible/roles/scan-runner-image/` | เครื่อง registry |
| Sync ขึ้น ECR | `ansible/roles/ecr-sync/` | เครื่อง registry (systemd timer) |

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
                 │  QUEUED → สร้าง Job + Secret → RUNNING                  │
                 │  อ่านผลจาก termination message ของ container publish    │
                 └──────────────────────────────────────────────────────────┘
                                                         │
                        PASS: push เข้า camp registry → APPROVED → ลบ tar จาก R2
                        FAIL / ERROR: บันทึกผล → ครบ 7 วัน reject (ลบ tar + ลบแถว)
                                                         │
                 เครื่อง registry: vlab-ecr-sync.timer (ทุก ~2 นาที) → skopeo copy ขึ้น ECR
```

หลักการสำคัญ
- **webhook ไม่เรียก K8s** แค่ตั้ง `QUEUED` แล้วตอบทันที cluster ล่มก็ไม่ทำให้ webhook ล้ม
- **reconciler เป็นเจ้าของ K8s คนเดียว** ทั้งเปิด Job อ่านผล และลบ Job
- **สถานะอยู่ใน DB ทั้งหมด** backend restart แล้วรอบถัดไปทำต่อได้เอง
- **Pod ไม่คุยกับ backend** backend อ่านผลจาก K8s API เอง Pod จึงไม่ต้องมี credential ของ backend

### สถานะของการสแกน
```
NOT_STARTED ──(ไฟล์ขึ้น R2)──► QUEUED ──(reconciler เปิด Job)──► RUNNING
                                  ▲                                   │
                                  └──── retry / อัปไฟล์ทับ ────────────┤
                                                                      ▼
                                                      PASSED / FAILED / ERROR
```
`status` ของ image (`PENDING` → `APPROVED`) แยกจากสถานะสแกน: `APPROVED` เกิดได้จาก PASS เท่านั้น

---

## 2. Webhook: `LabImageService.handle_upload_event`

เรียกเมื่อ Cloudflare Worker แจ้งว่ามีไฟล์ขึ้น R2 (ยืนยันตัวตนด้วย header `Webhook-Secret`)

1. หาแถวจาก `object_key` ไม่เจอ = ไม่ใช่ไฟล์ที่ระบบออก presign ให้ ตอบ `updated=false` (2xx เพื่อให้ Worker ไม่ retry)
2. เทียบ ETag ใหม่กับของเดิม ถ้าต่างกันหรือยังไม่เคยมีไฟล์ = **ไฟล์ใหม่**
3. บันทึก etag, ขนาด, เวลาอัปโหลด
4. ตั้ง `QUEUED` และรีเซ็ตจำนวนครั้งที่ลอง **เฉพาะเมื่อ** เป็นไฟล์ใหม่ + image ยัง `PENDING` + ยังสแกนไม่จบ
   - event ซ้ำ (etag เดิม) ไม่รีเซ็ต กัน Job ที่กำลังรันถูกนับใหม่
   - สแกนจบแล้วไม่เริ่มใหม่ เพราะไฟล์ที่ push ไปแล้วคือไฟล์ที่ถูกสแกน

**การบังคับชื่อ** (`lab_image_schema.py`): ตอนขอ presign `repository` ต้องขึ้นต้นด้วย `vlab/` และห้ามเป็น `vlab/scan-runner` ไม่งั้นได้ 400 (`repository_prefix` / `repository_reserved`) เหตุผลคือ IAM ของ ECR sync มีสิทธิ์แค่ `repository/vlab/*` ชื่อนอก prefix จะสแกนผ่านแต่ขึ้น ECR ไม่ได้

---

## 3. Scan Reconciler (`scan_reconciler.py`)

### 3.1 การเริ่มและวนรอบ
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

### 3.2 `run()`: 4 ขั้นต่อรอบ
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

### 3.3 อ่านสถานะจาก K8s
- `read_scan_jobs(k8s)` เรียก API แค่ 2 ครั้งต่อรอบ: list Job และ list Pod ด้วย label `vlab/scan=true` แล้วจับคู่ Pod กับ Job ผ่าน label `job-name` ที่ K8s ใส่ให้เอง คืน `dict[ชื่อ Job, JobState]`
- `_job_kind(job)` อ่าน condition ของ Job: `Failed` → `FAILED` (พร้อม reason เช่น `DeadlineExceeded`), `Complete` → `SUCCEEDED`, อื่นๆ → `ACTIVE` ส่วน Job ที่ไม่อยู่ใน dict ถือว่าหาย
- `_pod_result(pod)` อ่าน termination message ของ container `publish` แล้ว parse เป็น JSON (อ่านไม่ได้ = `None`)
- `delete_scan_job(k8s, name)` ลบ Job ด้วย `propagation_policy="Background"` (Pod และ Secret ถูกลบตาม) 404 ถือว่าสำเร็จ

### 3.4 ขั้น 2: `_collect` เก็บผลของแถว `RUNNING`

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

### 3.5 ขั้น 3: `launch_queued` เปิด Job ให้แถว `QUEUED`
1. คำนวณที่ว่าง = `SCAN_MAX_CONCURRENT` (2) − จำนวน `RUNNING` ถ้าเต็มก็จบ
2. ถ้ายังไม่ได้ตั้ง registry (`DOCKER_REGISTRY_HOST` / `scan_runner_image`) ไม่เปิด Job และไม่เผาจำนวนครั้งที่ลอง เพราะไม่ใช่ความผิดของแถว
3. วนแถว `QUEUED` เรียงตามเวลาอัปโหลด (มาก่อนได้ก่อน) เท่าที่ว่าง
   - ข้ามแถวที่ไม่ใช่ `PENDING`
   - ไม่มี etag หรือขนาดไฟล์ → `ERROR` ทันที เพราะตรวจว่าไฟล์ตรงกับที่บันทึกไม่ได้
4. ลบ Job ของรอบก่อน (ถ้ามี) ไม่งั้นผลเก่าอาจถูกอ่าน
5. **commit ก่อนแตะ K8s:** เพิ่มจำนวนครั้ง, ตั้งชื่อ Job ใหม่, `RUNNING`, เวลาเริ่ม ถ้าสร้าง Job ไม่สำเร็จ รอบหน้าจะเห็น Job หายแล้ว retry เอง จึงไม่มีทางได้ Job ซ้ำ
6. `launch_scan_job(...)` ถ้าล้มแค่ log แล้วไปแถวถัดไป แถวเดียวพังไม่หยุดแถวอื่น

### 3.6 ขั้น 4: เก็บกวาด
- `_delete_orphan_jobs` ลบ Job ที่มี label `vlab/scan` แต่ไม่ใช่ Job ปัจจุบันของแถว `RUNNING` ไหนเลย เช่นแถวถูกลบ หรือถูกแทนด้วยรอบใหม่ (เรียก `db.expire_all()` ก่อน เพื่ออ่านค่าล่าสุดหลังขั้น 2-3)
- `_reject_expired` แถว `FAILED`/`ERROR` ที่จบเกิน `SCAN_FAILED_RETENTION_DAYS` (7 วัน) → `reject_image` (ลบ tar จาก R2 แล้วลบแถว คืนชื่อ `repository:tag` ให้ใช้ใหม่) ระยะ 7 วันมีไว้ให้อาจารย์ได้เห็นเหตุผลก่อน ถ้า reject ไม่ได้ (ถูกอ้างอิงอยู่, R2 ลบไม่ได้) จะข้ามไปลองรอบหน้า

### 3.7 ค่าที่เกี่ยวข้อง (`settings.py`)
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
| `SCAN_RUNNER_IMAGE` / `SCAN_RUNNER_VERSION` | ว่าง / `1.0.0` | ถ้าไม่ตั้ง image จะเป็น `<DOCKER_REGISTRY_HOST>/vlab/scan-runner:<version>` (`settings.scan_runner_image`) |

---

## 4. `scan_job_service.py`

สร้าง K8s Job ที่รัน scanner กับ tar ของ image หนึ่งแถว เรียกจาก `launch_queued` เท่านั้น

| ชื่อ | ทำอะไร |
|---|---|
| `ScanJobConfigError` | exception เมื่อตั้งค่าไม่ครบ (ไม่มี registry) แยกจาก error ของแถว |
| `scan_job_name(image, attempt)` | สร้างชื่อ `scan-{id 12 ตัว}-{etag 8 ตัว}-a{attempt}` ยาวไม่เกิน 63 ตัว ใช้ได้ทั้งเป็นชื่อ Job และ Secret ชื่อเปลี่ยนเมื่อไฟล์หรือรอบเปลี่ยน ไม่มี etag ใช้ `noetag` |
| `_labels(image, job_name)` | label `vlab/scan=true`, `vlab/scan-image-id`, `vlab/scan-job` ใส่ทั้ง Job, Pod และ Secret (reconciler หาด้วย `vlab/scan=true`) |
| `_env(values)` | แปลง dict เป็นรายการ env ของ K8s ข้ามค่าว่าง |
| `_container(name, args, env, requests, limits, extra_mounts)` | สร้าง container หนึ่งตัวด้วย image ของ scanner + securityContext ชุดเดียวกัน: ห้ามยกสิทธิ์, rootfs read-only, non-root 10001, drop ALL capabilities, seccomp `RuntimeDefault`, mount `/work` |
| `build_scan_job(image, job_name)` | สร้าง manifest ของ Job เป็น dict (ฟังก์ชันล้วน ไม่แตะ cluster) |
| `build_download_secret(image, job_name, url, job_uid)` | สร้าง Secret ชื่อเดียวกับ Job มี key `download_url` และ `ownerReferences` ชี้ Job |
| `_uid_of(obj)` | อ่าน `metadata.uid` ของ Job ได้ทั้งจาก dict และ object ของ SDK |
| `launch_scan_job(k8s, r2, image, job_name)` | สร้าง Job แล้วสร้าง Secret (รายละเอียดข้างล่าง) |
| `_delete_job_quietly(k8s, job_name)` | ลบ Job แบบไม่โยน error ใช้ตอนสร้าง Secret ไม่สำเร็จ |

### 4.1 Manifest ของ Job (`build_scan_job`)
- **Container 4 ตัว ใช้ image เดียวกัน** ต่างกันที่คำสั่งย่อย และส่ง env เฉพาะที่ขั้นนั้นใช้
  | container | ชนิด | env | requests / limits | พิเศษ |
  |---|---|---|---|---|
  | `fetch` | init | `IMAGE_ID`, `ETAG`, `EXPECTED_SIZE` | 100m/128Mi → 1/256Mi | mount Secret ที่ `/secrets/fetch` (read-only) **ตัวเดียว** |
  | `validate` | init | `IMAGE_ID`, `ETAG`, `ALLOWED_ARCH=amd64`, `DECLARED_PORTS` | 100m/256Mi → 1/1Gi | |
  | `scan` | init | `IMAGE_ID`, `ETAG`, `POLICY_FAIL_SEVERITY`, `POLICY_IGNORE_UNFIXED=true` | 500m/1Gi → 2/4Gi | |
  | `publish` | main | `IMAGE_ID`, `ETAG`, `REGISTRY`, `REPOSITORY`, `TAG` | 100m/256Mi → 1/1Gi | ชื่อต้องเป็น `publish` ตรงตัว (reconciler อ่านผลจากตัวนี้) |
- **Pod:** `restartPolicy: Never`, ไม่ mount service account token, `enableServiceLinks: false` (ไม่ใส่ env ของ Service อื่น), securityContext ระดับ Pod เป็น non-root 10001 + `fsGroup`, ใส่ `priorityClassName` ถ้าตั้งไว้
- **Volume:** `work` เป็น `emptyDir` จำกัด `SCAN_WORK_SIZE_LIMIT`, `download-url` เป็น Secret ชื่อเดียวกับ Job สิทธิ์ `0400` มีแค่ key `download_url`
- **Job:** `backoffLimit: 0` (การ retry เป็นหน้าที่ reconciler ซึ่งนับจำนวนครั้งเอง), `activeDeadlineSeconds: SCAN_JOB_DEADLINE_SECONDS`, `ttlSecondsAfterFinished: 3600` (กันค้าง ปกติ reconciler ลบทันทีที่ได้ผล)

### 4.2 ลำดับของ `launch_scan_job`
1. สร้าง manifest แล้ว `create_namespaced_job` ถ้าได้ 409 (มี Job ชื่อนี้แล้ว เช่นรอบก่อนสร้างไปแต่ commit ไม่ทัน) อ่าน Job เดิมมาใช้
2. ออก presigned GET **ตอนนี้** ไม่ใช่ตอนเข้าคิว URL จึงสดเสมอ
3. สร้าง Secret ที่มี `ownerReference` ชี้ uid ของ Job
   - ได้ 409 → `replace` ด้วย URL ใหม่
   - error อื่น → ลบ Job ที่เพิ่งสร้างแล้วโยน error ให้ reconciler จัดการรอบหน้า

ทำไมสร้าง Job ก่อน Secret: Secret ต้องรู้ uid ของ Job เพื่อผูก ownerReference ส่วน Pod จะรอที่ `ContainerCreating` (เห็นเป็น `Init:0/3`) จนกว่า Secret มา เพราะ kubelet retry การ mount เอง เมื่อลบ Job แล้ว garbage collector ลบ Secret ตาม จึงไม่มี URL ค้างใน cluster

---

## 5. Scanner Image (`scan-runner/`)

### 5.1 ข้างใน image (`Dockerfile`)
- **2 stage:** ดึงแค่ binary `trivy` จาก `ghcr.io/aquasecurity/trivy:0.76.1@sha256:...` มาวางบน `alpine:3.24@sha256:...` ทั้งสองตัว pin ด้วย digest ค่าจริงส่งมาจาก Ansible
- ติดตั้ง `python3`, `skopeo`, `ca-certificates` แล้ว:
  - สร้าง user `scanner` (10001:10001) ไม่มี shell (`/sbin/nologin`) ไม่มี home
  - ถอดบิต setuid/setgid ทุกไฟล์ และลบ `apk` ทิ้ง ใน container จึงติดตั้งอะไรเพิ่มหรือยกสิทธิ์ไม่ได้
- `trivy`, `runner.py` (0555) และ `policy.json` (0444) เป็นของ root user 10001 แก้ไม่ได้
- `HOME`, `TMPDIR`, `TRIVY_CACHE_DIR` อยู่ใต้ `/work` ทั้งหมด rootfs จึงตั้ง read-only ได้
- `ENTRYPOINT ["python3", "-I", "/opt/vlab-scan/runner.py"]` (`-I` = isolated mode ไม่อ่าน env `PYTHON*` และ user site-packages) ค่าเริ่มต้น `CMD ["version"]`
- ไม่มีบรรทัด `# syntax=` เพราะจะดึง frontend image เพิ่มอีกตัวที่ไม่ได้ pin

`policy.json` ของ skopeo: `default: reject` ยอมรับเฉพาะ transport `docker-archive` และ `oci-archive` (ไฟล์ในเครื่อง) ต่อให้ argument ถูกปลอม skopeo ก็ไม่ดึง image จาก registry ภายนอก

#### โครงไฟล์ใน image
| path | เจ้าของ / สิทธิ์ | คืออะไร |
|---|---|---|
| `/opt/vlab-scan/runner.py` | root, 0555 | logic ทั้งหมด (คอมไพล์ตรวจ syntax ตอน build แล้วลบ `__pycache__`) |
| `/usr/local/bin/trivy` | root, 0555 | binary ที่ copy มาจาก image ทางการของ Trivy |
| `/etc/vlab-scan/policy.json` | root, 0444 | trust policy ของ skopeo |
| `/usr/bin/skopeo`, `/usr/bin/python3` | root (จาก apk) | tool ที่ runner เรียก |
| `/work` | 10001, เขียนได้ | ใน Pod ถูกทับด้วย `emptyDir` เป็นที่เดียวที่เขียนได้ |
| `/secrets/fetch/download_url` | mount ตอนรัน, 0400 | มีเฉพาะใน container `fetch` |

#### ลำดับการ build ใน `Dockerfile`
1. `FROM ${TRIVY_IMAGE} AS trivy` ดึง image ของ Trivy มาเป็น stage ชั่วคราว (ใช้แค่ binary)
2. `FROM ${BASE_IMAGE}` เริ่ม image จริงจาก Alpine ที่ pin digest
3. `RUN apk add ... && addgroup/adduser ... && find / -perm /6000 -exec chmod a-s ... && rm -rf /sbin/apk ...` ทุกอย่างอยู่ใน `RUN` เดียว layer สุดท้ายจึงไม่มี apk หลงเหลือ
4. `COPY --from=trivy`, `COPY policy.json`, `COPY runner.py`
5. `RUN chown root ... chmod 0555/0444 ... python3 -I -m py_compile` ล็อกสิทธิ์และตรวจว่า `runner.py` ไม่มี syntax error ถ้ามีจะ build ล้ม
6. ตั้ง `ENV`, `USER 10001:10001`, `WORKDIR /work`, `ENTRYPOINT`, `CMD`

ค่า `ARG` ทุกตัว (`TRIVY_IMAGE`, `BASE_IMAGE`, `RUNNER_VERSION`, `TRIVY_VERSION`) มีค่าเริ่มต้นใน Dockerfile แต่ role `scan-runner-image` ส่งค่าทับทุกครั้ง ถ้าแก้เวอร์ชันต้องแก้ทั้งสองที่ให้ตรงกัน

### 5.2 กลไกร่วมของ `runner.py`
- **Python stdlib อย่างเดียว** ไม่มี supply chain ของ pip
- **state ข้ามขั้น:** ทุกขั้นอ่าน/เขียน `/work/state.json` (`load_state` / `save_state`) โดยเขียนไฟล์ชั่วคราว + `fsync` แล้ว `os.replace` (atomic) container ถูกฆ่ากลางทางก็ไม่ได้ไฟล์ครึ่งๆ
- **`run_step(name, body)`:** ถ้า state มี verdict แล้ว ข้ามขั้นตัวเอง, ถ้า body โยน `Verdict` บันทึก verdict + เหตุผลลง state แล้ว **exit 0** เพื่อให้ `publish` ได้เขียนผลเสมอ
- **`Verdict(verdict, reason, retryable)`** แทนผลที่รายงานได้ ใช้ผ่าน `fail(reason)` (FAIL) และ `error(reason, retryable)` (ERROR)
- **exit non-zero เฉพาะเมื่อ runner พังเอง** (exception ไม่คาดคิด, เขียน termination log ไม่ได้) → Job `Failed` → reconciler retry
- **`run_tool(argv, timeout)`:** เรียก tool ด้วย argv list (ไม่ผ่าน shell), stdin ปิด, env มีแค่ `PATH`, `HOME`, `TMPDIR`, `LANG`
- **ตรวจรูปแบบ input ทุกตัวก่อนใช้** ด้วย regex (`RE_UUID`, `RE_ETAG`, `RE_REGISTRY`, `RE_REPOSITORY`, `RE_TAG`, `RE_DIGEST`, `RE_ARCH`) ค่าผิดรูปแบบได้ `ERROR` ไม่ retry
- ข้อความทุกอันผ่าน `clip()` (ตัดความยาว ลบขึ้นบรรทัดใหม่) และไม่เคย log URL หรือ environment
- `main` ตั้ง `umask 0077` ไฟล์ที่สร้างใน `/work` อ่านได้แค่เจ้าของ

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
| publish | `step_push(state)` | `skopeo copy` เข้า registry แล้วอ่าน digest |
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
| `WORK_DIR`, `DOWNLOAD_URL_FILE`, `TERMINATION_LOG`, `SKOPEO_POLICY` | ทุกขั้น | ตาม path ในตารางโครงไฟล์ | ใช้แก้ path ตอนทดสอบนอก Pod |

#### ไฟล์ใน `/work` ระหว่างทาง
| ไฟล์ | สร้างโดย | ใช้โดย |
|---|---|---|
| `image.tar` | fetch | validate, scan, publish |
| `state.json` | ทุกขั้น | ทุกขั้น |
| `tmp/` | `main` | Trivy, skopeo (ผ่าน `TMPDIR`) |
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
ถ้าขั้นไหนได้ verdict ระหว่างทาง ขั้นนั้นจะเป็น `{"ok": false}` มี `verdict`, `retryable`, `reasons` และขั้นที่เหลือจะไม่ถูกบันทึก (ข้ามตัวเอง)

#### ตัวอย่างผลที่ `publish` เขียนลง termination log
PASS (จาก `vlab/print-test2077:latest` ที่ทดสอบจริง):
```json
{"imageId":"b81aa248-7937-...","etag":"d313c7e5c05841c025b76c1f6394a2dc","verdict":"PASS","retryable":false,
 "reasons":[],"warnings":["image runs as root"],"digest":"sha256:5b5427e6...b800",
 "summary":{"runnerVersion":"1.0.0","trivyVersion":"0.76.1","failSeverity":"CRITICAL",
            "counts":{"CRITICAL":0,"HIGH":0,"MEDIUM":0,"LOW":0,"UNKNOWN":0},"secrets":0,
            "image":{"os":"linux","architecture":"amd64","user":"","exposedPorts":[]},
            "archiveSha256":"8087a2d2...bbc5"}}
```
ERROR (แถว seed ที่ไม่มีไฟล์บน R2):
```json
{"imageId":"f247a5ca-71cd-...","etag":"d41d8cd98f00b204e9800998ecf8427e","verdict":"ERROR","retryable":true,
 "reasons":["download failed: HTTP 404"],"warnings":[],"digest":null,"summary":{"runnerVersion":"1.0.0"}}
```
`summary` เก็บเฉพาะค่าที่ไม่ว่าง ERROR ตั้งแต่ขั้น fetch จึงเหลือแค่ `runnerVersion`
reconciler ใช้ `etag`, `verdict`, `retryable`, `digest`, `reasons` ตัดสิน ส่วน `summary` (บวก verdict / reasons / warnings) ถูกเก็บลง DB ผ่าน `_summary_from` ให้หน้าเว็บแสดง

#### ผลที่เป็นไปได้ของแต่ละขั้น
| ขั้น | เหตุ | verdict | retryable |
|---|---|---|---|
| fetch | `ETAG` / `EXPECTED_SIZE` ไม่มีหรือผิดรูปแบบ | ERROR | ไม่ |
| fetch | ขนาดเกิน `MAX_ARCHIVE_BYTES` | FAIL | |
| fetch | ไม่มีไฟล์ Secret | ERROR | ใช่ |
| fetch | URL ไม่ใช่ https | ERROR | ไม่ |
| fetch | HTTP error, เครือข่าย, ขนาดไม่ตรง, md5 ไม่ตรง (ลองครบ 3 ครั้ง) | ERROR | ใช่ |
| validate | ไม่ใช่ tar, tar เสีย, path อันตราย, device, entry เยอะเกิน, ไม่ใช่ image archive | FAIL | |
| validate | skopeo อ่านไม่ได้ / หลาย image / config ไม่ใช่ JSON | FAIL | |
| validate | ไม่ใช่ `linux/amd64` | FAIL | |
| validate | `ALLOWED_ARCH` ผิดรูปแบบ | ERROR | ไม่ |
| scan | `POLICY_FAIL_SEVERITY` ผิด | ERROR | ไม่ |
| scan | Trivy ล้ม / report อ่านไม่ได้ | ERROR | ใช่ |
| scan | ไม่ผ่าน policy | FAIL | |
| publish | `REGISTRY` / `REPOSITORY` / `TAG` ผิดรูปแบบ | ERROR | ไม่ |
| publish | ไม่มี transport ใน state | ERROR | ใช่ |
| publish | push ไม่ได้, ไม่มี digest, digest ผิดรูปแบบ | ERROR | ใช่ |
| ทุกขั้น | exception ที่ไม่คาด, `state.json` เสีย, เขียน termination log ไม่ได้ | (runner exit ≠ 0 → Job Failed) | reconciler retry |

### 5.3 ลำดับใน Pod
```
fetch (init) ─► validate (init) ─► scan (init) ─► publish (main) ─► /dev/termination-log
      └──────────────── /work: image.tar, state.json, trivy.json, digest ────────────────┘
```

#### `fetch` (`step_fetch`): container เดียวที่เห็นความลับ
1. ตรวจ `ETAG` (md5 32 ตัว หรือรูปแบบ multipart `xxx-N`) และ `EXPECTED_SIZE`
2. ถ้าขนาดเกิน `MAX_ARCHIVE_BYTES` (ค่าเริ่มต้น 20 GiB) → `FAIL`
3. อ่าน URL จาก `/secrets/fetch/download_url` ต้องขึ้นต้นด้วย `https://` (ไม่มีไฟล์ → `ERROR` retryable)
4. `_download_once` โหลดด้วย `urllib`
   - ไม่ใช้ proxy จาก env (`ProxyHandler({})`)
   - redirect ได้เฉพาะไป https (`_HttpsOnlyRedirect`) กันถูกเบนไป http หรือ `file://`
   - ถ้า `Content-Length` ไม่ตรงกับที่คาด หยุดทันที
   - ระหว่างโหลด ถ้าเกิน `EXPECTED_SIZE` หยุดทันที กันดิสก์เต็ม
   - คำนวณ md5 และ sha256 ไปพร้อมกัน แล้ว `fsync`
5. ตรวจหลังโหลด: ขนาดต้องตรง และ md5 ต้องเท่ากับ ETag (ถ้าเป็น multipart ตรวจได้แค่ขนาด) ข้อนี้รับประกันว่า **ไฟล์ที่สแกนคือไฟล์ที่ webhook บันทึกไว้**
6. ลองได้ 3 ครั้ง (หน่วง 2, 4 วินาที) ยกเว้น HTTP 401/403/404 ที่หยุดลองทันที
7. ล้มทั้งหมด → ลบไฟล์ครึ่งๆ ทิ้ง → `ERROR retryable` (ข้อความมีแค่ `HTTP <code>` ไม่มี URL)
8. สำเร็จบันทึก `bytes` และ `sha256` (ไปโผล่ใน summary เป็น `archiveSha256`)

#### `validate` (`step_validate`)
1. `detect_archive_format()` อ่าน header ของ tar โดย **ไม่แตกไฟล์**
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

| เจออะไร | ผล |
|---|---|
| ช่องโหว่ CRITICAL ที่มีเวอร์ชันแก้ | FAIL |
| ช่องโหว่ CRITICAL ที่ยังไม่มีเวอร์ชันแก้ | warning |
| secret HIGH/CRITICAL (private key, cloud token) | FAIL |
| ช่องโหว่ HIGH, secret ระดับต่ำ, รันเป็น root, port ไม่ตรง | warning |

#### `publish` (`cmd_publish` + `step_push`)
1. ถ้ายังไม่มี verdict (ทุกขั้นผ่าน) → `step_push`
   - ตรวจ `REGISTRY`, `REPOSITORY`, `TAG` และ transport ที่ `validate` บันทึกไว้
   - `skopeo --policy ... copy --retry-times 3 --dest-tls-verify=false --digestfile /work/digest <transport>:/work/image.tar docker://REGISTRY/REPOSITORY:TAG`
   - digest ต้องเป็น `sha256:<64 hex>`
   - push ไม่ได้หรือ digest ผิด → `ERROR retryable`
   - สำเร็จ → verdict `PASS`
   - push ทับ tag เดิมได้ เพราะ `(repository, tag)` ใน DB เป็น unique tag นี้จึงเป็นของแถวนี้แถวเดียว
2. `build_result(state)` รวมผล: `imageId`, `etag`, `verdict`, `retryable` (เฉพาะ ERROR), `reasons` (≤5), `warnings` (≤8), `digest` (เฉพาะ PASS), `summary` (เวอร์ชัน runner/Trivy, severity, counts, top findings, image info, `archiveSha256`)
3. `encode_result` ตัดส่วนที่ไม่จำเป็นทีละชั้นจนไม่เกิน 3,500 ไบต์ (K8s ตัดที่ 4,096) ลำดับการตัด: `secretTop` → ลด `top` เหลือ 2 → ลบ `top` → ย่อ warnings → ย่อ reasons → ลบ `image` ส่วนที่ reconciler ต้องใช้ (`etag`, `verdict`, `digest`) ไม่ถูกตัด
4. เขียน JSON ลง `/dev/termination-log` ถ้าเขียนไม่ได้ runner พัง (exit non-zero) → reconciler retry

#### `version`
พิมพ์เวอร์ชัน runner, Python, Trivy, skopeo เป็น JSON ใช้ตรวจ image หลัง build
```json
{"runner": "1.0.0", "python": "3.12.x", "trivy": "0.76.1", "skopeo": "1.x.x"}
```

#### ระยะเวลาจริงที่วัดได้ (tar ขนาด 3.8 MB บน cluster ของแลป)
| ช่วง | สถานะ Pod | ใช้เวลา | หมายเหตุ |
|---|---|---|---|
| ครั้งแรกบน node | `Init:0/3` | ~2.5 นาที | pull image `vlab/scan-runner` ครั้งแรก รอบต่อไปมีในเครื่องแล้ว |
| fetch + validate | `Init:0/3` → `Init:2/3` | 2-5 วินาที | ไฟล์ใหญ่ขึ้นเวลาขึ้นตามความเร็วโหลดจาก R2 |
| scan | `Init:2/3` | ~1.5-2 นาที | ส่วนใหญ่คือโหลด Trivy DB ไม่ใช่การสแกน |
| publish | `Running` | ~6-10 วินาที | push เข้า camp registry |
| ERROR ที่ fetch (404) | ทุกขั้นข้าม | ~5 วินาที | ขั้นหลังเห็น verdict แล้วข้ามตัวเอง |

#### debug ทีละขั้น
แต่ละ container log ลง stderr ในรูป `[vlab-scan] <ขั้น>: ok` หรือ `[vlab-scan] <ขั้น>: FAIL - <เหตุผล>` และขั้นที่ข้ามจะเขียน `skipped (verdict already ...)`
```bash
k3s kubectl -n vlab-scan logs <pod> -c fetch
k3s kubectl -n vlab-scan logs <pod> -c validate
k3s kubectl -n vlab-scan logs <pod> -c scan
k3s kubectl -n vlab-scan logs <pod> -c publish
# ผล JSON ที่ reconciler จะอ่าน
k3s kubectl -n vlab-scan get pod <pod> -o jsonpath='{.status.containerStatuses[?(@.name=="publish")].state.terminated.message}'
```
ต้องดูก่อน reconciler ลบ Job (ภายในประมาณหนึ่งรอบ 15 วินาทีหลังจบ) ถ้าดูไม่ทัน ผลยังอยู่ใน DB ที่ `scan_summary`

ทดสอบ `validate` / `scan` นอก Pod ได้ด้วย docker โดย mount โฟลเดอร์ที่มี `image.tar` เป็น `/work` (ข้าม `fetch` ซึ่งต้องมี URL จริง) และใส่ข้อจำกัดเดียวกับใน Pod:
```bash
mkdir work && cp image.tar work/ && sudo chown -R 10001:10001 work
docker run --rm --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$PWD/work:/work" localhost:5001/vlab/scan-runner:1.0.0 validate
docker run --rm --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$PWD/work:/work" localhost:5001/vlab/scan-runner:1.0.0 scan
cat work/state.json
```
ขั้นตอนนี้เขียนตามโค้ด ยังไม่ได้ลองรันจริง

### 5.4 Namespace `vlab-scan` (`k8s/scan-namespace.yaml`)
- Pod Security `restricted` (K8s บังคับเอง)
- `PriorityClass vlab-scan`: ค่า -100, `preemptionPolicy: Never` ต่ำกว่า lab ของนักศึกษาและไม่เบียดใคร
- `ResourceQuota`: 6 pods, requests 4 CPU / 6Gi, limits 8 CPU / 12Gi
- NetworkPolicy: ขาเข้าปิดทั้งหมด, ขาออกได้แค่ DNS (`kube-dns`), camp registry `REGISTRY_IP/32:5001` และอินเทอร์เน็ตพอร์ต 443 โดยตัดช่วงภายในทั้งหมด (`10/8`, `172.16/12`, `192.168/16`, `100.64/10`, `169.254/16`, `127/8`) Pod จึงแตะ kube API, node อื่น, tailnet และ backend ไม่ได้
- role `k3s-server` apply ไฟล์นี้โดยแทน `REGISTRY_IP` ด้วย IP ของ registry ใน inventory

---

## 6. Ansible บนเครื่อง Registry

play `Provision Virtual-Lab registry` ใน `site.yml` รัน role ตามลำดับ
```yaml
- { role: common,            tags: ['common'] }
- { role: registry,          tags: ['registry'] }
- { role: scan-runner-image, tags: ['scan-runner'] }   # ต้องรันหลัง registry (ใช้ docker + camp-registry)
- { role: ecr-sync,          tags: ['ecr-sync'] }
```

### 6.1 `registry` (มีอยู่เดิม)
ติดตั้ง Docker แล้วรัน container `camp-registry` (`registry:2`) ที่พอร์ต 5001 เก็บข้อมูลที่ `/srv/camp-registry` เปิดการลบ (`REGISTRY_STORAGE_DELETE_ENABLED`) และ **ไม่มี auth** (ดูข้อ 8)

### 6.2 `scan-runner-image`: build และ push scanner image
```bash
ansible-playbook -i inventory.yml site.yml -K --tags scan-runner --limit rn
```
1. **ตรวจ input:** image ทุกตัวต้อง pin ด้วย digest, เวอร์ชัน Trivy ต้องตรงกับ tag ใน digest และไม่อยู่ใน `scan_runner_blocked_trivy_versions` (0.69.4-0.69.6 ที่ถูกวางโค้ดร้าย), เวอร์ชัน runner ต้องเป็น semver
2. **cosign verify** image ของ Trivy ด้วย cosign ที่ pin ด้วย digest รันใน container `--read-only --cap-drop=ALL` ต้องถูกเซ็นแบบ keyless โดย `aquasecurity/trivy/.github/workflows/reusable-release.yaml@refs/tags/v<version>` ผ่าน OIDC ของ GitHub Actions เท่านั้น ไม่ผ่าน = หยุดทั้ง play
3. copy build context (`Dockerfile`, `.dockerignore`, `runner.py`, `policy.json`) ไป `/opt/vlab-scan-runner-build` (root, 0750)
4. คำนวณ **build hash** = sha256 ของ checksum ทุกไฟล์ + digest ของ Trivy และ base + เวอร์ชัน
5. `docker build --pull` ส่ง digest และเวอร์ชันเป็น build-arg และติด label `vlab.scan-runner.build-hash`
6. ตรวจ image: user ต้องเป็น `10001:10001`, smoke test `version` ภายใต้ `--read-only --cap-drop=ALL --network=none` ต้องได้ Trivy ตรงเวอร์ชันที่ pin
7. **tag เป็น immutable:** อ่าน manifest และ config ของ `vlab/scan-runner:<version>` ใน registry
   - ไม่มี → push
   - มีและ build hash เดิม → ไม่ push (ไม่มีอะไรเปลี่ยน)
   - มีแต่ hash ต่าง → **fail** ให้เพิ่มเวอร์ชันแทน (Job ที่รันอยู่อาจใช้ tag นี้) ยกเว้นสั่ง `-e scan_runner_force_push=true`
8. push ผ่าน `localhost:5001` (docker เชื่อ HTTP บน localhost โดยไม่ต้องตั้ง `insecure-registries`)
9. แสดงค่า `SCAN_RUNNER_IMAGE=<registry IP>:5001/vlab/scan-runner@sha256:...` ให้ใส่ใน backend ถ้าต้องการอ้างด้วย digest

### 6.3 `ecr-sync`: sync camp registry ขึ้น ECR
```bash
ansible-playbook -i inventory.yml site.yml -K --tags ecr-sync --limit rn
```

**role ทำอะไร** (เมื่อ `ecr_sync_enabled: true`)
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

**Timer ใช้ทำอะไร** (`vlab-ecr-sync.timer`)
เป็นตัวสั่งให้ `vlab-ecr-sync.service` (oneshot) รันซ้ำเป็นรอบๆ แทนการรันเป็น daemon ค้างไว้
| ค่า | ความหมาย |
|---|---|
| `OnBootSec=2min` | รอบแรกหลังเปิดเครื่อง 2 นาที |
| `OnActiveSec=30s` | รอบแรกหลัง timer ถูก start 30 วินาที |
| `OnUnitInactiveSec={{ ecr_sync_interval }}` (2min) | รอบถัดไปนับจากตอนรอบก่อน **จบ** รอบที่ copy นานจึงไม่ซ้อนกัน |
| `RandomizedDelaySec=15s` | สุ่มหน่วงเพิ่ม 0-15 วินาที |

ตัวนับเป็นนาฬิกาแบบ monotonic ช่วงที่เครื่องพักจะไม่นับ หลังตื่นอาจต้องสั่ง `sudo systemctl start vlab-ecr-sync.service` เอง

**Service** (`vlab-ecr-sync.service`)
- รันเป็น user `vlab-ecr-sync`, อ่าน `config.env` เป็น env
- key ส่งผ่าน `LoadCredential=aws.env:...` systemd copy เข้า `$CREDENTIALS_DIRECTORY` ให้ service นี้ตัวเดียว ไม่ผ่าน env หรือ argv
- `RuntimeDirectory` (0700) ใช้วาง authfile ชั่วคราว, `CacheDirectory` ใช้พัก blob ของ skopeo (ไม่ใช้ `/run` ที่เป็น RAM)
- hardening: `NoNewPrivileges`, ไม่มี capability, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `PrivateDevices`, ปิด namespace/realtime/SUID, จำกัด address family และ syscall (`@system-service`), `UMask=0077`
- `TimeoutStartSec=6h`

**Push ขึ้น ECR ยังไง** (`ecr_sync.py` ต่อหนึ่งรอบ)
1. อ่าน config: `ECR_REGISTRY`, `SOURCE_REGISTRY` (`localhost:5001`), `INCLUDE_REGEX` (`^vlab/`), `EXCLUDE_REGEX` (`^vlab/scan-runner$`), `MAX_COPIES` (20), `COPY_TIMEOUT` (3600) และ key จาก `$CREDENTIALS_DIRECTORY/aws.env`
2. อ่านรายการ repo จาก camp registry (`/v2/_catalog` รองรับ pagination) คัดตาม include/exclude และกติกาชื่อของ ECR
3. ต่อ repo: `describe_images` บน ECR ได้ map tag → digest (ยังไม่มี repo = `None`)
4. ต่อ tag: อ่าน digest ต้นทางด้วย `HEAD /v2/<repo>/manifests/<tag>`
   - digest ตรงกับ ECR → ข้าม
   - ECR มี tag นี้แต่ digest ต่าง → **ไม่เขียนทับ** log `conflict` และนับเป็น failure (repo บน ECR เป็น IMMUTABLE)
   - ECR ไม่มี → เข้ารายการที่ต้อง copy
5. ไม่มีอะไรต้อง copy → log `up to date` จบ (ไม่ขอ token ECR เลย)
6. ขอ token ECR (`get_authorization_token`) เขียนเป็น authfile 0600 ใน `$RUNTIME_DIRECTORY`
7. ต่อรายการ (ไม่เกิน `MAX_COPIES` ที่เหลือไปรอบหน้า)
   - `ensure_repository` สร้าง repo บน ECR ถ้ายังไม่มี: `IMMUTABLE`, scan on push, เข้ารหัส AES256, tag `managed-by=vlab-ecr-sync`
   - `skopeo copy --all --src-tls-verify=false --dest-authfile <authfile> docker://localhost:5001/<repo>:<tag> docker://<ECR>/<repo>:<tag>` (ผ่าน argv list ไม่ผ่าน shell)
   - อ่าน digest บน ECR อีกครั้ง ต้องตรงกับต้นทาง ไม่งั้น `digest mismatch`
8. ลบ authfile ทิ้งเสมอ (`finally`) แล้ว log `copied N, failed N, deferred N`
9. exit 1 ถ้ามี failure → service เป็น failed (เห็นใน `journalctl`) แล้วรอบหน้าลองใหม่

ไม่ลบอะไรบน ECR เลย image ที่ถูกลบจาก camp registry ยังอยู่บน ECR ให้ lifecycle policy ของ ECR จัดการ

**IAM:** user ของงานนี้ควรแยกจาก SkyPilot มีสิทธิ์ตาม `ansible/roles/ecr-sync/files/iam-policy.json` คือ `ecr:GetAuthorizationToken` และสิทธิ์ push (`CreateRepository`, `TagResource`, `DescribeImages`, `BatchCheckLayerAvailability`, `BatchGetImage`, `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload`, `PutImage`) จำกัดที่ `repository/vlab/*`

**เช็คบนเครื่อง registry**
```bash
systemctl list-timers vlab-ecr-sync.timer          # รอบถัดไป
sudo journalctl -u vlab-ecr-sync.service -n 20 --no-pager
sudo systemctl start vlab-ecr-sync.service         # sync ทันที
curl http://localhost:5001/v2/_catalog             # ของใน camp registry
```

---

## 7. คู่มือดูสถานะ

```bash
# บน master: Pod ของการสแกนแบบ real-time
k3s kubectl -n vlab-scan get pods -w
# log ของแต่ละขั้น (ต้องดูก่อน reconciler ลบ Job)
k3s kubectl -n vlab-scan logs <pod> -c fetch        # validate / scan / publish
# Pod ค้าง: ดู events ก่อนถูกลบ
k3s kubectl -n vlab-scan describe pod <pod>
# ก่อนรีเซ็ต DB: ล้าง Job ค้าง (กัน image กำพร้าถูก push เข้า registry หลังรีเซ็ต)
k3s kubectl -n vlab-scan delete jobs -l vlab/scan=true
```

| สถานะ Pod | ขั้น |
|---|---|
| `Init:0/3` | `fetch` (หรือยังรอ Secret) |
| `Init:1/3` | `validate` |
| `Init:2/3` | `scan` (นานสุด เพราะโหลด Trivy DB) |
| `PodInitializing` / `Running` | `publish` |
| `Completed` | จบแล้ว ผลจริงดูใน DB (`scan_status`, `scan_summary`) |

ชื่อ Pod `scan-<id 12>-<etag 8>-a<ครั้งที่>-xxxxx` ถ้าเห็น `a2` แปลว่ารอบแรกถูก retry

---

## 8. รีวิวความพร้อมและข้อแนะนำ

ตัว image ดีพอสำหรับใช้งานจริงในระดับห้องแลปแล้ว แต่ระบบรอบๆ ยังมีช่องที่ทำให้การสแกนถูกข้ามได้ ซึ่งสำคัญกว่าตัว image เอง รีวิวนี้มาจากการอ่าน `Dockerfile`, `runner.py`, `policy.json` และ role `registry` ยังไม่ได้ทดสอบโจมตีจริง

### ที่ทำได้ดีแล้ว
- **Supply chain:** pin base และ Trivy ด้วย digest, ตรวจ cosign ก่อน build, บล็อก Trivy 0.69.4-0.69.6, ไม่มี pip dependency
- **Hardening:** non-root, read-only rootfs, ถอด setuid และลบ `apk`, `python3 -I`, เรียก tool แบบไม่ผ่าน shell และใช้ env น้อยที่สุด
- **แยก secret:** URL อยู่ใน `fetch` ตัวเดียวและไม่ถูกเขียนลง log, skopeo `default: reject`
- **ตรวจไฟล์:** md5 = ETag, หยุดโหลดทันทีถ้าใหญ่เกิน, ตรวจ path traversal / device / จำนวน entry โดยไม่แตกไฟล์
- **policy ตัดสินใน Python:** อ่านและตรวจสอบได้ ไม่ฝากไว้กับ flag ของ Trivy

### ช่องโหว่ เรียงตามความสำคัญ

**1. camp registry ไม่มี auth ใครก็ push ข้ามการสแกนได้ (สำคัญที่สุด)**
role `registry` ไม่มี `htpasswd` หรือการจำกัดสิทธิ์ใดๆ และ Tailscale ACL เปิดให้ `tag:vlab-worker` เข้า `:5001` ได้ ใครที่อยู่บนเครื่องแลปหรือในทีมสามารถ `docker push <registry>:5001/vlab/อะไรก็ได้` ได้ตรงๆ จากนั้น `ecr-sync` จะ copy ขึ้น ECR ให้ด้วย ข้อนี้ขัดกับเป้าหมายใน `SCAN_RUNNER_IMAGE.md` ที่ว่า "ต้องไม่มีทางทำให้ image ที่ไม่ผ่านเข้าไปอยู่ใน registry"
แก้ด้วยการเปิด auth ของ registry ให้ push ได้แค่ scan Job (credential แยก) และ role build image ส่วน pull ยังเปิดได้ หรือใช้ ACL แยก push/pull ยังไม่ได้ตรวจว่า Pod ของนักศึกษาออกไป `:5001` ได้ไหม (ต้องอ่าน `lab-isolation-networkpolicy.yaml`)

**2. ไม่มี unit test ของ `runner.py`**
ไม่มี test ของ `evaluate_report` หรือ `detect_archive_format` ผลใน `SCAN_RUNNER_IMAGE.md` ข้อ 6 เป็นการทดสอบด้วยมือครั้งเดียว ทั้งที่ policy เป็นหัวใจของ gate นี้ และ `evaluate_report` ถูกแยกเป็นฟังก์ชันล้วนไว้ให้ test อยู่แล้ว ควรเพิ่ม pytest ด้วย report JSON ตัวอย่าง (fixable/unfixed CRITICAL, secret HIGH/LOW, report ว่าง) และ tar ประหลาด

**3. ขนาดไฟล์สามจุดไม่ตรงกัน**
`MAX_ARCHIVE_BYTES` = 20 GiB, `emptyDir` = 15 Gi ซึ่งต้องจุทั้ง tar และงานของ Trivy ส่วน backend จำกัด `LAB_IMAGE_MAX_ARCHIVE_BYTES` (single PUT) ต่ำกว่านั้นอีก ถ้าไฟล์ใหญ่ใกล้ 15 Gi Pod จะถูก evict แล้ว retry จนเป็น `ERROR` โดยข้อความไม่บอกสาเหตุจริง ควรให้ runner ใช้ limit เดียวกับ backend และตั้ง `sizeLimit` ประมาณ 2 เท่าของ limit นั้น

**4. 404 ยังถูก retry**
`fetch` หยุดลองซ้ำเมื่อเจอ 401/403/404 แต่ยังส่ง `retryable=True` reconciler จึงเปิด Job ใหม่ (เห็นได้จากแถว seed ที่โดนสองรอบ) 401/403 ควร retry ต่อ เพราะรอบใหม่ได้ URL ใหม่ แต่ 404 แปลว่าไฟล์หายไปแล้ว ควรเป็น `retryable=False` แก้บรรทัดเดียว

**5. โหลด Trivy DB ใหม่ทุก Job**
ข้อดีคือ cache ไม่ถูกวางยาข้าม Pod แต่ทุกการสแกนต้องพึ่ง `mirror.gcr.io`/ghcr ถ้าโดน rate limit หรือเน็ตล่ม จะ `ERROR` ทุกตัว และ DB ไม่ได้ตรวจลายเซ็น ทางที่ดีกว่าคือให้ timer บนเครื่อง registry ดึง DB มาเก็บใน camp registry วันละครั้ง แล้วให้ Job ใช้ `--db-repository` ชี้เข้าข้างใน จะได้ทั้งความเร็วและควบคุมได้

**6. symlink / hardlink ใน tar ชั้นนอกไม่ถูกตรวจ**
`detect_archive_format` ตรวจ path ของชื่อไฟล์ แต่ไม่ได้ตรวจปลายทางของ symlink หรือ hardlink ความเสี่ยงต่ำ เพราะ skopeo ไม่ได้แตกไฟล์ลงดิสก์และ rootfs เป็น read-only แต่ปิดได้ด้วยโค้ดไม่กี่บรรทัด (ปฏิเสธ `issym()`/`islnk()` ที่ปลายทางเป็น absolute หรือมี `..`)

### เรื่อง policy (เป็นการตัดสินใจ ไม่ใช่บั๊ก)
- FAIL เฉพาะ CRITICAL ที่มีเวอร์ชันแก้แล้ว ส่วน CRITICAL ที่ยังไม่มี fix และ HIGH ทั้งหมดผ่านเป็น warning ถือว่าหลวมแต่เหมาะกับ lab image ที่มักใช้ base ใหญ่
- Trivy ไม่ได้หา malware หรือ backdoor ผล PASS แปลว่า "ไม่พบปัญหาที่รู้จัก" ไม่ใช่ "ปลอดภัย" ถ้าต้องการชั้นนี้ ต้องเพิ่ม ClamAV/YARA ซึ่งทำให้ image ใหญ่ขึ้นมาก

### ข้อสังเกตเพิ่มจากการรันบน cluster จริง
- **Secret หายถ้าระบบล้มกลางทาง:** ถ้า backend ถูกหยุดระหว่าง "สร้าง Job แล้ว" กับ "สร้าง Secret" จะไม่มีใครสร้าง Secret ให้ซ้ำ Pod ค้างที่ `Init:0/3` จนถึง deadline แล้วเสีย attempt ไปหนึ่งครั้ง ควรให้ reconciler ตรวจว่า Job ที่ `ACTIVE` มี Secret หรือยัง ถ้าไม่มีก็เรียก `launch_scan_job` ซ้ำ (ทำซ้ำได้อยู่แล้ว)
- **โควตา retry น้อย:** `SCAN_MAX_ATTEMPTS = 2` รอบที่ล้มเพราะ infra (เครื่องพัก, Job หาย) ก็นับด้วย ถ้าเจอปัญหาชั่วคราวซ้ำ image ของอาจารย์จะเป็น `ERROR` และถูก reject ใน 7 วัน ควรเพิ่มเป็น 3 หรือไม่นับรอบที่ล้มเพราะ infra
- **VM พักเครื่อง:** Job ค้าง, timer ของ ECR sync ไม่รันหลังตื่น และนาฬิกาเพี้ยน มาจากสาเหตุเดียวกัน ควรตั้งไม่ให้เครื่อง master / worker / registry พัก
- **รีเซ็ต DB ขณะมี Job:** Job ของแถวเดิมอาจไปถึง `publish` แล้ว push image ที่ไม่มีแถวใน DB และถูก sync ขึ้น ECR (ซึ่งเป็น IMMUTABLE) ให้ลบ Job ก่อนรีเซ็ตทุกครั้ง (คำสั่งในข้อ 7)

### ลำดับที่แนะนำ
1. ข้อ 1 (auth ของ registry) ไม่งั้นการสแกนเป็นแค่ด่านที่เดินอ้อมได้ กระทบ role `registry`, `registries.yaml` ของ k3s, `build-images.yml` และ scan Job พร้อมกัน ควรวางแผนก่อนลงมือ
2. ข้อ 2 (test ของ `runner.py`) และข้อ 4 (404) ทำเสร็จได้ในครั้งเดียว พร้อมกับเรื่อง Secret หายและโควตา retry
3. ข้อ 3, 5, 6 ทำทีหลังได้
