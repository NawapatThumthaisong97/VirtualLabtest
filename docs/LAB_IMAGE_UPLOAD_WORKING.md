# Phase 1: ฟอร์มอัปโหลดและการอัปโหลดเบื้องหลัง

> ส่วนหนึ่งของ [LAB_IMAGE_UPLOAD_PLAN.md](LAB_IMAGE_UPLOAD_PLAN.md) (ข้อ 3) · branch `feature/lab-image-upload-p1`
> เอกสารนี้บันทึกทุกอย่างที่แก้ใน Phase 1 พร้อมเหตุผลของแต่ละจุด เขียนไว้ให้อ่านทบทวนทีหลังได้โดยไม่ต้องไล่ diff เอง
> กล่อง **💡** คือหลักคิดที่ใช้กับงานอื่นได้ กล่อง **⚠️** คือสิ่งที่ยังไม่เสร็จหรือต้องระวัง

## สารบัญ

| ข้อ | เรื่อง |
|---|---|
| 1 | [ปัญหาก่อนแก้](#1-ปัญหาก่อนแก้) |
| 2 | [ผลหลังแก้ (มุมมองอาจารย์)](#2-ผลหลังแก้-มุมมองอาจารย์) |
| 3 | [ไฟล์ที่แก้ทั้งหมด](#3-ไฟล์ที่แก้ทั้งหมด) |
| 4 | [Backend: ให้ entrypoint ว่างได้](#4-backend-ให้-entrypoint-ว่างได้) |
| 5 | [Frontend: ฟอร์มและส่วน Advanced](#5-frontend-ฟอร์มและส่วน-advanced) |
| 6 | [Frontend: อัปโหลดเบื้องหลัง](#6-frontend-อัปโหลดเบื้องหลัง) |
| 7 | [Frontend: หน้า Lab images และ Lab Builder](#7-frontend-หน้า-lab-images-และ-lab-builder) |
| 8 | [เทส](#8-เทส) |
| 9 | [ทดลองด้วยมือ (ไม่ต้องเปิดเครื่องแลป)](#9-ทดลองด้วยมือ-ไม่ต้องเปิดเครื่องแลป) |
| 10 | [Deploy](#10-deploy) |
| 11 | [ข้อจำกัดที่ยังเหลือ](#11-ข้อจำกัดที่ยังเหลือ) |
| 12 | [บทเรียนระหว่างทำ](#12-บทเรียนระหว่างทำ) |
| 13 | [คำศัพท์และแนวคิด](#13-คำศัพท์และแนวคิด) |
| 14 | [คำถามทบทวน](#14-คำถามทบทวน) |

---

## 1. ปัญหาก่อนแก้

### 1.1 ฟอร์มบังคับกรอก และใส่ค่าเดาไว้ให้
| จุด | โค้ดเดิม | ผล |
|---|---|---|
| ฟอร์ม | Entrypoint เป็น `required` ค่าเริ่มต้น `/bin/bash /run.sh`, ports `8080, 5173, 8443`, workdir `/workspace` (Lab Builder) | อาจารย์ต้องรู้ว่า image ตัวเองมี `/run.sh` ไหม ถ้าไม่มี lab เปิดไม่ขึ้น |
| API (`lab_image_schema.py`) | `entrypoint_script: str = Field("/bin/bash /run.sh", min_length=1)` | ต่อให้ client ไม่ส่งมา ก็ยังถูกเติม `/bin/bash /run.sh` |
| DB (`lab_image.py`) | `entrypoint_script` เป็น `NOT NULL` | เก็บค่าว่างไม่ได้ |

ประเด็นสำคัญคือโค้ดฝั่งรัน lab **รองรับ entrypoint ว่างอยู่แล้ว** (ว่าง = ไม่ทับคำสั่งของ image) ทั้ง [warm_pod_service.py](../web-portal/backend/app/services/warm_pod_service.py) และ `_build_aws_task` ใน [session_service.py](../web-portal/backend/app/services/session_service.py) ที่ใช้ไม่ได้เป็นเพราะฟอร์ม, API และ DB ไม่ยอมให้ค่าว่างผ่านเข้ามาเลย

### 1.2 อัปโหลดแล้วต้องค้างอยู่หน้าเดิม
- ไฟล์ .tar วิ่งจาก browser ขึ้น R2 ตรง ๆ ผ่าน **presigned PUT URL** ไม่ได้ผ่าน backend
- โค้ดที่สั่ง PUT อยู่ใน component (`LabImageTab` และ `CreateLabModal`) และสถานะความคืบหน้าก็อยู่ใน `useState` ของ component
- `LabImageTab` ยังมี `useEffect(() => () => abort.current?.abort(), [])` ซึ่งหมายถึง **ถ้า component ถูกถอด (unmount) ให้ยกเลิก PUT**
- ผลคือพอเปลี่ยนหน้า การอัปโหลดหยุดทันที อาจารย์ต้องนั่งรอ ~3 นาทีกับไฟล์ใหญ่

---

## 2. ผลหลังแก้ (มุมมองอาจารย์)

```
กรอก Repository / Tag / ไฟล์ .tar / (Description, CPU, RAM, Lifespan มีค่าเริ่มต้นแล้ว)
  └─ Advanced settings พับไว้ ไม่ต้องเปิดก็ได้
กด Upload image
  └─ "Preparing upload…" ไม่กี่วินาที (ขอ presigned URL)
  └─ ฟอร์มปิด แถวใหม่โผล่ในรายการพร้อม "Uploading 12%"
  └─ ถาดความคืบหน้ามุมซ้ายล่าง ตามไปทุกหน้า
ไปหน้าอื่นในเว็บได้ อัปโหลดเดินต่อ
ปิด / reload แท็บ → browser ถามยืนยันก่อน
อัปเสร็จ → toast "Upload complete" → แถวเปลี่ยนเป็น Queued → Scanning → Ready
ล้ม → toast + ปุ่ม Retry ในถาด (ไม่ต้องกรอกฟอร์มใหม่)
```

---

## 3. ไฟล์ที่แก้ทั้งหมด

| ไฟล์ | สถานะ | แก้อะไร |
|---|---|---|
| [lab_image_schema.py](../web-portal/backend/app/schemas/lab_image_schema.py) | แก้ | entrypoint ว่างได้, `""` → `None`, workdir ต้องเป็น path เต็ม |
| [lab_image.py](../web-portal/backend/app/models/lab_image.py) | แก้ | `entrypoint_script` nullable ไม่มีค่าเริ่มต้น |
| [20261118_01_lab_image_optional_entrypoint.py](../web-portal/backend/migrations/versions/20261118_01_lab_image_optional_entrypoint.py) | ใหม่ | migration `DROP NOT NULL` |
| [test_lab_image_upload.py](../web-portal/backend/tests/lab_image/test_lab_image_upload.py) | แก้ | เทสค่าว่าง / trim / workdir / response เป็น null |
| [test_direct_pod.py](../web-portal/backend/tests/session/test_direct_pod.py) | แก้ | entrypoint `None` → pod ไม่มี `command` |
| [test_task_builder.py](../web-portal/backend/tests/session/test_task_builder.py) | แก้ | entrypoint `None` บน AWS → ไม่ต่อคำสั่งท้าย image |
| [labImage.ts](../web-portal/frontend/src/services/labImage.ts) | แก้ | type: `entrypointScript: string \| null`, field ของ Advanced เป็น optional |
| [labImageUploads.ts](../web-portal/frontend/src/services/labImageUploads.ts) | ใหม่ | store และ logic ของการอัปโหลดเบื้องหลัง |
| [UploadTray.tsx](../web-portal/frontend/src/components/UploadTray.tsx) | ใหม่ | ถาดความคืบหน้า + เตือนก่อนปิดแท็บ |
| [App.tsx](../web-portal/frontend/src/App.tsx) | แก้ | mount `<UploadTray />` นอก router |
| [LabImageForm.tsx](../web-portal/frontend/src/components/instructor/LabImageForm.tsx) | แก้ | เอาค่าเดาออก, ส่วน Advanced พับได้, hint, ส่ง `null` เมื่อว่าง |
| [LabImageTab.tsx](../web-portal/frontend/src/components/instructor/LabImageTab.tsx) | แก้ | ใช้ `startUpload`, แสดง % ในแถว, แสดง "from image" |
| [CreateLabModal.tsx](../web-portal/frontend/src/components/lab-builder/CreateLabModal.tsx) | แก้ | เลิกส่งค่าเดา, ผูก image ก่อนแล้วอัปเบื้องหลัง |
| [labImageUploads.test.ts](../web-portal/frontend/src/__tests__/labImageUploads.test.ts) | ใหม่ | เทส store (8 ข้อ) |
| [LabImageForm.test.tsx](../web-portal/frontend/src/__tests__/LabImageForm.test.tsx) | ใหม่ | เทสฟอร์มและถาด (7 ข้อ) |

**ไม่แตะ:** Ansible, Terraform, K8s manifest, scan-runner, Cloudflare Worker

---

## 4. Backend: ให้ entrypoint ว่างได้

### 4.1 Schema ของ request
```python
entrypoint_script: str | None = Field(None, max_length=255)
workdir: str | None = Field(None, max_length=255)

@field_validator("entrypoint_script", "workdir", mode="before")
@classmethod
def _blank_to_none(cls, value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value

@field_validator("workdir")
@classmethod
def _check_workdir(cls, workdir):
    if workdir is not None and not workdir.startswith("/"):
        raise PydanticCustomError("workdir_not_absolute", "workdir must be an absolute path (start with /)")
    return workdir
```

**ทำไมต้องแปลง `""` เป็น `None`**
ฝั่งรันเช็กแบบ `(entrypoint or "").strip()` จึงรับ `""` ได้อยู่แล้ว แต่ใน DB "ว่าง" ควรมีความหมายเดียว ถ้าปล่อยให้มีทั้ง `NULL` และ `""` โค้ดที่เขียนทีหลังอาจเช็กแค่ `is None` แล้วเผลอส่ง `""` ไปเป็นคำสั่ง ซึ่ง `/bin/sh -c ""` จะจบทันทีและ lab ตาย

**ทำไมใช้ `mode="before"`**
validator แบบ `before` รันก่อน pydantic ตรวจ type และ `max_length` จึง trim ช่องว่างก่อนนับความยาว และค่า `"   "` จะกลายเป็น `None` ก่อนถูกตรวจอะไรต่อ

**ทำไม workdir ต้องขึ้นต้นด้วย `/`**
`docker run -w workspace` ล้มด้วย "the working directory 'workspace' is invalid, it needs to be an absolute path" ตรวจตั้งแต่ตอนอัปโหลดดีกว่าไปเจอตอนนักศึกษาเปิด lab

**ทำไมใช้ `PydanticCustomError` ไม่ใช้ `ValueError`**
คอมเมนต์เดิมในไฟล์อธิบายไว้แล้ว: handler ใน `main.py` ใส่ `exc.errors()` ลง response ตรง ๆ ถ้าเป็น `ValueError` จะติดไปใน `ctx` ซึ่ง serialize เป็น JSON ไม่ได้ แล้วกลายเป็น 500 แทน 400

### 4.2 Schema ของ response
`LabImageResponse.entrypoint_script: str | None` ถ้าไม่แก้จุดนี้ แถวที่เป็น `NULL` จะทำให้ GET รายการ image ล้ม (pydantic ไม่ยอมแปลง `None` เป็น `str`) มีเทส `test_list_returns_null_entrypoint` กันไว้

### 4.3 Model
```python
# NULL = ใช้ ENTRYPOINT / CMD ของ image เอง มีค่า = รันผ่าน /bin/sh -c ทับคำสั่งของ image
entrypoint_script = Column(String(255), nullable=True)
```
เอา `default="/bin/bash /run.sh"` ออกด้วย ไม่งั้นโค้ดที่สร้าง `LabImage(...)` โดยไม่ใส่ field นี้จะได้ค่าเดาเหมือนเดิม

### 4.4 Migration `20261118_01`
```python
def upgrade():
    op.alter_column("lab_images", "entrypoint_script", existing_type=sa.String(255), nullable=True)

def downgrade():
    op.execute(UPDATE lab_images SET entrypoint_script = '/bin/bash /run.sh' WHERE entrypoint_script IS NULL)
    op.alter_column(..., nullable=False)
```
- **upgrade ไม่แปลงข้อมูลเดิม:** image เก่าที่เก็บ `/bin/bash /run.sh` ไว้ถูกอัปโหลดมาโดยรู้ว่าจะรันแบบนั้น จึงให้รันแบบเดิมต่อ
- **downgrade ต้องเติมค่าก่อน:** `SET NOT NULL` จะล้มถ้ามีแถวไหนเป็น `NULL` จึงต้องเติมค่าเดิมให้ก่อน แถวพวกนั้นจะรันไม่เหมือนเดิม (คอมเมนต์ในไฟล์บอกไว้)
- `existing_type` ต้องใส่ เพราะ alembic บาง dialect ต้องรู้ type เดิมตอน `ALTER COLUMN`

> **💡** migration ที่ดีต้องถามสองคำถาม: "ข้อมูลเดิมต้องแปลงไหม" และ "ถอยกลับได้จริงไหม" ข้อสองมักถูกลืม
> จนวันที่ต้อง rollback จริงแล้ว downgrade ล้มกลางทาง

### 4.5 ฝั่งรัน lab เมื่อ entrypoint เป็น `None`
| ที่รัน | โค้ด | ผล |
|---|---|---|
| ห้องแลป (direct pod / warm pod) | `_lab_container`: `if entrypoint: container["command"] = ["/bin/sh","-c",...]` | ไม่มี `command` → K8s รัน ENTRYPOINT / CMD ของ image |
| AWS | `_build_aws_task`: `command = ... if entrypoint else ""` | ไม่ต่อคำสั่งท้าย `docker run <image>` → Docker รัน ENTRYPOINT / CMD ของ image |
| ห้องแลปผ่าน SkyPilot (ทางเก่า `_build_k8s_task`) | `"run": lab_image.entrypoint_script or "/bin/bash /run.sh"` | **ยังเติม `/bin/bash /run.sh`** เพราะ SkyPilot ต้องมี `run` เสมอ ดูข้อ 11 |

ไม่ต้องแก้โค้ดฝั่งรัน แค่เพิ่มเทสยืนยันว่า `None` ทำงานเหมือน `""`

---

## 5. Frontend: ฟอร์มและส่วน Advanced

### 5.1 ค่าเริ่มต้น
```ts
exposedPorts: '',
entrypointScript: '',
workdir: '',
envVars: [],       // เดิมมีแถว IDE_PASSWORD ว่างไว้ให้
```
หลักคือ **ระบบไม่เดาค่าแทนอาจารย์** ค่าเดาที่ผิดแย่กว่าค่าว่าง เพราะค่าว่างยังตกไปใช้ค่าของ image ซึ่งคนสร้าง image ตั้งไว้เอง

### 5.2 ส่วน Advanced พับได้
```tsx
<button aria-expanded={advancedOpen} aria-controls="img-advanced" onClick={toggle}>
  Advanced settings {advancedFilled > 0 && <span>{advancedFilled} set</span>}
</button>
<div id="img-advanced" className={cn('gap-4 md:col-span-2 md:grid-cols-2', advancedOpen ? 'grid' : 'hidden')}>
  ...Entrypoint, Working directory, Exposed ports, Environment variables
</div>
```
- **ซ่อนด้วย class ไม่ใช่ไม่ render:** ถ้าเขียน `{advancedOpen && <div>…</div>}` ช่องจะถูกถอดออกจาก DOM ตอนพับ react-hook-form จะเลิกติดตาม (หรือลบค่าทิ้ง ขึ้นกับ option `shouldUnregister`) ค่าที่อาจารย์กรอกไว้แล้วพับจึงอาจหาย การใช้ class `hidden` ทำให้ช่องยังอยู่ แค่มองไม่เห็น
- **ใช้ `advancedOpen ? 'grid' : 'hidden'` ไม่ใช้ `'grid' + (open ? '' : 'hidden')`:** ทั้ง `grid` และ `hidden` ตั้งค่า `display` ถ้าใส่สอง class พร้อมกัน ตัวไหนชนะขึ้นกับลำดับใน CSS ที่ Tailwind สร้าง ไม่ใช่ลำดับที่เราเขียน
- **ป้าย "2 set":** ช่องที่พับอยู่มองไม่เห็น ถ้าไม่มีป้าย อาจารย์อาจลืมว่าเคยกรอกอะไรทิ้งไว้ ฟังก์ชัน `countAdvancedFilled` แยก export ไว้ให้เทสได้
- **`aria-expanded` / `aria-controls`:** screen reader จะบอกได้ว่าปุ่มนี้เปิด/ปิดส่วนไหน และตอนนี้เปิดอยู่หรือไม่

### 5.3 Error ในส่วนที่พับอยู่
```ts
const onValid = handleSubmit(submit, (formErrors) => {
  if (!file) setFileError('Attach the image .tar file')
  if (ADVANCED_FIELDS.some((field) => formErrors[field])) setAdvancedOpen(true)
})
```
ถ้าอาจารย์กรอก workdir ผิดแล้วพับ Advanced ไว้ กด Upload แล้วจะเหมือนไม่มีอะไรเกิดขึ้น เพราะข้อความ error ถูกซ่อนอยู่ จึงเปิดส่วนนั้นให้เองเมื่อมี error อยู่ข้างใน

### 5.4 Hint ใต้แต่ละช่อง
| ช่อง | placeholder | hint | ทำไม |
|---|---|---|---|
| Entrypoint | Empty = use the image's ENTRYPOINT / CMD | Runs with /bin/sh -c. It must keep running in the foreground… | คำสั่งที่จบเอง (เช่น `npm install` แล้วจบ) ทำให้ container ปิด lab ตาย |
| Working directory | Empty = use the image's WORKDIR | Full path, e.g. /workspace | ตรงกับ validator ฝั่ง backend |
| Exposed ports | Empty = use the image's EXPOSE | …The app must listen on 0.0.0.0, not 127.0.0.1… | app ที่ฟัง 127.0.0.1 รับได้แค่ภายใน container นักศึกษาเข้าไม่ได้ เป็นปัญหาที่เจอบ่อยที่สุด |
| Environment variables | – | …visible to students; never put real passwords here. | env ส่งเข้า container นักศึกษาพิมพ์ `env` ก็เห็น และ scanner FAIL ถ้าเจอ secret ระดับ HIGH |

UI ทั้งเว็บเป็นภาษาอังกฤษ hint จึงเป็นภาษาอังกฤษตาม แต่เนื้อหาตรงกับที่ Pete เสนอใน issue

### 5.5 ค่าที่ส่งไป API
```ts
entrypointScript: values.entrypointScript.trim() || null,
workdir: values.workdir.trim() || null,
exposedPorts: ports,            // [] ถ้าว่าง
envVars: Object.keys(envVars).length ? envVars : null,
```
ส่ง `null` ตรง ๆ แทน `""` แม้ backend จะแปลงให้อยู่แล้ว ฝั่งไหนก็ไม่ควรพึ่งอีกฝั่งในการทำความสะอาดข้อมูล

---

## 6. Frontend: อัปโหลดเบื้องหลัง

### 6.1 ทำไม component เก็บสถานะการอัปโหลดไม่ได้
React Router เปลี่ยนหน้าด้วยการ **ถอด component ของหน้าเดิมออก** (unmount) แล้วใส่ของหน้าใหม่ state ใน `useState` ของหน้าเดิมจะหายไปด้วย โค้ดที่ยังรอ `await` อยู่ก็ยังรันต่อได้ แต่ `setState` ใส่ component ที่ไม่มีแล้วไม่มีผลอะไร และโค้ดเดิมยังสั่ง `abort()` ตอน unmount ด้วย

ทางแก้คือย้ายสถานะไปไว้ที่ที่**อายุยาวกว่าหน้า** มี 2 ทาง:

| ทาง | ข้อดี | ข้อเสีย |
|---|---|---|
| React Context + Provider ห่อ router | เป็นแนวทางของ React เอง | ต้องเพิ่ม Provider, โค้ดนอก React (เช่น callback ของ axios) เรียกยาก |
| **zustand store ระดับโมดูล** (เลือกทางนี้) | โปรเจกต์ใช้อยู่แล้ว (`useToast`), เรียกได้ทั้งใน component และนอก React (`useUploadStore.getState()` / `setState`) ไม่ต้องมี Provider | สถานะเป็น global ต้องระวังตอนเทส (มี `resetUploads()`) |

โมดูล JavaScript ถูกโหลดครั้งเดียวต่อแท็บ ตัวแปรระดับโมดูลจึงอยู่จนกว่าจะปิดหรือ reload แท็บ ไม่ว่าจะเปลี่ยนหน้ากี่ครั้ง

### 6.2 โครงของ `labImageUploads.ts`
```
useUploadStore  (zustand)      ← UI subscribe: ถาด, แถวในรายการ
  uploads: UploadItem[]          { id, courseId, label, fileName, percent, status, error, retryable }

jobs: Map<imageId, Job>        ← ไม่อยู่ใน store
  { file: File, payload, controller: AbortController | null }

startUpload(upload, file, payload)   เริ่ม PUT (เรียกหลัง createUpload สำเร็จ)
retryUpload(id)                      ขอ URL ใหม่ แล้ว PUT ไฟล์เดิม
cancelUpload(id)                     abort
dismissUpload(id)                    เอาออกจากถาด (ห้ามถ้ายังอัปอยู่)
```

**ทำไมแยก `jobs` ออกจาก store**
- `File` กับ `AbortController` ไม่ใช่ข้อมูลธรรมดา (เทียบค่าหรือ copy ไม่ได้) store ควรเก็บแค่สิ่งที่ UI ใช้แสดง
- ถ้า `File` (ขนาดหลาย GB) อยู่ใน store ทุกครั้งที่ % เปลี่ยน zustand จะสร้าง object ใหม่ที่อ้างถึงมัน ถึงจะไม่ได้ copy ไฟล์จริง แต่ก็ทำให้ debug tool พยายามแสดงมัน
- พออัปเสร็จ `jobs.delete(id)` ปล่อยไฟล์ออกจากหน่วยความจำได้ทันที

### 6.3 ลำดับการอัปโหลด
```
LabImageForm ── submit ──► LabImageTab.handleUpload
                             │ 1. labImageService.createUpload(payload)   ← รอในฟอร์ม ("Preparing upload…")
                             │    ล้ม (409 ชื่อซ้ำ, 403) → toast, ฟอร์มยังเปิดให้แก้
                             │ 2. startUpload(upload, file, payload)      ← ไม่ await
                             │ 3. ปิดฟอร์ม, กางแถวของ image นี้, โหลดรายการใหม่
                             ▼
                      runPut (เบื้องหลัง)
                             │ axios PUT ไป R2 พร้อม AbortSignal
                             │ onUploadProgress → patch({ percent }) เฉพาะตอนเลขเปลี่ยน
                             ├─ สำเร็จ → status 'done', toast success, ลบออกจากถาดใน 8 วินาที
                             ├─ abort  → status 'canceled' (ไม่มี toast)
                             └─ ล้ม    → status 'failed' + ข้อความ + retryable, toast error
```

**ทำไมขั้นที่ 1 ยังรอในฟอร์ม** error ของขั้นนี้ (ชื่อซ้ำ, ไม่มีสิทธิ์, ไฟล์ใหญ่เกิน) ต้องแก้ที่ฟอร์ม ถ้าปิดฟอร์มไปก่อน อาจารย์ต้องกรอกใหม่หมด ขั้นนี้ใช้เวลาไม่กี่วินาทีอยู่แล้ว

**ทำไมอัปเดต % เฉพาะตอนเลขเปลี่ยน** axios ยิง event `onUploadProgress` ถี่มาก (หลายร้อยครั้งต่อไฟล์) ถ้าทุกครั้ง `setState` ทุก component ที่ subscribe จะ render ใหม่โดยไม่จำเป็น ปัดเป็นจำนวนเต็มแล้วเทียบกับค่าก่อน ทำให้ render สูงสุดแค่ ~100 ครั้งต่อไฟล์

### 6.4 ข้อความเมื่อล้ม
| HTTP จาก R2 | ความหมาย | retry ได้ไหม |
|---|---|---|
| 412 | URL ถูกเซ็นด้วย `If-None-Match: *` และมีไฟล์ของ image นี้อยู่แล้ว | ไม่ (ต้องใช้ tag ใหม่) |
| 403 | presigned URL หมดอายุ (`R2_PRESIGN_EXPIRES_SECONDS`) | ได้ (retry จะขอ URL ใหม่) |
| อื่น ๆ / ไม่มี response | เน็ตหลุด | ได้ |

### 6.5 Retry
```ts
upload = await labImageService.createUpload(job.payload)   // ขอ URL ใหม่ด้วย payload เดิม
await runPut(id, upload)                                    // PUT ไฟล์เดิมที่ยังอยู่ใน jobs
```
ทำได้เพราะ backend มี `_find_reusable_draft`: ขอ presign ซ้ำด้วย `repository:tag` เดิมจากคนเดิมที่ยังไม่มีไฟล์ จะได้**แถว draft เดิม** (imageId เดิม) กลับมา ไม่ใช่ 409 ส่วน `CreateLabModal` ผูก imageId นี้กับ lab ไว้แล้ว retry จึงไม่ทำให้ lab ชี้ผิดแถว

**กรณีที่ retry ได้ 409:** ไฟล์ขึ้น R2 ครบแล้วจริง แต่เน็ตหลุดตอน browser รอคำตอบ browser เลยเห็นเป็น error พอ webhook เติม `archive_uploaded_at` แถวนั้นก็ไม่ใช่ draft ว่างอีกต่อไป ขอ presign ซ้ำจึงได้ 409 ทุกครั้ง ในกรณีนี้ถาดจะเลิกแสดงปุ่ม retry และบอกให้ไปดูสถานะในหน้า Lab images แทน

### 6.6 อัปไฟล์ของ image เดิมซ้ำระหว่างที่รอบก่อนยังไม่จบ
```ts
const previous = jobs.get(id)
jobs.set(id, { file, payload, controller: null })   // ตั้งรอบใหม่ก่อน
previous?.controller?.abort()                       // แล้วค่อยยกเลิกรอบเก่า
```
และใน `runPut` ทุกจุดที่จะเขียนผล เช็กก่อนว่า `jobs.get(id)?.controller === controller` ของตัวเอง ถ้าไม่ใช่แปลว่ามีรอบใหม่มาแทนแล้ว ให้เงียบไป ไม่งั้นรอบเก่าที่ถูก abort จะเขียนทับสถานะของรอบใหม่เป็น 'canceled'

> **💡** นี่คือ race condition แบบเดียวกับ "etag ไม่ตรง" ใน scan reconciler: งานเก่าที่จบทีหลังต้องไม่ไปเขียนทับผลของงานใหม่
> วิธีแก้มาตรฐานคือให้งานแต่ละรอบถือ "ตั๋ว" ของตัวเอง (ที่นี่คือ `controller`) และเขียนผลได้เฉพาะตอนตั๋วยังเป็นตัวปัจจุบัน

### 6.7 ถาด `UploadTray` และ `beforeunload`
- mount ใน `App.tsx` **นอก `RouterProvider`** จึงไม่ถูกถอดเมื่อเปลี่ยนหน้า
- อยู่มุมซ้ายล่าง เพราะ toast อยู่มุมขวาล่าง (`ToastContainer`)
- ในถาดไม่มีลิงก์ไปหน้า Lab images เพราะอยู่นอก router ใช้ `<Link>` ไม่ได้ และถ้าใช้ `<a href>` ธรรมดาจะ reload ทั้งหน้า ซึ่งทำให้การอัปโหลดหาย
- `useWarnBeforeUnload(active)`:
  ```ts
  const warn = (event) => { event.preventDefault(); event.returnValue = '' }
  window.addEventListener('beforeunload', warn)
  ```
  - ลงทะเบียนเฉพาะตอนมีการอัปโหลดค้าง ถ้าลงทะเบียนตลอด browser จะถามทุกครั้งที่ปิดแท็บ
  - browser สมัยใหม่**ไม่แสดงข้อความของเรา** จะแสดงข้อความมาตรฐานของ browser เอง (กันเว็บหลอกผู้ใช้) จึงตั้ง `returnValue = ''`
  - `preventDefault()` คือวิธีตามมาตรฐานใหม่ ส่วน `returnValue` มีไว้รองรับ browser รุ่นเก่า

---

## 7. Frontend: หน้า Lab images และ Lab Builder

### 7.1 `LabImageTab`
| เปลี่ยน | เหตุผล |
|---|---|
| ลบ `abort.current` และ effect ที่ abort ตอน unmount | ตัวการที่ทำให้เปลี่ยนหน้าแล้วอัปโหลดหยุด |
| `UploadPhase` → `submitting: boolean` | ฟอร์มรอแค่ขั้นขอ URL แล้ว ไม่ต้องรู้ % อีก |
| แถวแสดง "Uploading 45% ·" | เห็นความคืบหน้าในรายการด้วย ไม่ใช่แค่ในถาด |
| ซ่อน "No file received yet…" ระหว่างอัป / เพิ่งอัปเสร็จ | ข้อความนี้มีไว้สำหรับการอัปที่ค้างกลางทาง ระหว่างที่อัปอยู่ถ้ายังโชว์จะทำให้เข้าใจผิด |
| `finishedKey` + effect โหลดรายการใหม่ | การอัปที่จบตอนอาจารย์อยู่หน้าอื่น พอกลับมาที่หน้านี้รายการจะอัปเดตเอง |
| `hasInProgress` นับการอัปที่ uploading / done ด้วย | **webhook จาก R2 มาช้ากว่า PUT ไม่กี่วินาที** ถ้าดึงรายการทันทีที่ PUT จบ แถวยังไม่มี `archiveUploadedAt` และ `isInProgress` เดิมจะคืน false การถามซ้ำทุก 10 วินาทีจึงหยุด แถวจะค้างจนกว่าจะกด refresh |
| ช่องที่ว่างแสดง *from image* | แยกให้เห็นว่า "ว่างเพราะใช้ค่าของ image" ไม่ใช่ "ไม่มีค่า" |

### 7.2 `CreateLabModal` (Virtual Lab Builder)
```ts
const upload = await labImageService.createUpload(payload)
await labService.update(lab.id, { imageId: upload.imageId })   // ผูกก่อน
void startUpload(upload, form.image, payload)                  // แล้วอัปเบื้องหลัง
```
- **เลิกส่ง ports / entrypoint / workdir** (เดิมส่ง 8080/5173/8443 และ `/bin/bash /run.sh`)
- **ผูก image กับ lab ก่อนอัปไฟล์:** เดิมผูกหลังอัปเสร็จ แต่ตอนนี้ modal ปิดไปก่อนที่ไฟล์จะอัปเสร็จ จะไม่มีใครผูกให้ ผูกก่อนได้เพราะ `lab_service` ตรวจแค่ว่า image อยู่ในวิชาเดียวกัน และไม่ให้ publish lab จนกว่า image จะ approved

---

## 8. เทส

### 8.1 Backend (`web-portal/backend/tests`)
| เทส | ตรวจอะไร |
|---|---|
| `test_defaults_when_only_required_fields` (แก้) | ไม่ส่ง entrypoint → `None` (เดิมคาด `/bin/bash /run.sh`) |
| `test_blank_entrypoint_and_workdir_are_stored_as_null` ×3 | `""`, `"   "`, `null` → `NULL` ทั้งคู่ |
| `test_entrypoint_and_workdir_are_trimmed` | ช่องว่างหัวท้ายถูกตัด |
| `test_list_returns_null_entrypoint` | GET รายการไม่ล้มเมื่อ entrypoint เป็น `NULL` |
| `test_invalid_body_is_400` (+3 กรณี) | workdir `workspace`, `./app` และ entrypoint ยาว 256 ตัว → 400 |
| `test_null_entrypoint_keeps_image_command` | pod ห้องแลปไม่มี `command` |
| `test_null_entrypoint_uses_image_entrypoint` | AWS ไม่ต่อคำสั่งท้าย image |

รัน (ใน WSL ต้องมี Postgres `virtual_lab_db` ใน Docker Desktop):
```bash
wsl -d Ubuntu-24.04 -- bash -lc 'cd /mnt/c/Users/Panup/VirtualLabtest/web-portal/backend && .venv/bin/python -m pytest tests -q'
```
**ดูตัวเลข skipped ทุกครั้ง** ถ้า Postgres ไม่ขึ้น เทสที่ใช้ DB จะถูก skip ไม่ใช่ fail

### 8.2 Frontend (`web-portal/frontend/src/__tests__`)
| ไฟล์ | เทส |
|---|---|
| `labImageUploads.test.ts` | % เดินและจบเป็น done + toast / done หายจากถาดเอง / cancel ไม่มี toast error / 412 ไม่มีปุ่ม retry / retry ขอ URL ใหม่และส่งไฟล์เดิม / retry ที่ได้ 409 (ไฟล์ขึ้น R2 ไปแล้วจริง) เลิกให้กดซ้ำ / อัปซ้ำแทนที่รอบเดิมไม่เพิ่มแถว / ยังอัปอยู่ปิดจากถาดไม่ได้ |
| `LabImageForm.test.tsx` | Advanced พับไว้ตอนเริ่ม / ไม่แตะ Advanced → ส่ง `[]` และ `null` / ค่าใน Advanced ถูก trim / error ใน Advanced ที่พับอยู่ทำให้เปิดเอง / นับช่องที่กรอก / ถาดว่างไม่ render / `beforeunload` เตือนเฉพาะตอนอัปอยู่ |

รัน (**ต้องใช้ PowerShell และ path ที่ขึ้นต้นด้วย `C:\` ตัวใหญ่** ดูข้อ 12.1):
```powershell
Set-Location 'C:\Users\Panup\VirtualLabtest\web-portal\frontend'
npx vitest run
npx tsc -b
```

### 8.3 ผลที่รันได้ (2026-11-18/19)
| ชุด | ผล |
|---|---|
| Frontend `vitest run` | **69 passed** (15 ไฟล์ ของใหม่ 15 ข้อ) |
| Frontend `tsc -b` / `oxlint src` | ผ่าน / ไม่มี error (warning เดิมใน `runbook.ts` ไม่เกี่ยว) |
| Backend `pytest tests` | **713 passed, 3 failed, 3 skipped** |
| Migration up → down → up บน DB ชั่วคราว | ผ่าน `nullable` เป็น YES → NO → YES |

3 ตัวที่ล้ม **ไม่เกี่ยวกับ Phase 1**:
- `test_vector_agent_config_passes_strict_binary_validation` และ `test_vector_aggregator_config_passes_strict_binary_validation` (SIEM) ต้องเรียก `docker` ภายใน WSL ซึ่งไม่ได้เปิด WSL integration ของ Docker Desktop ไว้ ล้มแบบเดียวกันก่อนเริ่ม Phase 1
- `test_activity.py::test_instructor_feed_for_taught_courses` ล้มเพราะเวลา ดูข้อ 12.4 รันเดี่ยวผ่าน 5/5

### 8.4 ตรวจ migration โดยไม่แตะ DB จริง
สร้าง database ชั่วคราว `vlab_migration_check` ใน Postgres เดียวกัน ชี้ `DATABASE_URL` ไปที่มัน แล้วรัน
`alembic upgrade head` → `alembic downgrade 20261111_01` → `alembic upgrade head` ตรวจ `information_schema.columns.is_nullable` ทุกขั้น เสร็จแล้ว `DROP DATABASE`
เทสของ backend ใช้ `Base.metadata.create_all` ไม่ได้รัน migration จึงต้องตรวจ migration แยกแบบนี้

---

## 9. ทดลองด้วยมือ (ไม่ต้องเปิดเครื่องแลป)

Phase 1 ไม่แตะ K3s หรือ AWS จึงทดสอบบนเครื่องตัวเองได้ทั้งหมด ต้องมี backend + Postgres + frontend dev server และ R2 ที่ตั้งค่าใน `.env` แล้ว

1. `alembic upgrade head` แล้วเปิด backend และ `npm run dev`
2. เข้าหน้าอาจารย์ → วิชา → แท็บ Lab images → Upload image
3. **ฟอร์ม:** Advanced ต้องพับอยู่ / กรอก workdir `abc` แล้วพับ → กด Upload ต้องเปิดเองพร้อม error / กรอก entrypoint แล้วพับ → ต้องเห็นป้าย "1 set"
4. **อัปเบื้องหลัง:** เปิด DevTools → Network → Throttling เป็น "Slow 4G" ให้อัปช้าพอจะทดสอบ แล้ว
   - ฟอร์มปิดทันทีหลัง "Preparing upload…"
   - ถาดมุมซ้ายล่างแสดง % และแถวในรายการแสดง "Uploading xx%"
   - เปลี่ยนไปหน้าอื่นในเว็บ → ถาดยังอยู่และ % เดินต่อ
   - กด reload → browser ต้องถามยืนยัน (กด Cancel เพื่ออยู่ต่อ)
   - กด X ในถาด → Canceled
5. **ล้มแล้ว retry:** ตั้ง Throttling เป็น "Offline" กลางทาง → failed + ปุ่ม retry → กลับ "No throttling" แล้วกด retry
6. **Lab Builder:** สร้าง lab พร้อมไฟล์ .tar → modal ปิดเร็ว, lab ผูก image ทันที, ถาดแสดงการอัป

⚠️ ถ้า backend รันบนเครื่องตัวเองที่ Cloudflare Worker เรียกไม่ถึง webhook จะไม่มา แถวจะค้างที่ "not started" หลังอัปเสร็จ เป็นเรื่องปกติของการทดสอบ local ไม่ใช่บั๊กของ Phase 1

---

## 10. Deploy

1. merge branch
2. backend: `alembic upgrade head` แล้ว restart
3. frontend: build ใหม่
4. ไม่ต้องรัน Ansible ไม่ต้องแตะ Terraform

ถอยกลับ: deploy โค้ดเดิม แล้ว `alembic downgrade 20261111_01` (แถวที่ entrypoint ว่างจะถูกเติม `/bin/bash /run.sh`)

---

## 11. ข้อจำกัดที่ยังเหลือ

| # | เรื่อง | ผลกระทบ | แก้ใน |
|---|---|---|---|
| 1 | **ports ว่างยังไม่ถูกเติมจาก EXPOSE** | image ที่อาจารย์ไม่กรอก ports (รวมทุก image ที่สร้างจาก Lab Builder) **lab เปิดได้แต่ไม่มีลิงก์ให้นักศึกษา** placeholder "Empty = use the image's EXPOSE" จะเป็นจริงหลัง Phase 2 | Phase 2 ข้อ 4.2 — **ควร release Phase 1 พร้อม Phase 2** หรือบอกอาจารย์ให้กรอก ports ไปก่อน |
| 2 | `_build_k8s_task` (ทางเก่าผ่าน SkyPilot บน K3s) ยังเติม `/bin/bash /run.sh` เมื่อ entrypoint ว่าง | ถ้ายังมีการใช้ทางนี้ image ที่ไม่มี `/run.sh` จะเปิดไม่ขึ้น ห้องแลปตอนนี้ใช้ direct pod / warm pod เป็นหลัก | เรื่องที่ต้องตัดสินใจข้อ 1 ในแผน |
| 3 | reload / ปิดแท็บ การอัปโหลดหาย | มีคำเตือนแล้ว แต่กันไม่ได้ 100% (เช่นเครื่องดับ) | ถ้าจำเป็นค่อยทำ R2 multipart upload |
| 4 | ไม่มีหน้าแก้ไข config ของ image หลังอัปโหลด | กรอกผิดต้องอัปใหม่ด้วย tag ใหม่ | ยังไม่อยู่ในแผน |
| 5 | อัปพร้อมกันหลายไฟล์ไม่มีการจำกัด | อัป 3 ไฟล์พร้อมกันจะแบ่งแบนด์วิดท์กัน ไม่พัง แค่ช้า | ไม่จำเป็นต้องแก้ |

---

## 12. บทเรียนระหว่างทำ

### 12.1 vitest บน Windows ล้มทุกไฟล์ถ้า path ขึ้นต้นด้วย `c:\` ตัวเล็ก
อาการ: เทสทุกไฟล์ (แม้แต่ไฟล์ที่ไม่ได้แก้) ล้มด้วย `TypeError: Cannot read properties of undefined (reading 'config')` ที่บรรทัด `describe(`
สาเหตุ: terminal ของ VS Code ส่ง cwd เป็น `c:\Users\...` (ตัวเล็ก) ส่วน Node resolve module บางตัวเป็น `C:\...` (ตัวใหญ่) vitest จึงถูกโหลดสองครั้งเป็นคนละ instance และตัวที่ไฟล์เทส import มาไม่มี config ของตัวที่กำลังรัน
แก้: `Set-Location 'C:\Users\...'` (ตัวใหญ่) ก่อน `npx vitest run`
> **💡** error ที่เกิดกับ "ทุกเทส รวมของที่ไม่ได้แตะ" เกือบทุกครั้งคือปัญหาสภาพแวดล้อม ไม่ใช่โค้ด
> อย่าเริ่มจากการแก้โค้ด ให้รันเทสไฟล์ที่ง่ายที่สุดบน branch หลักก่อน ถ้าก็ยังล้มแปลว่าปัญหาไม่ได้อยู่ที่ diff ของเรา

### 12.2 `node_modules` ของ frontend ไม่ครบ
มีแค่ ~100 package และไม่มี `vitest` / `tsc` แก้ด้วย `npm ci` (ติดตั้งตาม `package-lock.json` เป๊ะ ๆ ไม่แก้ lockfile) ต่างจาก `npm install` ที่อาจอัปเดต lockfile

### 12.3 เทส backend ต้องมี Docker Desktop
เปิดไม่ทัน = 510 เทสถูก skip และรายงานว่า "passed" ได้ทั้งที่เทสสำคัญไม่ได้รันเลย

### 12.4 เทสที่ล้มเพราะรันข้ามเที่ยงคืน (บั๊กเดิม ไม่ได้แก้ใน Phase 1)
`test_instructor_feed_for_taught_courses` สร้าง session ที่ `NOW - 5 นาที` โดย `NOW = datetime.now()` ถูกคำนวณ**ครั้งเดียวตอน import ไฟล์เทส** ส่วน `activity_service` นับ `launch_count` เฉพาะ session ตั้งแต่ **เที่ยงคืนเวลาไทย** ของเวลาจริงตอนที่เรียก API
รอบนี้ชุดเทสเริ่มก่อนเที่ยงคืนไม่กี่นาทีแล้วรันข้ามเที่ยงคืน session ในเทสจึงตกไปอยู่ "เมื่อวาน" และไม่ถูกนับ
แก้ได้โดยให้เทสสร้าง session ที่เวลา "เที่ยงคืนวันนี้ + 1 นาที" แทน หรือ freeze เวลาในเทส
> **💡** เทสที่ใช้ `datetime.now()` จะเปราะเสมอเมื่อโค้ดมีขอบเขตของวัน / เดือน ถ้าเทสล้มแบบสุ่ม ๆ ให้ดูเวลาที่รันก่อน

---

## 13. คำศัพท์และแนวคิด

| คำ | ความหมาย |
|---|---|
| presigned URL | URL ที่ backend เซ็นด้วย key ของ R2 ไว้ล่วงหน้า ให้ browser ใช้ PUT ไฟล์ตรงเข้า bucket ได้ภายในเวลาที่กำหนด โดย browser ไม่ต้องรู้ key |
| unmount | React ถอด component ออกจากหน้า state ใน `useState` หายตาม |
| client-side routing | เปลี่ยนหน้าโดยไม่โหลดหน้าใหม่จาก server (JavaScript และหน่วยความจำของแท็บยังอยู่) ต่างจากการกด reload |
| zustand | library จัดการ state ขนาดเล็ก สร้าง store ด้วย `create()` อ่านใน component ด้วย hook และอ่าน/เขียนนอก React ด้วย `getState()` / `setState()` |
| `AbortController` | ตัวสั่งยกเลิก request ส่ง `signal` ให้ axios แล้วเรียก `abort()` axios จะ reject ด้วย `CanceledError` |
| `beforeunload` | event ที่ browser ยิงก่อนปิด / reload แท็บ ใช้ถามยืนยันได้แต่กำหนดข้อความเองไม่ได้ |
| `field_validator(mode="before")` | validator ของ pydantic ที่รันก่อนตรวจ type ใช้แปลงค่าดิบ เช่น trim, `""` → `None` |
| `alembic alter_column` | เปลี่ยนคุณสมบัติของคอลัมน์ที่มีอยู่ (type, nullable, default) ใน migration |
| draft row | แถว `lab_images` ที่สร้างตอนขอ presigned URL ก่อนไฟล์จะขึ้น R2 webhook เติม etag / ขนาดเมื่อไฟล์มาถึง |

---

## 14. คำถามทบทวน

1. ถ้าเอา validator `_blank_to_none` ออก แล้วอาจารย์ส่ง entrypoint เป็น `"  "` lab บนห้องแลปจะเป็นยังไง และบน AWS จะเป็นยังไง
2. ทำไม migration ไม่เปลี่ยน `/bin/bash /run.sh` ของแถวเดิมเป็น `NULL` ไปด้วยเลย
3. ถ้าส่วน Advanced ใช้ `{advancedOpen && <div>…</div>}` แทน class `hidden` จะเกิดปัญหาอะไร และเทสข้อไหนจะจับได้
4. ทำไม `File` ไม่อยู่ใน zustand store
5. ถ้าลบเงื่อนไข `jobs.get(id)?.controller !== controller` ใน `runPut` เทสข้อไหนจะล้ม และผู้ใช้จะเห็นอะไร
6. ทำไม `UploadTray` ต้องอยู่นอก `RouterProvider` และทำไมในถาดถึงไม่มีลิงก์ไปหน้า Lab images
7. ถ้า `hasInProgress` ไม่นับการอัปที่ `done` แถวในรายการจะค้างที่สถานะไหน เพราะอะไร
8. หลัง Phase 1 อาจารย์อัป image ที่มี `EXPOSE 8080` โดยไม่กรอก ports นักศึกษาจะเปิด lab ได้ไหม ได้ลิงก์ไหม (ดูข้อ 11)
