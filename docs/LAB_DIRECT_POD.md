# เครื่องแลปสร้าง pod ตรง ไม่ผ่าน SkyPilot — กฎเดียว "AUTO" ทุก lab

สถานะ: **ทำแล้ว** (2026-10-21) — pytest 263/263, รอเทสจริงบนหน้าเว็บ (หัวข้อ "เทส")
ต่อจาก `docs/RUN_TARGET_AUTO.md` (AUTO แบบเดิม) และผลเทสหน้าเว็บจริงใน `docs/NextToU.md` หัวข้อ 9

## ทำไม

เทสบนหน้าเว็บจริง 2026-10-20 / 21 (master ใหม่ + web-service + Sophia):

| ทาง | ผล |
|---|---|
| warm pod (เครื่องแลป + มีคาบ) | ✅ ทุกครั้ง ~0–1 วิ |
| EC2 ผ่าน SkyPilot (ข้างนอก) | ✅ ทุกครั้ง ~1.5–2 นาที (AMI bake runtime ไว้แล้ว) |
| **K8s ผ่าน SkyPilot** (เครื่องแลป ไม่มีคาบ / lab K8s จากข้างนอก) | ⚠️ ผ่านบ้างพังบ้าง **"เป็นบางเวลา"** 3–4 นาทีเมื่อผ่าน |

ทาง K8s ผ่าน SkyPilot ต้องลงของใน pod ใหม่ทุกครั้ง: apt (openssh-server / gcc / fuse …) → uv / conda → SkyPilot runtime
→ Ray → ssh เข้าไปรัน — ทุกขั้นต้องใช้เน็ต และ SkyPilot server ยังสั่ง apt ซ้ำผ่าน `kubectl exec` ทับกับ script ใน pod อีกชั้น
ที่เจอ:
1. CoreDNS ถาม DNS ปลายทาง IPv6 ของ router → `network is unreachable` → apt / curl หาชื่อไม่เจอ
   (**แก้แล้ว** role k3s ใช้ `resolv-conf` IPv4 เท่านั้น)
2. หลังแก้ DNS ยังพัง: apt ใน pod กับ apt ที่ server สั่งผ่าน `kubectl exec` ทำพร้อมกัน → ฝั่ง server ลงไม่ได้ (เดาว่า lock)
   → `exit 137` → container ตาย (**ยังพิสูจน์ไม่ได้** log หายไปพร้อม pod)

เครื่องแลปเป็น node ที่รู้อยู่แล้วว่าเป็นเครื่องไหน (หาจาก IP ของคนกด) ไม่ต้องให้ SkyPilot "หาเครื่อง" ให้
warm pod พิสูจน์แล้วว่าสร้าง pod ด้วย k8s API ตรง ๆ ใช้ได้และเร็ว — **ใช้ทางเดียวกันตอนไม่มี warm pod**
SkyPilot เหลือทำแค่สิ่งที่มันเก่ง: หาเครื่องบน cloud (EC2)

## กฎใหม่ (กฎเดียว ทุก lab)

| กด Start จาก | ได้ |
|---|---|
| เครื่องแลป (IP = InternalIP ของ worker ที่ Ready) + มี warm pod ว่างของ image นี้ | warm pod (เหมือนเดิม) |
| เครื่องแลป + มี warm pod ของ image นี้ที่**กำลังจะพร้อม** | **รอ warm pod ตัวนั้น** (สูงสุด `WARM_POD_WAIT_SECONDS`) |
| เครื่องแลป + ไม่มี warm pod | **pod ตรง** บนเครื่องนั้น (ใหม่) |
| ที่อื่น / เช็ก K3s ไม่ได้ | EC2 ผ่าน SkyPilot (เหมือนเดิม) |

- **ไม่ดู `labs.run_target` แล้ว** (เก็บคอลัมน์ไว้ ไม่ต้อง migration / แก้หน้าอาจารย์ ลบทีหลังได้)
- lab ที่ตั้ง `KUBERNETES` แล้วกดจากข้างนอก **เปลี่ยนพฤติกรรม**: เดิมได้ pod บน cluster (ไม่ pin) → ตอนนี้ไป EC2
- เครื่องแลปไม่มีที่ว่าง → **error บอกตรง ๆ** ไม่ส่งไป EC2 (Pete 2026-10-21: เครื่องแลปเป็นของ lab อย่างเดียว ไม่มีงานอื่นแย่ง)

## pod ตรงหน้าตาเหมือน warm pod

ใช้ container spec ตัวเดียวกับ `build_warm_daemonset` (image / env / entrypoint / workdir / requests / hostPort)
ต่างกันแค่เป็น Pod เดี่ยวที่สร้างตอนกด ไม่ใช่ DaemonSet ที่สร้างรอ

| | warm pod | pod ตรง (ใหม่) |
|---|---|---|
| สร้างเมื่อ | ก่อนคาบ (scheduler) | ตอนกด Start |
| ชื่อ | `warm-<image>-xxxxx` | `lab-pod-<session id 8 ตัว>` (ไม่ใช่ `lab-` เฉย ๆ เพราะ seed มี `lab-se301-sophia`) |
| ลงเครื่อง | DaemonSet ทุก worker | `nodeSelector: kubernetes.io/hostname=<เครื่องที่กด>` |
| label | `vlab/lab=true`, `vlab/warm…` | `vlab/lab=true`, `vlab/session-id` (annotation) |
| port | hostPort (+ `hostIP 127.0.0.1` เมื่อ `LAB_ISOLATION_ENABLED`) | เหมือนกัน |
| endpoint | `http://localhost:<port>` | เหมือนกัน (`warm_endpoints`) |
| image | pull ไว้แล้วโดย prewarm | มีคาบ = pull ไว้แล้ว / ไม่มีคาบ = pull ตอนนั้น (~10–30 วิ, 700 MB จาก registry ในบ้าน) |
| ปิด / หมดเวลา / pod หาย | ลบ pod (DaemonSet สร้างใหม่) | ลบ pod (จบ) |

`restartPolicy: Always` (แอปใน lab ตายเองให้ kubelet เปิดใหม่) `terminationGracePeriodSeconds: 5` เหมือน warm pod

## ลำดับใน `create_session` (หลังเช็ก user / lab / enrollment / image / session ซ้ำ เหมือนเดิม)

```
node = _client_node(client_ip, always=True)          # เดิมของ AUTO
if node is None:                                     # ข้างนอก / K3s ล่ม
    → EC2 ผ่าน SkyPilot (โค้ดเดิม ไม่แตะ)
else:
    warm = _try_warm_pod(...)                        # เดิม
    if warm: return warm
    if มี warm pod ของ image นี้บน node ที่ยังไม่ Ready (ไม่ถูกลบ, state free):
        รอจน Ready สูงสุด WARM_POD_WAIT_SECONDS แล้ว _try_warm_pod อีกครั้ง
    → _launch_direct_pod(...)                        # ใหม่
```

`_launch_direct_pod`:
1. สร้าง session `PENDING` + `k8s_pod_name = lab-pod-…` + `node_name` ก่อน (ถ้า backend ตายกลางทาง reconciler ยังตามลบ pod ได้)
2. `create_namespaced_pod`
3. poll ทุก 2 วิ จน Ready สูงสุด `DIRECT_POD_READY_TIMEOUT` (ค่าเริ่ม 180 วิ — เผื่อ pull image)
   - `PodScheduled=False` reason `Unschedulable` → ลบ pod, session `FAILED` → **error "เครื่องนี้ไม่มีที่ว่างสำหรับ lab"**
   - container `ErrImagePull` / `ImagePullBackOff` / `CrashLoopBackOff` → ลบ pod, `FAILED` + ข้อความจาก k8s
   - หมดเวลา → ลบ pod, `FAILED`
4. Ready → session `RUNNING`, `endpoints = warm_endpoints(...)`, `expires_at = now + lifespan_minutes`
5. response รูปเดิม `launch_mode = "pod"`, `run_target = "kubernetes"` (หน้าเว็บไม่ต้องแก้)

## reconcile / delete / กดซ้ำ

ตอนนี้ทั้งหมดดูแค่ `_is_warm_session` (มี `k8s_pod_name` ขึ้นต้น `warm-` และไม่มี `sky_cluster_name`)
→ ขยายเป็น `_is_pod_session`: ขึ้นต้น `warm-` **หรือ** `lab-pod-` แล้วทุกทางใช้ได้ทันที:
- `delete_session` → `delete_pod`
- `_reconcile_warm` → ถึง `expires_at` ลบ pod / pod หาย = `LOST`
- `create_session` กดซ้ำ → pod ยังอยู่ = 409, pod หาย = ปิด session เดิมแล้วเปิดใหม่
- PENDING ค้างเกิน `PENDING_TIMEOUT` → `FAILED / STALE_PENDING` + ลบ pod (เพิ่มให้ทาง pod เหมือนที่ทำกับ cluster)

## เก็บ log ตอนพัง (ข้อ 3 ที่คุยกัน)

pod ที่พังลบทิ้งแล้ว log หาย — วันนี้ต้องนั่งดึงเองทุก 3 วิ
ก่อนลบ pod ที่ launch พัง: `read_namespaced_pod_log(tail 200)` + events ของ pod → `logger.warning("[pod failed] …")`
(EC2 ใช้ `_job_log_tail` เดิมอยู่แล้ว)

## settings ใหม่

| ค่า | เริ่มต้น | ใช้ทำ |
|---|---|---|
| `WARM_POD_WAIT_SECONDS` | 60 | รอ warm pod ที่กำลังขึ้น (DaemonSet เพิ่งสร้างใหม่หลังคนก่อนปิด) |
| `DIRECT_POD_READY_TIMEOUT` | 180 | รอ pod ตรง Ready (รวม pull image) |
| `LAB_MACHINE_LAUNCH` | `pod` | เครื่องแลปไม่มี warm pod → `pod` (ตรง) / `skypilot` (ทางเดิม ดูหัวข้อ "ทางสำรอง") |

role `web-service` ไม่ต้องใส่ (ใช้ค่าเริ่ม) — `WARM_POD_ENABLED` / `LAB_ISOLATION_ENABLED` ความหมายเดิม

## ไม่แตะ
frontend, DB / migration, Ansible, ทาง EC2 ทั้งหมด, prewarm scheduler, NetworkPolicy
## เก็บทาง SkyPilot บน K8s ไว้เป็นทางสำรอง (Pete 2026-10-21)

ไม่ลบ — สลับได้ด้วย setting ตัวเดียว (ค่าเริ่ม = pod ตรง)

| `LAB_MACHINE_LAUNCH` | เครื่องแลป + ไม่มี warm pod |
|---|---|
| `pod` (ค่าเริ่ม) | pod ตรง (ใหม่) |
| `skypilot` | SkyPilot in-cluster pin เครื่องนั้น + label `vlab/lab` (ทางเดิม `_build_k8s_task`) |

- ทาง pod ตรงมีปัญหาตอนใช้จริง → `ansible-playbook ... --limit webservice --tags web-service -e webservice_lab_machine_launch=skypilot`
  (หรือตั้ง `webservice_lab_machine_launch` ใน group_vars) — แก้ `.env` ตรง ๆ ได้แต่ playbook รอบหน้าจะเขียนทับ
- warm pod / EC2 / กฎ "ข้างนอก → EC2" เหมือนกันทั้งสองค่า
- SkyPilot server เปิด `kubernetes/in-cluster` ไว้ตามเดิม (`sky check` เห็นอยู่แล้ว)
- เทสเดิมของทาง SkyPilot บน K8s **เก็บไว้** แค่ตั้ง `LAB_MACHINE_LAUNCH=skypilot` ในกลุ่มนั้น

## เทส

ใช้ `FakeK8s` เดิม (เพิ่ม `create_namespaced_pod` / `read_namespaced_pod_log` / สถานะ pod ตามที่เทสตั้ง)

| กลุ่ม | เคส |
|---|---|
| กฎ | เครื่องแลป → pod / warm, ข้างนอก → EC2, K3s ล่ม → EC2, lab `KUBERNETES` จากข้างนอก → EC2, `AWS` จากเครื่องแลป → pod |
| pod ตรง | spec: nodeSelector / label / hostPort localhost / requests / env / entrypoint, endpoint `localhost`, session RUNNING + expires_at, ไม่เรียก SkyPilot |
| พัง | Unschedulable → error เครื่องเต็ม + ลบ pod + FAILED, ImagePullBackOff, หมดเวลา, create ได้ 409 / 403, log ถูกเก็บก่อนลบ |
| warm กำลังขึ้น | รอแล้วได้ warm / รอหมดเวลาแล้วไป pod ตรง |
| lifecycle | delete ลบ pod, reconcile หมดอายุ / pod หาย / PENDING ค้าง, กดซ้ำ 409 / pod หายเปิดใหม่ได้ |
| สวิตช์ | `LAB_MACHINE_LAUNCH=skypilot` → ทางเดิม (SkyPilot pin เครื่อง), `pod` → pod ตรง, warm / EC2 ไม่เปลี่ยนตามสวิตช์ |
| ของเดิม | เทส "lab K8s ผ่าน SkyPilot" (ราว 20 ตัวใน `tests/session/`) เก็บไว้ ตั้ง `LAB_MACHINE_LAUNCH=skypilot` / เคสที่กดจากข้างนอกเปลี่ยนเป็น EC2 |

เทสจริงหลังทำ (หน้าเว็บ + tunnel แบบวันนี้): ไม่มีคาบ → pod ตรงบน worker-pete, มีคาบ → warm, ข้างนอก → EC2,
กด Start ซ้ำทันทีหลังปิด → รอ warm, เปิดค้างจนหมดอายุ → reconciler ลบ, launch 10 รอบติดไม่พัง

## ลำดับงาน
1. Pete อนุมัติ doc นี้ (+ ตอบคำถามข้างล่าง)
2. `warm_pod_service.py`: แยก `_lab_container()` + `build_lab_pod()` + `create_pod` / `pod_phase` / `pod_log`
3. `session_service.py`: กฎใหม่ + `_launch_direct_pod` + รอ warm + `_is_pod_session` + เก็บ log
4. เทส → `pytest` ทั้งชุดผ่าน
5. deploy web-service → เทสจริงตามข้างบน → อัปเดต `RUN_TARGET_AUTO.md` / `NextToU.md`

## คำถามให้ Pete
1. ~~ลบโค้ด SkyPilot ทาง K8s ทิ้งไหม~~ → **เก็บไว้เป็นทางสำรอง** สลับด้วย `LAB_MACHINE_LAUNCH` (Pete 2026-10-21)
2. `launch_mode` ของ pod ตรงใช้ `"pod"` โอเคไหม (warm = `"warm_pod"`, EC2 = `"skypilot"`)
3. ค่าเริ่ม `WARM_POD_WAIT_SECONDS = 60` / `DIRECT_POD_READY_TIMEOUT = 180` โอเคไหม
4. เครื่องแลปเต็ม: error (ตามที่เขียนไว้) หรือ fallback ไป EC2 — fallback ต้องเพิ่ม ACL `tag:vlab-worker` →
   `10.10.2.0/24:8080,5173,8443` และ `--accept-routes` บน worker (ตอนนี้เครื่องแลปเปิด EC2 ไม่ได้)
