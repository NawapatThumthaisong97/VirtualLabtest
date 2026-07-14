# SkyPilot + K3s — Runbook & คู่มือแก้ปัญหา

> สรุปจาก session จริงที่ setup SkyPilot API server (stable `0.12.3.post1`) บน K3s single-node
> บน ThinkPad โดยเข้าผ่าน NodePort `30080`
>
> เอกสารนี้มี 3 ส่วน: (1) setup สะอาดที่กันปัญหาทั้งหมด, (2) ปัญหาที่เจอจริงเรียงตามลำดับ +
> สาเหตุ + วิธีแก้, (3) checklist ตอนอัปเกรดเวอร์ชัน

---

## ทำไมมันวุ่นวาย (อ่านก่อน)

ปัญหาทั้งหมดใน session นี้มาจาก **event เดียว**: การเปลี่ยนจาก nightly → stable ด้วยวิธี
`helm uninstall` แล้วลงใหม่ ตัวนี้จุดชนวนให้เกิด domino ต่อกัน 4 อย่าง:

```
helm uninstall (เพื่อ downgrade nightly → stable)
        │
        ├─► PVC skypilot-state ถูกลบตาม  ──► pod ใหม่ Pending "PVC not found"
        │
        └─► ลงใหม่โดยไม่ใส่ NodePort flag ──► service กลับเป็น LoadBalancer
                                                   │
                                                   ├─► EXTERNAL-IP <pending> ตลอด (K3s ไม่มี LB)
                                                   └─► พอร์ต 30080 ไม่เปิด ──► curl / login fail
```

**บทเรียนหลัก 1 บรรทัด:** ทุก setting ที่ set ผ่าน `--set` ตอน install จะหายเมื่อ uninstall —
ถ้าไม่อยากเจอซ้ำ ต้องรวมทุก flag ไว้ใน install command เดียว (หรือ `values.yaml` ไฟล์เดียว)

---

## ส่วนที่ 1: Setup สะอาด (กันปัญหาทั้งหมด)

### ค่าเวอร์ชันที่ใช้ (pin ตายตัว)

| ฝั่ง | package/chart | เวอร์ชัน | format |
|---|---|---|---|
| Client (pip) | `skypilot[kubernetes]` | `0.12.3.post1` | `.post1` |
| Server (helm) | `skypilot/skypilot` | `0.12.3+post.1` | `+post.1` |

> helm กับ pip เขียนเลข post-release ต่างกัน (`+post.1` vs `.post1`) — ใส่ผิด format มันหาไม่เจอ

### 1.1 ติดตั้ง server ครั้งเดียวจบ (NodePort + auth รวมในคำสั่งเดียว)

```bash
NAMESPACE=skypilot
RELEASE_NAME=skypilot
WEB_USERNAME=admin
WEB_PASSWORD=admin123
AUTH_STRING=$(htpasswd -nb $WEB_USERNAME $WEB_PASSWORD)

helm upgrade --install $RELEASE_NAME skypilot/skypilot \
  --version 0.12.3+post.1 \
  --namespace $NAMESPACE --create-namespace \
  --set ingress.authCredentials=$AUTH_STRING \
  --set ingress-nginx.controller.service.type=NodePort \
  --set ingress-nginx.controller.service.nodePorts.http=30080
```

รอ pod ขึ้น `2/2 Running`:

```bash
kubectl get pods -n $NAMESPACE -w
```

### 1.2 ยืนยันว่า service เป็น NodePort จริง

```bash
kubectl get svc -n $NAMESPACE
```

ต้องเห็น `skypilot-ingress-nginx-controller` เป็น **TYPE=NodePort** และ **PORT(S)** มี `80:30080/TCP`
(ถ้าเห็น `LoadBalancer` + `EXTERNAL-IP <pending>` = flag NodePort หาย ต้อง re-apply)

### 1.3 ทดสอบ endpoint ก่อน login

```bash
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
curl http://${WEB_USERNAME}:${WEB_PASSWORD}@${NODE_IP}:30080/api/health
```

ได้ response = server พร้อม (ถ้า `Couldn't connect` = ปัญหา NodePort/IP ไม่ใช่ auth)

### 1.4 ฝั่ง client

```bash
source /home/pete/skypilot_proj/skypilot-env/bin/activate
pip uninstall -y skypilot-nightly            # ถอน nightly ให้เกลี้ยงก่อน
pip install "skypilot[kubernetes]==0.12.3.post1"
sky --version                                 # ต้องได้ 0.12.3.post1 (ไม่มีคำว่า nightly)

sky api login -e http://admin:admin123@${NODE_IP}:30080
sky check kubernetes
```

---

## ส่วนที่ 2: ปัญหาที่เจอจริง เรียงตามลำดับ

### ปัญหา #1 — เวอร์ชัน nightly ไม่นิ่ง

**อาการ:** ใช้ nightly (`skypilot-nightly` + `--devel`) ทั้ง client/server → wheel hash เปลี่ยนบ่อย
ต้อง rebake image ถี่ เสี่ยงหลุด sync แบบไม่รู้ตัว

**สาเหตุ:** nightly แพ็กจาก source ล่าสุดทุก dev commit → content/hash ไม่นิ่ง

**วิธีแก้:** pin เป็น stable ทั้ง 2 ฝั่ง (ต้องเปลี่ยน**คู่กันเสมอ** ไม่งั้น client/server version mismatch)
- chart: `skypilot/skypilot-nightly --devel` → `skypilot/skypilot --version 0.12.3+post.1`
- pip: `skypilot-nightly[kubernetes]` → `skypilot[kubernetes]==0.12.3.post1`

**หาเลข stable ล่าสุดยังไง:** `helm search repo skypilot/skypilot --versions` แล้วเอาตัวบนสุดที่
**ไม่มี** `rc`/`dev`/`nightly` ต่อท้าย

---

### ปัญหา #2 — pod ค้าง Pending: "persistentvolumeclaim skypilot-state not found"

**อาการ:**
```
FailedScheduling  0/1 nodes are available: persistentvolumeclaim "skypilot-state"
                  is being deleted / not found
```

**สาเหตุ:** `helm uninstall` ลบ PVC `skypilot-state` ไปด้วย พอลงใหม่ helm คาดว่าจะมี PVC เดิมอยู่
(ปกติ uninstall ไม่ลบ PVC) แต่รอบนี้มันหายเกลี้ยง → pod หา volume mount ไม่เจอ

**วิธีแก้ที่ผิด (ที่ลองแล้วไม่หาย):** `kubectl delete pod` เฉยๆ — deployment สร้าง pod ใหม่ที่ยังชี้
หา PVC เดิมที่หายไป การลบ pod ไม่ได้สร้าง PVC ใหม่

**วิธีแก้ที่ถูก:** ลบ release + เคลียร์ของค้างให้เกลี้ยง แล้วลงใหม่ตั้งแต่ศูนย์ (helm จะสร้าง PVC ใหม่เอง)
```bash
helm uninstall $RELEASE_NAME -n $NAMESPACE
kubectl get all -n $NAMESPACE                       # เช็คของค้าง
kubectl get pvc -n $NAMESPACE
kubectl delete pvc --all -n $NAMESPACE              # ลบ PVC ค้าง (ถ้ามี)
# แล้วลงใหม่ตามส่วนที่ 1.1
```

** ผลข้างเคียง:** PVC หาย = state ของ API server รีเซ็ต (cluster records / job history เดิมหาย)
สำหรับ lab ที่เพิ่ง setup ไม่มีปัญหา แต่ถ้ามี cluster ค้างเก่า ใช้ `sky status --refresh` ให้มันเช็คใหม่

---

### ปัญหา #3 — curl / login ไม่ติด: service เป็น LoadBalancer แทน NodePort

**อาการ:**
```
curl: (7) Failed to connect to 192.168.1.121 port 30080: Couldn't connect to server
```
```
kubectl get svc -n skypilot:
skypilot-ingress-nginx-controller  LoadBalancer  10.43.11.130  <pending>  80:31284/TCP,443:31721/TCP
```

**สาเหตุ 2 ชั้น:**
1. ลงใหม่โดยไม่ใส่ NodePort flag → service กลับเป็น default = `LoadBalancer`
2. K3s homelab ไม่มี cloud load balancer จ่าย IP → `EXTERNAL-IP` ค้าง `<pending>` ตลอด และพอร์ต
   ที่เปิดจริงเป็นเลขสุ่ม (`31284`) ไม่ใช่ `30080` → curl พอร์ต 30080 เลยไม่มีอะไร listen

> จุดสังเกต: `Couldn't connect to server` = ไม่มีอะไร listen ที่ระดับ TCP เลย (คนละเรื่องกับ auth ผิด
> ที่จะได้ 401) — แปลว่าปัญหาอยู่ที่ layer network/service ไม่ใช่ credential

**วิธีแก้:** re-apply NodePort (หรือ setup ครั้งแรกให้รวม flag นี้ไปเลยตามส่วนที่ 1.1)
```bash
helm upgrade --namespace $NAMESPACE $RELEASE_NAME skypilot/skypilot \
  --version 0.12.3+post.1 \
  --reuse-values \
  --set ingress-nginx.controller.service.type=NodePort \
  --set ingress-nginx.controller.service.nodePorts.http=30080
```
เช็คว่า TYPE เปลี่ยนเป็น `NodePort` + PORT(S) เห็น `80:30080/TCP` แล้ว curl ซ้ำ

---

### ปัญหา #4 — sky launch ล้มเหลว: "didn't match Pod's node affinity/selector" ยังไม่ปิดจบ

**อาการ:** สั่ง `sky launch --cpus 2 --memory 2` (ขอแค่ CPU ไม่ได้ขอ GPU) แต่ได้:
```
⨯ Cluster does not have sufficient GPUs for your request
Pod status: Pending Details: '0/1 nodes are available:
  1 node(s) didn't match Pod's node affinity/selector.'
```

**จุดที่ทำให้งง:** error พูดเรื่อง **GPU** ทั้งที่เราขอแค่ CPU — อันนี้เป็น generic message ของ SkyPilot
สาเหตุจริงอยู่ที่บรรทัด `didn't match Pod's node affinity/selector` = pod ที่ SkyPilot จะ launch
มี nodeAffinity/nodeSelector ที่ node `thinkpad` ไม่ match

**สิ่งที่ตัดออกไปแล้ว (ไม่ใช่สาเหตุ):**
- ❌ Taint — node เป็น `Taints: <none>` และ `Unschedulable: false`
- ❌ Arch — node เป็น `amd64` + `linux` ปกติ

**สิ่งที่ยังต้องเช็ค (diagnostic ที่ค้างอยู่):** ปัญหานี้ต้องดู affinity ที่ pod ขอจริง ซึ่งต้อง**จับ pod
ตอนมันยัง Pending** (มันหายเร็วหลัง launch fail):

```bash
# 1) launch ทิ้งไว้ background
sky launch --cpus 2 --memory 2 -y -- echo "test" &

# 2) รีบจับ pod ตอน Pending (job pod มักอยู่ namespace default ไม่ใช่ skypilot)
kubectl get pods -A | grep sky-
kubectl describe pod -n <ns> <sky-pod> | grep -A 25 "Node-Selectors:\|Node-Affinity:\|Events:"

# 3) เช็ค resource ที่ node เหลือ (เผื่อ error หลอก จริงๆ คือ CPU/mem ไม่พอ)
kubectl describe node thinkpad | grep -A 8  "Allocatable:"
kubectl describe node thinkpad | grep -A 10 "Allocated resources:"

# 4) เช็ค k8s context ฝั่ง sky
sky check kubernetes
sky show-gpus --infra kubernetes
```

**2 สมมติฐานที่ต้องแยก:**
- **affinity mismatch จริง** → ดู pod yaml ว่าขอ label อะไรที่ node ไม่มี แล้ว label ให้ node
  (`kubectl label node thinkpad <key>=<value>`) หรือปรับ config ฝั่ง sky
- **resource ไม่พอ** → error หลอก จริงๆ คือ allocatable CPU/mem บน ThinkPad เหลือไม่ถึง `cpus=2,mem=2`
  → ลองลดเป็น `--cpus 1 --memory 1` ดูว่าผ่านไหม

> เมื่อได้ output ของ describe pod (ส่วน Node-Selectors/Affinity/Events) จะฟันธงได้ว่าเป็นสาเหตุไหน

---

## ส่วนที่ 3: Checklist ตอนอัปเกรดเวอร์ชัน SkyPilot

ทำตามนี้ทุกครั้งที่จะเปลี่ยนเวอร์ชัน (กันลืม + กัน client/server หลุด sync):

1. **หาเลข stable ล่าสุด:** `helm search repo skypilot/skypilot --versions` (เอาตัวไม่มี rc/dev)
2. **Diff ค่าคงที่** ใน `sky/skylet/constants.py` ของเวอร์ชันใหม่เทียบของเดิมที่ bake ไว้
   (`SKY_REMOTE_RAY_VERSION`, python version, conda/uv path ฯลฯ — ส่วนใหญ่ไม่เปลี่ยน แต่ต้องเช็ค)
3. **แก้ทั้ง 2 ฝั่งพร้อมกัน** (client pip + server helm) ให้เลขตรงกัน
4. **`sky launch` จริง 1 ครั้ง** เพื่อ trigger wheel build ใหม่
5. **หา wheel hash ใหม่** — ถ้าใช้ remote API server การแพ็ก wheel เกิดใน **pod** ไม่ใช่เครื่อง client:
   ```bash
   kubectl exec -n skypilot deploy/skypilot-api-server -c skypilot-api -- sh -c 'ls -la ~/.sky/wheels/'
   ```
   แล้ว `kubectl cp` ไฟล์ `.whl` ออกมา bake
6. **เช็ค SSH user จริง** (path `$HOME/...` ที่ bake ต้องอยู่ใต้ user นี้ — เคสนี้เจอ `User sky` ไม่ใช่ root):
   ```bash
   cat ~/.sky/generated/ssh/<ชื่อ-cluster>
   ```

---

## Quick reference — คำสั่งเช็คสถานะที่ใช้บ่อย

```bash
# สถานะ pod/service
kubectl get pods -n skypilot
kubectl get svc  -n skypilot

# ทำไม pod ไม่ยอมขึ้น
kubectl describe pod -n skypilot -l app=skypilot-api | grep -A 20 "Events:"

# หา node IP จริง
kubectl get nodes -o wide

# health check server
curl http://admin:admin123@<NODE_IP>:30080/api/health

# สถานะ sky
sky check kubernetes
sky status --refresh
```
