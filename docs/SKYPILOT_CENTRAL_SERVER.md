# ใช้ SkyPilot กลาง (skypilot.bell-lab.space) แทน SkyPilot ในเครื่อง backend

สถานะ: **Pete อนุมัติ (เลือกทาง A) และทำแล้ว** 2026-10-17 บน branch `feature/skypilot-central` — ผลดูหัวข้อ 6

## 1. สถานะตอนนี้ (แก้มือบน cluster ที่บ้าน 2026-10-17)

| อะไร | ค่าตอนนี้ | อยู่ใน Ansible แล้วไหม |
|---|---|---|
| helm `skypilot-api` (rev 9) | `enableUserManagement: true`, `initialBasicAuthSecret: skypilot-initial-basic-auth` | ❌ |
| | `storage.enabled: true` (PVC local-path 10Gi) | ❌ (role ปิด storage) |
| | `apiService.nodeSelector: kubernetes.io/hostname=master` | ❌ |
| | `apiService.config`: `kubernetes.ports: podip` (+ ไฟล์บน PVC) | ❌ |
| secret admin | `skypilot-initial-basic-auth` (ns `skypilot`) รหัสใน `ansible/artifacts/skypilot-admin` | ❌ |
| token ของ backend | service account `vlab-backend` ใน `ansible/artifacts/skypilot-backend-token.json` | ❌ |
| CoreDNS | ConfigMap `kube-system/coredns-custom` key `no-aaaa.override` (ตอบ AAAA ว่าง) | ❌ |
| backend (dev, ThinkPad) | `uvicorn --env-file .env.skypilot` | – |

ผลทดสอบ: launch ผ่าน `/api/sessions` สำเร็จ 4/4 (ประมาณ 3–6 นาที) ทุกรอบลง thinkpad

### ทำไมต้องแก้ CoreDNS
pod ทุกตัวใน cluster ไม่มี IPv6 (flannel ตั้งไว้แค่ IPv4) แต่ DNS ตอบที่อยู่ IPv6 (AAAA) ของ
`files.pythonhosted.org` กลับมาด้วย ถ้า `uv` ที่ SkyPilot ใช้ลง runtime เลือกที่อยู่ IPv6 จะได้
`Network is unreachable (os error 101)` → `runtime-setup failed` → pod กลายเป็น Failed
ทดสอบแล้ว: thinkpad และ worker-pete ไปทาง IPv4 ได้ 15/15 ครั้ง ทาง IPv6 ได้ 0/15 ครั้ง
Corefile เดิมเป็นค่าเริ่มต้นของ k3s ไม่มีใครเคยแก้ ไม่ได้เกิดจากการตั้งค่าของเรา

## 2. ปัญหาที่เจอ (ต้องแก้ก่อนใช้จริง)

1. **การกันเครื่องอื่นเปิด lab (LAB_ISOLATION) ไม่ทำงานกับ lab ที่เปิดผ่าน server กลาง**
   server กลางสร้าง pod ใน namespace `skypilot` (ns ของ helm) แต่ NetworkPolicy
   `vlab-lab-isolation` อยู่ใน ns `default` เท่านั้น → pod lab ที่มี label `vlab/lab=true`
   ใน ns `skypilot` ไม่ได้ถูกปิดขาเข้า เครื่องข้าง ๆ เปิดผ่าน pod IP ได้
   (ตอนใช้ SkyPilot ในเครื่อง pod ลง ns `default` จึงไม่เจอปัญหา)
   warm pod (สร้างตรงด้วย kubernetes client ลง `default`) ไม่กระทบ
2. **ใส่ `SKYPILOT_*` ใน `.env` ไม่ได้** — `Settings` ห้าม key ที่ไม่รู้จัก (extra=forbid) backend จะ crash
   ตอนนี้จึงต้องแยกไว้ใน `.env.skypilot` แล้วเปิดด้วย `--env-file`
3. **role `skypilot-node` จะทับค่าที่แก้มือทั้งหมด** ถ้ารัน playbook อีกครั้ง (ปิด storage, ไม่มี auth,
   ไม่มี nodeSelector / podip) และ `-e skypilot_reset=true` จะลบทั้ง namespace รวมถึง PVC
4. **role `web-portal` ยังใช้ SkyPilot ใน container ของ backend** (เช็กด้วย `sky check kubernetes`
   ผ่าน kubeconfig) ไม่มี endpoint / token ของ server กลาง
5. **CoreDNS fix กับ NetworkPolicy ไม่ได้อยู่ใน Ansible** — ตั้ง cluster ใหม่แล้วจะพังแบบเดิม

## 3. แผนแก้ (เรียงตามลำดับที่จะทำ)

### 3.1 ตัดสินใจเรื่อง namespace (ต้องให้ Pete เลือก)

| ทาง | ทำอะไร | ข้อดี | ข้อเสีย |
|---|---|---|---|
| **A (แนะนำ)** | apply `vlab-lab-isolation` ลง ns `skypilot` เพิ่มอีกชุด | เปลี่ยนน้อย ไม่แตะ RBAC ของ helm | lab อยู่คนละ ns กับ warm pod |
| B | ตั้ง helm `kubernetesCredentials.inclusterNamespace: default` ให้ lab กลับไปอยู่ `default` | ทุกอย่างอยู่ ns เดียวเหมือนเดิม | ต้องให้ service account ของ helm มีสิทธิ์ใน `default` (`rbac.grantedNamespaces`) ต้องทดลองเพิ่ม |

### 3.2 Ansible role `skypilot-node` (master)
- values file: `storage.enabled: true`, `apiService.enableUserManagement: true`,
  `apiService.initialBasicAuthSecret: skypilot-initial-basic-auth`,
  `apiService.nodeSelector: {kubernetes.io/hostname: <master>}`,
  `apiService.config: "kubernetes:\n  ports: podip"`
- ลบ `--set storage.enabled=false` ที่ทับค่าใน values ออก และไม่ใช้ `--wait` นาน 10 นาที
  (เปลี่ยนเป็น apply แล้วค่อยเช็ก health)
- task สร้าง secret admin จาก `vault_skypilot_admin_password` (htpasswd apr1) เฉพาะตอนที่ยังไม่มี secret
- `skypilot_reset=true`: เตือนชัดว่าจะลบ PVC (user, token, config) ด้วย
- หมายเหตุ: config ใน ConfigMap จะถูก copy ลง PVC **เฉพาะตอนที่ไฟล์บน PVC ว่าง** ถ้าจะแก้ config ทีหลัง
  ต้องเขียนไฟล์ใน pod (หรือแก้ผ่าน dashboard) แล้ว restart

### 3.3 Ansible: cluster-wide (role `k3s-server`)
- apply `kube-system/coredns-custom` (`no-aaaa.override`)
- apply `k8s/lab-isolation-networkpolicy.yaml` ลง `default` (+ `skypilot` ถ้าเลือกทาง A)

### 3.4 Backend (โค้ด)
- เพิ่ม field ใน `Settings`: `SKYPILOT_API_SERVER_ENDPOINT: str | None`, `SKYPILOT_SERVICE_ACCOUNT_TOKEN: str | None`
- ตอน start app ถ้ามีค่า → ใส่ลง `os.environ` ให้ sky SDK เห็น (ไม่ต้องใช้ `--env-file` แล้ว ใส่ใน `.env` ได้ตรง ๆ)
- ไม่ตั้ง = ใช้ SkyPilot ในเครื่องเหมือนเดิม (dev ที่ไม่มีเน็ตไป server กลางยังทำงานได้)
- log ตอน start ว่าใช้ server ไหน (ไม่ log token)

### 3.5 Ansible role `web-portal`
- `backend.env.j2`: เพิ่ม `SKYPILOT_API_SERVER_ENDPOINT=https://{{ skypilot_domain }}` และ
  `SKYPILOT_SERVICE_ACCOUNT_TOKEN={{ vault_skypilot_backend_token }}`
- เปลี่ยน `sky check kubernetes` เป็น `sky api info` (ต้องเห็น endpoint ของ server กลาง + user `vlab-backend`)
- kubeconfig ยังต้องมี (warm pod / prewarm / หา node จาก IP คุยกับ K3s ตรง)
- token สร้างครั้งแรกจาก dashboard แล้วเก็บใน vault (token แสดงครั้งเดียว Ansible สร้างเองไม่ได้ง่าย ๆ)

### 3.6 Secrets
- `group_vars/all.yml` (vault): `vault_skypilot_admin_password`, `vault_skypilot_backend_token`
- ลบไฟล์ใน `ansible/artifacts/` หลังย้ายเข้า vault แล้ว

## 4. ทดสอบหลังแก้

| เทส | คาดหวัง |
|---|---|
| ไม่มีรหัส → `/dashboard/` | 401 |
| backend `sky api info` | endpoint `https://skypilot.bell-lab.space`, user `vlab-backend` |
| `/api/sessions` 3 รอบติด | สำเร็จทุกรอบ ไม่มี `Network is unreachable` |
| กด Start จากเครื่อง worker (pin_node) | pod ลงเครื่องนั้น มี label `vlab/lab=true` |
| เครื่องอื่นเปิด pod IP ของ lab | เปิดไม่ได้ (NetworkPolicy) |
| เครื่องเดียวกันเปิด pod IP ของ lab | เปิดได้ |
| restart pod API server | token / user ยังใช้ได้ |
| รัน playbook ซ้ำ | ค่าข้างบนไม่ถูกทับ |

## 5. ถอยกลับ
- backend: ไม่ตั้ง `SKYPILOT_*` = กลับไปใช้ SkyPilot ในเครื่อง
- helm: `helm rollback skypilot-api 6` (ไม่มี auth / storage)
- CoreDNS: `kubectl delete cm coredns-custom -n kube-system && kubectl rollout restart deploy/coredns -n kube-system`

## 6. ผลหลังทำ (2026-10-17 เย็น)

| เทส | ผล |
|---|---|
| NetworkPolicy ใน ns `skypilot` (ทาง A) | ✅ pod label `vlab/lab=true` บน thinkpad: thinkpad เปิดได้ / master เปิดไม่ได้ · pod ไม่มี label: เปิดได้ทั้งคู่ · API server ยัง 200 |
| backend อ่าน `SKYPILOT_*` จาก `.env` (ไม่ใช้ `--env-file`) | ✅ log `SkyPilot API server: ... (token: yes)` |
| เทส backend ทั้งหมด | ✅ 137/137 (แก้ `tests/conftest.py` ให้ทุกเทสใช้ค่า default ของ Settings ไม่อ่าน `.env` ของเครื่อง dev — เดิม warm pod 2 ตัว fail เพราะ `.env` ตั้ง `LAB_ISOLATION_ENABLED=true`) |
| launch ผ่าน `/api/sessions` + ลบ | ✅ 325s, IDE 302, ลบสะอาด (รวมทั้งวัน 5/5 หลังแก้ CoreDNS) |
| `ansible-playbook --syntax-check` | ✅ |
| render manifest ของ role + `kubectl apply --dry-run=server` | ✅ NetworkPolicy spec ตรงกับของจริง, coredns-custom unchanged |
| รัน playbook จริงกับ cluster | ⏳ ยังไม่ได้รัน (role skypilot-node จะ `helm upgrade` ด้วย values ใหม่) |
| กด Start จากเครื่อง worker จริง (pin_node + label) | ✅ ดูหัวข้อ 7 |

## 7. ย้าย endpoint ของ backend ออกจาก Cloudflare + เทส Start จากเครื่องแลป (2026-10-17 ค่ำ)

### ปัญหา
เทส Start จาก worker-pete ได้ `Could not connect to SkyPilot API server` (ลบ session ก็เจอ) ทั้งที่ server ปกติ
sky SDK เช็ก `/api/health` ด้วย timeout 2.5s และไม่ retry เมื่อ ConnectionError วัดแล้ว:

| เส้นทาง | min | median | max |
|---|---|---|---|
| ตรงเข้า ClusterIP (จาก master) | 0.006s | 0.007s | 0.011s |
| `https://skypilot.bell-lab.space` (Cloudflare tunnel) | 0.07s | 0.34s | **2.1s** |
| NodePort 30880 ผ่าน Tailscale (หลังแก้) | 0.010s | 0.029s | 0.17s |

### แก้
- `k8s/skypilot-api-tailnet-service.yaml`: Service NodePort 30880 → pod API server ตัวเดิม (chart ล็อก Service เป็น ClusterIP)
  role skypilot-node apply ให้ ยังต้องใช้ token / รหัสเหมือนเดิม (ไม่มีรหัส = 401)
- backend: `SKYPILOT_API_SERVER_ENDPOINT=http://<master Tailscale IP>:30880` (role web-portal ตั้งเป็นค่าเริ่มต้น)
- Tailscale ACL ไม่ต้องแก้: worker เข้า master ได้แค่ 6443/8000/5173/80/443 → เข้า 30880 ไม่ได้
  เครื่องที่รัน backend ต้องติด `tag:vlab-server`
- dashboard สำหรับคนยังเข้าทาง Cloudflare ได้ตามเดิม

### บั๊กที่เจอระหว่างเทส (มีอยู่ก่อน)
`create_session` เช็ก session เดิมด้วย `sky.status` ถ้าเรียกไม่ได้จะเดาว่า cluster หยุดแล้ว → ตั้ง STOPPED แล้ว launch ต่อ
cluster เดิมไม่ถูก down (ลบ session ทีหลังก็ข้ามเพราะเห็น STOPPED) ค้างจน autostop 1 ชม. และเปิดซ้อนได้
แก้: ตอบ `ClusterOperationError` ("please try again") ไม่แตะ session เดิม ไม่ launch + เทส regression

### ผลเทส Start จากเครื่องแลป (จำลองด้วย IP ของเครื่อง: thinkpad ยิงผ่าน Tailscale IP,
worker-pete ใช้ pod hostNetwork บน worker-pete ยิงหา backend)

| เทส | ผล |
|---|---|
| A. Start จาก thinkpad | ✅ pod ลง thinkpad, label `vlab/lab=true`, nodeSelector thinkpad (243s) |
| B. Start จาก worker-pete | ✅ pod ลง worker-pete, label + nodeSelector worker-pete |
| lab ของ thinkpad: thinkpad / master / worker-pete เปิด | ✅ 302,200 / ❌ / ❌ |
| lab ของ worker-pete: worker-pete / thinkpad / master เปิด | ✅ 302,200 / ❌ / ❌ |
| เทส backend ทั้งหมด | ✅ 138/138 (เทสใหม่ fail กับโค้ดเก่า ผ่านกับโค้ดใหม่) |
| launch + ลบ 3 รอบติด ผ่าน NodePort | ✅ 3/3: 151s / 164s / 164s (ผ่าน Cloudflare เดิม 173–325s) IDE 302 ลบแบบ down cluster จริงทุกรอบ |

## 8. เทส 4 เส้นทางด้วย account Sophia (2026-10-19)

ทุกเส้นใช้ SkyPilot กลางบน master (`http://100.125.244.48:30880`) และ lab music-lab (`skypilot/music-lab:lab-01`)
backend รันด้วย `AWS_PROFILE=skypilot` — ไม่ตั้ง boto3 จะใช้ profile default ของ ThinkPad ซึ่งเป็น **root** ตอนขอ ECR token

| เส้นทาง | ผล | เวลา |
|---|---|---|
| 1. prewarm (`PREWARM_TARGETS`, pre-pull อย่างเดียว) | ✅ DaemonSet pull ครบ thinkpad + worker-pete (workerfilm NotReady ไม่นับ) | 1–4s (image มีในเครื่องอยู่แล้ว) |
| 2. K8s ผ่าน SkyPilot (Start จาก worker-pete) | ✅ pod ลง worker-pete + label, pull image 0.3s, worker-pete เปิดได้ / thinkpad, master เปิดไม่ได้ | 230s |
| 3. EC2 ผ่าน SkyPilot (cloud burst) | ✅ `m7i-flex.large` private subnet ไม่มี public IP, role `vlab-lab-ecr-pull`, AMI bake r2, IDE ผ่าน router 302 / 5173 200, ไม่พบ ECR token ใน log, DELETE → terminate | 133s (ลบ 15s) |
| 4. warm pod (class slot ชั่วคราว) | ✅ scheduler สร้าง warm pod 2 เครื่อง, Start จาก worker-pete ได้ `warm_pod`, เปิดได้แค่ `localhost` (IP Tailscale ของเครื่องเอง / เครื่องอื่น / pod IP เปิดไม่ได้) | **1s** |

prewarm ช่วยแค่ pull image ส่วน launch ผ่าน SkyPilot ยังลง runtime (conda / uv / Ray) ใหม่ทุกครั้ง จึงเป็นเวลาส่วนใหญ่
ทางเร็วจริงคือ warm pod (ไม่ผ่าน SkyPilot) หรือ bake runtime ลง image

### สิ่งที่ต้องตั้งเพิ่มให้ EC2 ผ่าน server กลางบน master
| อะไร | ทำยังไง | อยู่ในโค้ดแล้ว |
|---|---|---|
| ECR repo `skypilot/music-lab` + push `lab-01` จาก register | AWS CLI (admin) | `terraform/ecr.tf` (infra branch, ต้อง import) |
| `Skypilot-IAM` pull repo ใหม่ | แก้ inline policy `ecr-pull-lab` | ❌ IAM user สร้างมือ |
| router egress ไป lab 5173 / 8443 (เดิม 8080) | AWS CLI | `terraform/security_groups.tf` (ต้อง import) |
| master รับ Tailscale subnet route | `sudo tailscale set --accept-routes` | role `tailscale` (เฉพาะ master) |
| ค่า `aws:` ใน config ของ server (vpc / internal IP / no SSM / SG / role) | เขียน `/root/.sky/config.yaml` ใน pod แล้ว restart | role `skypilot-node` (`apiService.config`) |
| `awsCredentials.enabled: true` | มีอยู่แล้วใน helm (ตั้งมือ) | role `skypilot-node` |
| `sky check aws` | ผ่าน token → `AWS [compute]` | – |

หมายเหตุ: ConfigMap `skypilot-api-config` ยังมีแค่ `ports: podip` (server ไม่ sync จาก PVC ทันที) ไม่กระทบเพราะ server อ่านจาก PVC
