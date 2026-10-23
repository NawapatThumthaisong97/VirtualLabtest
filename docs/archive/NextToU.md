# NextToU — งานต่อสำหรับ session ถัดไป

เขียน 2026-10-20 ส่งต่อจาก session ที่ทำ SkyPilot กลาง / AUTO / launch-test
**ผู้อ่าน: Claude session ถัดไปที่จะลงมือ** (และ Pete) — อ่านหัวข้อ 0 ก่อนทำอะไรทั้งนั้น

---

## 0. วิธีทำงานกับ Pete (สำคัญกว่าเนื้องาน)

- **ถามก่อนแตะ infra ที่ใช้ร่วม** (helm, k3s, Tailscale, AWS, DB) ทีละขั้น อย่ารวบหลายขั้นในคำสั่งเดียว
- **งานออกแบบใหม่ → เขียน `docs/*.md` ให้รีวิวก่อน** ยังไม่แตก branch / เขียนโค้ดจนกว่าจะอนุมัติ
- **รายงานผลเป็นตาราง ✅ / ❌ / ⏳ ทุกขั้น** ไม่ต้องรอให้ถาม
- **ห้ามนั่งรอนาน** (`helm --wait`, `until` loop บล็อกหน้าจอ) — สั่งแล้วเช็กเป็นช่วง หรือรันเบื้องหลัง
- **ทดสอบกับของจริงที่จะ deploy** ถ้าใช้ตัวแทน (local / mock) ต้องบอกตั้งแต่แรก
- commit **ภาษาไทย** (ศัพท์เทคนิคอังกฤษ) โครง title + why + how **ไม่ใส่ Co-Authored-By**
- อย่า `pkill -f` ด้วย pattern ที่อยู่ในคำสั่งตัวเอง (เคยฆ่า shell ตัวเอง) ใช้ `ps -eo pid,args | awk '/[u]vicorn .../'`
- Pete เครียดง่ายเมื่อของพังต่อกัน — อธิบายสั้น ง่าย บอกตรง ๆ ว่าอะไรรู้แน่ อะไรเดา

---

## 1. เป้าหมายรอบนี้

Pete จะ
1. **ลง master ใหม่** ด้วย Ansible (`k3s-server` + `skypilot-node`) — เทส playbook จากศูนย์ครั้งแรก
2. **ถอน ThinkPad ออกจาก worker** แล้วใช้เป็นเครื่อง web-portal (อาจเป็น **VM บน ThinkPad**) — เทส role `web-service` ครั้งแรก
   (2026-10-20 เปลี่ยนชื่อ role `web-portal` → `web-service`, กลุ่ม inventory `webservice`, ตัวแปร `webservice_*` — โฟลเดอร์แอป `web-portal/` ชื่อเดิม)
3. **AWS ใช้ของเดิมต่อ ไม่ destroy** — แค่ให้ server ตัวใหม่ชี้มาที่ VPC / router / SG / ECR เดิม (หัวข้อ 2.1)

งานของ session ถัดไป: ช่วยลงตามลำดับ แล้ว **เทสทุกเส้นทาง launch ในหัวข้อ 5** ให้ผ่าน

---

## 2. สถานะตอนส่งต่อ (2026-10-20)

### Cluster ที่บ้าน
| เครื่อง | Tailscale IP | บทบาทตอนนี้ | หลังรอบนี้ |
|---|---|---|---|
| master | 100.125.244.48 (SSH `vboxuser@`, sudo ใช้รหัส) | control-plane + SkyPilot API server (helm) | ลงใหม่ |
| thinkpad | 100.93.121.17 | worker + backend dev (uvicorn) | **web-portal** (ไม่ใช่ worker) |
| worker-pete | 100.83.96.97 | worker | worker (เครื่องแลปหลักที่ใช้เทส) |
| workerfilm | 100.97.13.122 | NotReady มานาน | – |
| register | 100.127.74.48:5001 | registry on-prem | เหมือนเดิม |
| **webservice** (VM ใหม่) | **100.102.72.39** (SSH `web@`) | ยังว่าง — ลง Tailscale + openssh แล้ว | **web-portal** (target ของ role `web-service`) |

webservice (เพิ่ม 2026-10-20):
- hostname เครื่อง `webservice` ลง Tailscale ด้วย `--hostname=vlab-web --advertise-tags=tag:vlab-server` (เช็ก tag ว่าติดจริงด้วย `tailscale status --self`)
- **ปิด Tailscale SSH แล้ว** (`tailscale set --ssh=false`) — ถ้าเปิด Tailscale จะดักพอร์ต 22 แล้ว ACL ปฏิเสธเครื่องที่มี tag
  (`tailnet policy does not permit you to SSH to this node`) ใช้ openssh ปกติแทน (`ufw allow OpenSSH` แล้ว)
- ต้องเพิ่ม `100.102.72.39  tag:vlab-server` ใน `tailscale/vlab-tags.tsv` ไม่งั้นรัน `tailscale-acl.sh apply` รอบหน้า tag อาจถูกตั้งไม่ตรง
- อยู่ใน `ansible/inventory.home.yml` กลุ่ม `webservice` host `vlab-web` (ansible_host = 100.102.72.39, ansible_user = web)
- `ssh-copy-id` แล้ว (2026-10-20) Claude SSH ได้

inventory ที่บ้าน: `ansible/inventory.home.yml` (gitignored), secret: `ansible/group_vars/all.yml` (gitignored)

### Branch / PR
| branch | PR | สถานะ |
|---|---|---|
| `feature/lab-isolation` | #93 draft | push แล้ว |
| `feature/skypilot-central` | #94 draft (ต่อ #93) | push แล้ว |
| `feature/launch-test` | ยังไม่มี PR | **commit แล้ว ยังไม่ push** — AUTO, `GET /api/prewarm/schedule`, memory 4Gi, `script/launch-test.sh` |

ทำงานต่อบน `feature/launch-test` (มีทุกอย่างของ #93 / #94 อยู่ข้างใต้)

### สิ่งที่ตั้งมือไว้บน infra เดิม (master ใหม่จะไม่มี — role ต้องสร้างให้ ดูหัวข้อ 3)
- helm `skypilot-api`: auth (user management), storage PVC, nodeSelector master, memory 2Gi/4Gi, `awsCredentials`
- NodePort `skypilot-api-tailnet` 30880 (backend คุยผ่าน Tailscale ไม่ผ่าน Cloudflare)
- CoreDNS `coredns-custom` (ตอบ AAAA ว่าง — cluster ไม่มี IPv6)
- NetworkPolicy `vlab-lab-isolation` ใน ns `default` และ `skypilot`
- master `tailscale set --accept-routes` (SSH เข้า EC2 ใน private subnet)
- `/root/.sky/config.yaml` ใน pod: `ports: podip` + block `aws:` (vpc_names / use_internal_ips / use_ssm: false / SG / role)

### AWS (สร้างด้วย CLI 2026-10-19 — Terraform state ของ VPC นี้หาไม่เจอบนเครื่อง)
- ECR repo `skypilot/music-lab` (มี `lab-01`) + inline policy `ecr-pull-lab` ของ IAM user `Skypilot-IAM` เพิ่ม repo นี้
- SG router `sg-02fd238b646558f30` egress ไป lab `sg-05520129fde94de1e` พอร์ต 5173, 8443 (8080 มีเดิม)
- Terraform มีโค้ดตรงกันแล้วใน worktree `/home/pete/document/VirtualLabtest-infra` (`infra/ecr-pull-experiment`) แต่ **ไม่เคย apply**
  ถ้า Pete จะ apply ใหม่: ต้อง `terraform import` ของที่สร้างด้วย CLI ก่อน (คำสั่งอยู่ใน comment ของ `ecr.tf`, `security_groups.tf`)
  ไม่งั้น apply จะชนกับของที่มีอยู่ — **ถาม Pete ก่อน** ว่าจะ import หรือสร้างใหม่ทั้งชุด
- router `vlab-ts-router` (running, ประกาศ route `10.10.2.0/24`, `10.10.3.0/24`), AMI `ami-0da9046ec7f57f3af` (bake 0.12.3.post1-r2)

### 2.1 AWS: ใช้ของเดิม ไม่ต้อง destroy (Pete ถาม 2026-10-20)

ของบน AWS ไม่ได้ผูกกับเครื่อง master ทุกตัวถูกอ้างด้วยชื่อ / ID ใน config → ลง master ใหม่แล้ว**ชี้มาที่ของเดิม**
| ของ | ผูกกับ master ไหม | หลังลง master ใหม่ |
|---|---|---|
| VPC `vlab-ecr-pull` + subnet `10.10.1-3.0/24` | ❌ | ใช้ต่อ |
| router `vlab-ts-router` (เครื่องใน tailnet ของตัวเอง) | ❌ | ยังประกาศ route `10.10.2.0/24`, `10.10.3.0/24` |
| SG `vlab-lab-instances` / `vlab-ts-router` | ❌ | ใช้ต่อ |
| IAM role `vlab-lab-ecr-pull`, IAM user `Skypilot-IAM` | ❌ | ใช้ต่อ |
| ECR `skypilot/music-lab`, `vlab/music-lab-ide` | ❌ | ใช้ต่อ |
| AMI `ami-0da9046ec7f57f3af` | ❌ | ใช้ต่อ |

master / server ใหม่ต้องมีแค่
1. block `aws:` ใน config ของ server (role `skypilot-node` ใส่ให้)
2. secret `aws-credentials` = key ของ `Skypilot-IAM` (สร้างเอง — ช่องว่าง #2 หัวข้อ 3)
3. `tailscale set --accept-routes` บน master (role `tailscale` ทำให้)
4. backend `.env` ค่าเดิม `AWS_LAB_AMI`, `ECR_REGISTRY_HOST`, `AWS_REGION` ไม่ต้องเปลี่ยน
5. `sky check aws` ผ่าน token → เห็น `aws` ใน Enabled Infra

⚠️ **ก่อนลง master ใหม่ เช็กว่าไม่มี lab บน EC2 รันค้าง** (คำสั่งหัวข้อ 5.3) — server ใหม่จะไม่รู้จัก EC2 ที่ตัวเก่าสร้าง
→ ค้างเสียเงินจนกว่าจะลบด้วยมือ (`aws ec2 terminate-instances --profile skypilot`)

ไม่แนะนำ destroy แล้วสร้างใหม่: router ต้อง login Tailscale + อนุมัติ route ใหม่, VPC / SG ID เปลี่ยน, ต้อง push ECR
และแก้ IAM ใหม่ — ได้ผลเท่าเดิมแต่งานเยอะกว่าและเสี่ยงกว่า
Terraform state หาไม่เจอ = ไม่กระทบการใช้งาน ค่อย `terraform import` ทีหลังถ้าอยากให้ Terraform ดูแล (หัวข้อ 2 AWS)
ของเก่าที่เก็บกวาดได้ภายหลัง (stopped แต่ยังเสียค่า disk): `Tailscale-subnet-router` (อีก VPC), `vlab-test-a`, `vlab-test-b` — ถาม Pete ก่อน

### DB dev (Postgres บน ThinkPad, `virtual_lab`)
- enum `runtarget` มี `AUTO` แล้ว (`ALTER TYPE ... ADD VALUE 'AUTO'` จดใน `docs/archive/DB_DIAGRAM.md`) — **DB ใหม่ต้องรันคำสั่งนี้ด้วย**
- user เทส: Sophia Davis `sophia.dav@dome.tu.ac.th` id `b4f5c004-5dac-4e38-99cb-8382d5982484`
- lab เทส (course SE301, image `skypilot/music-lab:lab-01`, พอร์ต 8080 / 5173 / 8443):
  | lab | id | run_target |
  |---|---|---|
  | OOP with Spring Boot | `03a18386-1558-4bcf-9399-4b79cc1ae22b` | KUBERNETES |
  | OOP with Spring Boot (AWS) | `536989c2-52d1-4169-b23a-ed06247cdb57` | AWS |
  | OOP with Spring Boot (AUTO) | `035a1861-3b1b-4309-8600-22cab0d06439` | AUTO |
  ถ้าย้าย DB ไปเครื่อง web-portal ใหม่ (seed ใหม่) id จะเปลี่ยน → ส่งเป็น env ให้ `launch-test.sh` (`LAB_K8S`, `LAB_AWS`, `LAB_AUTO`, `USER_ID`)

---

## 3. ต้องแก้ก่อนลง (ช่องว่างที่รู้แล้ว — ทำเป็น doc / PR ให้ Pete อนุมัติก่อน)

| # | ช่องว่าง | ทำไมสำคัญ |
|---|---|---|
| 1 | ✅ แก้แล้ว 2026-10-20: role `web-service` render `backend/aws-credentials` (profile `skypilot`) mount เข้า container + ค่า AWS / สวิตช์ใน `.env` | เดิม backend ขอ ECR token ไม่ได้ → lab AWS / AUTO จากข้างนอกพัง ห้ามใช้ root |
| 2 | ✅ แก้แล้ว 2026-10-20: role `skypilot-node` สร้าง secret `aws-credentials` จาก `skypilot_aws_access_key_id/secret_access_key` ใน `group_vars/all.yml` | เดิม master ใหม่จะไม่มี → `sky check aws` ไม่ผ่าน |
| 3 | token `vlab-backend` อยู่ใน PVC | master ใหม่ = PVC ใหม่ → ต้องสร้าง token ใหม่จาก dashboard แล้วใส่ `skypilot_backend_token` ใน `group_vars/all.yml` ก่อนรัน role `web-service` |
| 4 | role `k3s-server` เขียน `registries.yaml` ต่างจากของเดิม → restart k3s | master ใหม่ไม่เป็นไร (ลงครั้งแรก) แค่รู้ไว้ |
| 5 | เครื่อง web-portal ต้องติด `tag:vlab-server` ใน Tailscale | ไม่งั้นเข้าพอร์ต 30880 ของ master ไม่ได้ (ACL) → แก้ `tailscale/vlab-tags.tsv` + `./script/tailscale-acl.sh plan` แล้ว apply (Pete รันเอง ต้องใช้ token) |
| 6 | ThinkPad ไม่ใช่ worker แล้ว | node `thinkpad` ต้องถูกลบออกจาก cluster (`kubectl delete node`, ถอน k3s-agent ด้วย `script/k3s-remove-local.sh` ถ้าใช้ได้) และ `vlab-tags.tsv` ย้าย tag |
| 7 | ConfigMap ของ server ไม่ sync จาก PVC | ถ้าแก้ config server ทีหลัง ต้องเขียน `/root/.sky/config.yaml` ใน pod แล้ว restart (role ใส่ให้ตอน PVC ว่างครั้งแรกเท่านั้น) |

---

## 4. ลำดับลง (ถาม Pete ทีละขั้น)

1. **AWS** — ไม่ต้องลงใหม่ (หัวข้อ 2.1) แค่เช็กว่าไม่มี EC2 ของ lab ค้าง และ router `vlab-ts-router` running
   ถ้า Pete อยากให้ Terraform ดูแล: `terraform import` ของเดิม แล้ว `terraform plan` ต้องไม่มีอะไรจะสร้าง / ลบ ก่อน apply
2. **master ใหม่** — `ansible-playbook -i inventory.home.yml site.yml --limit master -K` (Pete รัน ต้องใส่ sudo)
   - สร้าง secret `aws-credentials` (ช่องว่าง #2) ถ้ายังไม่ได้ทำใน role
   - เข้า dashboard (`https://skypilot.bell-lab.space/dashboard`, admin รหัสใน `group_vars`) สร้าง service account token `vlab-backend`
3. **worker** — ให้ worker-pete join master ใหม่ (`--limit workers`)
4. **ThinkPad → web-portal** (หรือ VM): ถอนออกจาก worker, ติด tag, รัน role `web-portal`
5. รัน `ALTER TYPE runtarget ADD VALUE 'AUTO'` บน DB ใหม่ + seed / สร้าง lab เทส 3 ตัว

---

## 5. เทสหลังลง (ลำดับนี้ รายงานเป็นตาราง)

### 5.1 พื้นฐาน infra
| เทส | วิธี | คาด |
|---|---|---|
| node | `kubectl get nodes` | master + worker-pete Ready (ไม่มี thinkpad) |
| CoreDNS IPv6 | pod ทดสอบ `nslookup -type=AAAA files.pythonhosted.org` | ไม่มีที่อยู่ (ว่าง) |
| NetworkPolicy | `kubectl get networkpolicy -A` | `vlab-lab-isolation` ใน `default` และ `skypilot` |
| SkyPilot auth | `curl https://skypilot.bell-lab.space/dashboard/` ไม่ใส่รหัส / ใส่รหัสผิด / ถูก | 401 / 401 / 200 |
| NodePort | `curl http://100.125.244.48:30880/api/health` (ทุกครั้ง < 0.2s) | 200 |
| memory ของ server | `kubectl exec ... cat /sys/fs/cgroup/memory.max` | 4294967296 |
| config server | `cat /root/.sky/config.yaml` ใน pod | `ports: podip` + block `aws:` |
| AWS | `sky check aws` ผ่าน token (`SKYPILOT_API_SERVER_ENDPOINT` + `SKYPILOT_SERVICE_ACCOUNT_TOKEN`) | `Enabled Infra: kubernetes/in-cluster, aws` |
| master route ไป AWS | บน master `ip route get 10.10.2.10` | `dev tailscale0` |
| web-portal | role จบด้วย `sky api info` ใน container | endpoint 30880 + user `vlab-backend` HEALTHY |

### 5.2 เส้นทาง launch — ใช้ `script/vlab-tui.py` (TUI รันทั้งชุด ดู docs/archive/TEST_ALL.md) หรือ `script/launch-test.sh` (curl + jq ทีละข้อ)
IP ที่ backend เห็น = เครื่องที่รัน script → **เทสเครื่องแลป ต้องรัน script บน worker-pete** (copy ไฟล์ไป
ตั้ง `BACKEND_URL=http://<Tailscale IP ของเครื่อง web-portal>:8000`) หรือใช้ pod `hostNetwork` บน worker-pete ยิง curl
เทสข้างนอก = รันบนเครื่องที่ไม่ใช่ node (เครื่อง web-portal เอง / laptop ใน tailnet)

| # | เทส | ยิงจาก | เมนู | คาด |
|---|---|---|---|---|
| 1 | prewarm | – | เมนู 7 + สร้างคาบเรียนใกล้ ๆ ใน DB (note ขึ้นต้น `[test]`) | คาบ SCHEDULED → PREWARMING → READY, DaemonSet `prewarm-...` pull ครบ |
| 2 | **warm pod** | worker-pete (มีคาบอยู่) | 3 (AUTO) หรือ 1 (K8s) | `mode: warm_pod` ~1s, endpoint `localhost`, เปิดได้แค่บน worker-pete |
| 3 | K8s ผ่าน SkyPilot | worker-pete (ไม่มีคาบ / ไม่มี warm pod) | 1 | pod ลง worker-pete + label `vlab/lab=true`, ~2–4 นาที |
| 4 | isolation | – | – | lab ของ worker-pete: worker-pete เปิดได้ / master + เครื่อง web-portal เปิดไม่ได้ |
| 5 | AWS (burst) | ที่ไหนก็ได้ | 2 | `target: aws`, EC2 private subnet ไม่มี public IP, IDE 8443 ผ่าน router (จากเครื่องที่อยู่ใน tailnet) ~2 นาที |
| 6 | **AUTO จากเครื่องแลป** | worker-pete | 3 | `target: kubernetes` (warm pod หรือ pin) log backend `[auto] Start from lab machine worker-pete -> kubernetes` |
| 7 | **AUTO จากข้างนอก** | เครื่อง web-portal / laptop | 3 | `target: aws` log `[auto] Start from outside (...) -> aws` |
| 8 | terminate | – | 6 | ลบได้ทุกแบบ, EC2 terminate จริง, ไม่มี pod / EC2 ค้าง |
| 9 | ECR token ไม่หลุด | – | – | grep log backend / `sky logs` หา `eyJwYXlsb2Fk` (รูปแบบ ECR token) ไม่เจอ |
| 10 | โหลดซ้ำ | – | launch + terminate 3 รอบติดต่อแบบ | ผ่านทุกรอบ, server restart 0 (`kubectl get pod ... restartCount`) |

ระหว่างเทส launch ให้เก็บ memory ของ server (`kubectl top pod -n skypilot` ทุก 10s) — เคยชน 2Gi จนพังทั้งวัน

### 5.3 ตรวจไม่ให้มีของค้าง (ทำหลังทุกเทสที่พัง)
```bash
kubectl get pods -n skypilot | grep music                       # pod lab ค้าง
aws ec2 describe-instances --profile skypilot --region ap-southeast-1 \
  --filters Name=tag-key,Values=skypilot-cluster-name Name=instance-state-name,Values=pending,running \
  --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`skypilot-cluster-name`]|[0].Value]' --output text
```
launch ที่พังหลังสร้างเครื่องแล้ว **ทิ้ง EC2 ค้าง (เสียเงิน)** — down ด้วย `sky down <cluster>` ผ่าน token
ถ้า server ไม่ตอบ → `aws ec2 terminate-instances --profile skypilot` (ห้ามใช้ profile default = root)

---

## 6. ปัญหาที่เคยเจอ → ดูตรงนี้ก่อน

| อาการ | สาเหตุ | แก้ |
|---|---|---|
| setup พัง `Network is unreachable (os error 101)` ตอน `uv pip install` | pod ไม่มี IPv6 แต่ DNS ตอบ AAAA | CoreDNS `coredns-custom` (role `k3s-server`) |
| `Could not connect to SkyPilot API server` / `Connection refused` | server หน่วยความจำเต็ม (limit 2Gi) หรือทาง Cloudflare ช้า | memory 2Gi/4Gi, backend ใช้ NodePort 30880 ไม่ใช่ `https://skypilot.bell-lab.space` |
| container `skypilot-api` OOMKilled | เหมือนข้างบน | `kubectl get pod ... lastState.terminated.reason`, `cat /sys/fs/cgroup/memory.events` |
| launch EC2 ค้างตอน SSH | master ไม่รับ subnet route | `tailscale set --accept-routes` บน master |
| EC2 สร้างใน VPC ผิด / ใช้ SSM | config `aws:` ไม่มีใน server | หัวข้อ 2 (block `aws:`) |
| docker pull บน EC2 ไม่ได้ | ECR ไม่มี image / IAM ไม่ให้ pull repo | ECR repo ชื่อเดียวกับ `lab_images.repository` + `ecr-pull-lab` |
| IDE 8443 / 5173 บน EC2 เปิดไม่ได้ (8080 ได้) | SG router ไม่มี egress พอร์ตนั้น | หัวข้อ 2 (AWS) |
| ขอ ECR token ด้วย root | backend ไม่ได้ตั้ง `AWS_PROFILE=skypilot` | ช่องว่าง #1 |
| เปิด session ไม่ได้ 409 ค้าง | session RUNNING ไม่มี cluster (seed) | `DELETE /api/sessions/{id}` |
| เทส backend fail ตาม `.env` ของเครื่อง | — | แก้แล้ว: `tests/conftest.py` ใช้ค่า default ทุกเทส (ปัจจุบัน 161/161) |

---

## 7. นอกขอบเขตรอบนี้ (อย่าเริ่มเองถ้า Pete ไม่สั่ง)
- Cloudflare + gateway ให้คนไม่มี Tailscale เข้าหน้าเว็บ / IDE — **Pete ทำเอง**
  (เมื่อมี: backend ต้องอ่าน IP จริงจาก `CF-Connecting-IP` เฉพาะ request จาก tunnel ไม่งั้น AUTO มองทุกคนเป็นข้างนอก)
- fallback K8s เต็ม → AWS อัตโนมัติ (`ordered` resources)
- อัป SkyPilot จาก 0.12.3.post1 (ล็อกไว้ 5 จุด: requirement.txt, helm chart, AMI, image bake, script/docker-init.sh — ต้องอัปพร้อมกัน)

## 8. เอกสารที่เกี่ยวข้อง
`docs/archive/SKYPILOT_CENTRAL_SERVER.md` (ทั้งหมดเรื่อง server กลาง หัวข้อ 6–9), `docs/archive/RUN_TARGET_AUTO.md`, `docs/archive/LAUNCH_CONSOLE.md`,
`docs/archive/DaemonSetsExperiment.md` (prewarm / warm pod / isolation Exp1–4), `docs/archive/AWS_LAB_FLOW.md`, `docs/archive/EXPERIMENT_ECR_PULL_RESULT.md`

## 9. ผลลง master ใหม่ + เทส (2026-10-20 ค่ำ)

ลงจากศูนย์ด้วย playbook ครบ: master (ล้าง k3s แล้วลงใหม่), worker-pete (join ใหม่), webservice `vlab-web` (role `web-service` + DB ใหม่ seed)
ThinkPad ไม่ใช่ worker แล้ว (เป็นแค่เครื่องสั่งงาน ยัง `tag:vlab-server`) token `vlab-backend` สร้างผ่าน API (`POST /users/service-account-tokens`)
id ใหม่: Sophia `e9f0dd47-8b09-4056-b339-3df0772190e6` (ส่ง `USER_ID=` ให้ launch-test.sh) lab K8s / AWS / AUTO ใช้ id เดิม
DB ใหม่: enum `runtarget` มี `AUTO` จาก create_all แล้ว ไม่ต้อง `ALTER TYPE` แต่ต้องสร้าง lab AWS / AUTO เอง (seed มีแค่ K8s) และลบ session ปลอม RUNNING ของ seed

| เทส | ผล |
|---|---|
| 5.1 infra ทุกข้อ (node, AAAA, NetworkPolicy, auth ผ่าน NodePort 401/401/200, memory 4Gi, config, `sky check` AWS+K8s, route, `sky api info`) | ✅ |
| dashboard ผ่าน Cloudflare | ❌ 530 — `cloudflare_tunnel_token` ใน group_vars เป็น tunnel ที่ไม่มีแล้ว (Pete ต้องเอา token ใหม่) |
| 1 prewarm / 2 warm pod / 6 AUTO จากเครื่องแลป | ✅ warm pod 0s, localhost เปิดได้แค่บน worker-pete |
| 3 K8s ผ่าน SkyPilot / 4 isolation | ✅ 374s (รอบแรก pull image ใหม่) |
| 5 AWS / 7 AUTO จากข้างนอก | ✅ 127s / 94s (ครั้งแรกพังทั้งคู่ ดูข้างล่าง) |
| 8 terminate ทุกแบบ / 9 ECR token ใน log | ✅ (⚠️ token อยู่ใน task YAML บน PVC ของ server `~/.sky/api_server/clients/*/tasks/`) |
| 10 โหลดซ้ำ 3 รอบ | ✅ 354 / 213 / 191s, restart 0, memory สูงสุด 2337Mi |

เจอระหว่างลงจากศูนย์ (แก้แล้วใน role):
- cloudflared:latest ไม่ถอยจาก QUIC ไป http2 เอง → `--protocol http2`
- webservice Ubuntu 26.04 ใช้ `sudo-rs` ansible รอ prompt ไม่เจอ → inventory `ansible_become_exe: sudo.ws`
- นาฬิกา webservice ช้า 5 นาที → EC2 ตอบ `AuthFailure` (STS ผ่าน) → role `common` step เวลาด้วย chrony + เช็ก sync

ยังเปิดอยู่:
- **webservice เป็น VirtualBox VM บน ThinkPad** vCPU ถูกหยุดนานสุด 41s (`clocksource: Long readout interval` ใน dmesg) → นาฬิกาเพี้ยน
  + request ไป master หลุดเป็นพัก ๆ (AUTO รอบแรกพังหลัง launch เสร็จ แล้ว `_down_quietly` ก็หลุด → **EC2 ค้าง** ลบมือแล้ว)
  ทางแก้: ลดโหลด / RAM ของ ThinkPad หรือย้าย VM ไปเครื่องอื่น, และ backend ควร retry `_wait_job_running` / `_down_quietly` (ยังไม่ทำ — ต้อง doc ก่อน)
