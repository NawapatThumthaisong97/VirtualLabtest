# python-web-lab: image ทดสอบระบบอัปโหลด lab image (Phase 1–3)

lab เขียนโปรแกรม Python ที่ใช้งานได้จริง ใช้ทดสอบ [LAB_IMAGE_UPLOAD_PLAN.md](../../docs/LAB_IMAGE_UPLOAD_PLAN.md)
- `passed/` คือ lab ที่ดี ต้องสแกนผ่านและเปิดได้
- `failed/` คือ lab ที่ตั้งใจให้พัง ทีละแบบ แต่ละแบบต่อยอดจาก `passed` และแก้ไปแค่อย่างเดียว

## ข้างใน lab

| port | คืออะไร | ขึ้นภายใน |
|---|---|---|
| 5000 | Flask จาก `app.py` (`--reload` แก้แล้วเห็นผลทันที) | ~2 วินาที |
| 8888 | JupyterLab: editor, notebook แบบฝึกหัด 3 อัน, terminal (ไม่มีรหัส) | ~4 วินาที |

แบบฝึกหัด: `01_basics` (ตัวแปร, loop), `02_functions` (ฟังก์ชัน, dict), `03_flask` (เพิ่ม route `/square/<n>` ใน `app.py` แล้วเซลล์ตรวจเรียก port 5000 จริง)
`start-lab` เปิดทั้งสองตัว ถ้าตัวใดตัวหนึ่งตาย จะปิดอีกตัวแล้วจบด้วย exit ≠ 0 เพื่อให้ระบบเห็นว่า lab ล้ม ไม่ใช่ใช้ได้ครึ่งเดียว

⚠️ Jupyter ไม่มีรหัส ใช้ทดสอบภายในทีม หรือเปิด `LAB_ISOLATION_ENABLED` เท่านั้น

## Build

ต้องมี Docker (Docker Desktop ก็ได้) รันจาก Git Bash หรือ WSL:
```bash
./build.sh                    # ทุกแบบ → dist/<ชื่อ>.tar
./build.sh passed no-command  # เฉพาะบางแบบ
```
| ไฟล์ | ขนาด |
|---|---|
| `passed.tar`, `localhost-only.tar`, `exits-immediately.tar`, `unused-port.tar` | ~97 MB |
| `no-command.tar` | ~0.6 MB |

`dist/` ไม่ถูก commit

## อัปโหลด

หน้าอาจารย์ → วิชา → Lab images → Upload image
- Repository: `python-web-lab` (ฟอร์มเติม `vlab/` ให้เอง ใต้ฟอร์มต้องขึ้น `vlab/python-web-lab:<tag>`)
- Tag: ตามตาราง (ห้ามซ้ำ tag เดิม)
- **ไม่กรอกอะไรใน Advanced** ยกเว้นแถวที่บอกไว้

## ผลที่ต้องเห็น

ค่าใน "หน้า Lab images" คำนวณล่วงหน้าแล้วด้วย `image_info()` ของ runner 1.2.0 จาก config จริงของแต่ละ image

### passed/

| tag | หน้า Lab images หลังสแกน | กด Start ในห้องแลป (K3s) | กด Start นอกห้องแลป (AWS) |
|---|---|---|---|
| `v1` | PASSED → Ready<br>Ports `5000, 8888` *from image*<br>Entrypoint `start-lab --notebook-dir=/home/student/lab` *from image*<br>Workdir `/home/student/lab` *from image*<br>ไม่มี warning "runs as root"<br>`scan_summary.runnerVersion` = `1.2.0` | ได้ลิงก์หลัง port 5000 ตอบ (~2 วินาที) ลิงก์ 8888 อาจยังไม่ขึ้นอีก ~2 วินาที (probe เช็กแค่ port แรก) | ได้ลิงก์หลังทั้ง 5000 และ 8888 ตอบ |

ระหว่างอัปโหลด (Phase 1): ตั้ง DevTools → Network → Slow 4G แล้วเปลี่ยนหน้า ถาดมุมขวาล่างต้องเดินต่อ และ reload ต้องถูกถาม

### failed/

| แบบ | tag | หน้า Lab images หลังสแกน | Start (K3s) | Start (AWS) |
|---|---|---|---|---|
| `localhost-only` | `fail-localhost` | PASSED เหมือน `v1` (การสแกนดูไม่ออก) | ไม่ Ready เพราะ probe ต่อ 5000 ไม่ได้ → FAILED เมื่อครบ `DIRECT_POD_READY_TIMEOUT` (180 วินาที) | `vlab: port 5000 not ready after 180s` → FAILED, ลบเครื่อง |
| `exits-immediately` | `fail-exit` | PASSED<br>Entrypoint `python -c "print('setup done'); raise SystemExit(3)"` *from image* | container จบทันที → `CrashLoopBackOff` → FAILED เร็ว | `lab container exited before port 5000 was ready` + log `setup done` |
| `unused-port` | `fail-unused-port` | PASSED<br>Ports `80, 5000, 8888` *from image* | probe รอ port 80 ที่ไม่มีใครฟัง → FAILED หลัง 180 วินาที | port 80 not ready → FAILED |
| `no-command` | `fail-no-command` | PASSED + warning **No command** และ **No ports**<br>Entrypoint `(none)`, Workdir `/`<br>+ warning "runs as root" | container สร้างไม่ได้ (`no command specified`) → FAILED | `docker run` ล้มตั้งแต่ setup → FAILED |

- **`unused-port`:** คือข้อจำกัด P2-11 ข้อ 7 ใน [LAB_IMAGE_UPLOAD_WORKING.md](../../docs/LAB_IMAGE_UPLOAD_WORKING.md) (EXPOSE ที่ติดมาจาก base image) ตอนนี้พังจริงตามที่จดไว้ ถ้าวันหนึ่งแก้แล้ว ให้ย้ายแถวนี้ไปอยู่ใน `passed/`
- **`no-command` บน K3s:** สถานะ `CreateContainerError` ไม่อยู่ใน `FATAL_WAITING_REASONS` ([warm_pod_service.py](../../web-portal/backend/app/services/warm_pod_service.py)) อาจต้องรอจนครบ 180 วินาที แทนที่จะล้มทันที ให้จดเวลาที่ใช้ไว้ตอนทดสอบ

### ทดสอบ Advanced ด้วย `passed.tar` (ไม่ต้อง build เพิ่ม)

| tag | กรอกใน Advanced | ต้องเห็น |
|---|---|---|
| `v1-ports` | Exposed ports: `5000` | Ports `5000` **ไม่มี** *from image* (ค่าที่อาจารย์กรอกชนะ) |
| `v1-env-local` | Environment: `FLASK_HOST` = `127.0.0.1` | พังแบบเดียวกับ `localhost-only` |
| `v1-entrypoint` | Entrypoint: `echo bye` | Entrypoint แสดง `echo bye` (ไม่มี *from image*) / Start: FAILED ทันทีทั้ง K3s และ AWS (ทับ ENTRYPOINT ของ image ได้จริง) |
| `fix-unused-port` | ใช้ `unused-port.tar` + Exposed ports: `5000, 8888` | เปิดได้ เป็นวิธีที่อาจารย์แก้ข้อจำกัดข้อ 7 ได้เอง |

## ดูระหว่างทดสอบ

```bash
export KUBECONFIG="$(git rev-parse --show-toplevel)/web-portal/backend/kubeconfig.yaml"   # cluster ของ mn ที่ backend ใช้
kubectl -n vlab-scan get pods -o wide -w        # pod สแกนต้องลง masterpc
kubectl get pods -o wide -w                     # pod ของ lab (Start ในห้องแลป)
kubectl describe pod <lab pod>                  # Readiness probe / Events
```
