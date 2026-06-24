# VirtualLab — POC Core

> **Focus:** พิสูจน์ concept ว่า on-prem K3s + SkyPilot + AWS Spot + Tailscale ทำงานร่วมกันได้จริง  
> **ไม่มี:** Frontend, Backend API, Database  
> **Production version** ถูก save ไว้บน GitHub branch `production` แล้ว

---

## 🎯 Core Concept ที่ต้องพิสูจน์

```
Job submitted
      │
      ▼
SkyPilot ประเมิน K3s capacity
      │
      ├── K3s ว่าง? ──── YES ──► 🏠 Branch A: รันบน on-prem K3s worker
      │                                (เร็ว ไม่เสียค่า cloud)
      │
      └── K3s เต็ม? ──── YES ──► ☁️  Branch B: Burst ไป AWS EC2 Spot
                                      (ผ่าน Tailscale → t4g.nano → private subnet)
```

**ข้อกำหนดหลัก:**
- Spot worker ต้องไม่มี Public IP
- S3 เข้าถึงผ่าน VPC Gateway Endpoint (ไม่ผ่าน internet)
- SSH เข้า Spot worker ผ่าน Tailscale → t4g.nano → private IP
- ไม่มี credential hardcode ใดๆ

---

## 📁 โครงสร้าง

```
VirtualLabtest/
│
├── credentials.env.example    ← template (safe to commit)
├── credentials.env            ← ค่าจริง (อยู่ใน .gitignore)
│
├── 01-terraform/              ← AWS Infrastructure
│   ├── vpc.tf                 ← VPC, subnets, NAT GW, Security Groups
│   ├── tailscale_gateway.tf   ← t4g.nano ASG (always-on Tailscale router)
│   ├── iam.tf                 ← IAM user + minimum permissions for SkyPilot
│   ├── s3_endpoint.tf         ← VPC S3 Gateway Endpoint
│   ├── outputs.tf             ← Outputs: subnet IDs, SG IDs
│   └── variables.tf
│
├── 02-k3s/                    ← On-Prem K3s Setup
│   ├── install-master.sh      ← ติดตั้ง K3s master + แสดง join command
│   ├── install-worker.sh      ← Join worker node เข้า cluster
│   └── install-tailscale-host.sh  ← ติดตั้ง Tailscale บน host
│
├── 03-skypilot/               ← SkyPilot Configuration & Tasks
│   ├── setup-skypilot.sh      ← Install SkyPilot + write ~/.sky/config.yaml
│   ├── task-k3s-test.yaml     ← Test A: Force K3s only
│   ├── task-aws-burst.yaml    ← Test B: Force AWS Spot only + constraint validation
│   └── task-2tier.yaml        ← Test C: 2-tier auto routing (THE MAIN POC)
│
└── 04-validate/               ← Validation Scripts
    ├── validate-all.sh        ← รัน test ทุกอย่างทีเดียว
    ├── test-tailscale.sh      ← Tailscale connectivity
    └── test-k3s-sky.sh        ← K3s nodes + sky check
```

---

## 🚀 ขั้นตอน (ทำตามลำดับ)

### Prerequisites

รันทุกอย่างใน **WSL (Ubuntu)** หรือ Linux โดยตรง  
SkyPilot ไม่รองรับ Windows native

```bash
# ติดตั้ง tools ที่จำเป็น
sudo apt update && sudo apt install -y curl python3 python3-venv awscli
# terraform: https://developer.hashicorp.com/terraform/install
# kubectl: https://kubernetes.io/docs/tasks/tools/
```

---

### Step 1 — ตั้งค่า Credentials

```bash
cp credentials.env.example credentials.env
nano credentials.env   # แก้ค่า REPLACE_ME ทุกช่อง

# โหลดค่าเข้า shell (ต้องทำทุกครั้งที่เปิด terminal ใหม่)
source credentials.env
```

---

### Step 2 — Deploy AWS Infrastructure (Terraform)

```bash
cd 01-terraform

terraform init
terraform plan    # ดูแผนก่อน
terraform apply   # สร้าง VPC, NAT GW, Tailscale t4g.nano, IAM, S3

# ดู outputs ที่สำคัญ
terraform output
```

**สิ่งที่ Terraform สร้าง:**
| Resource | หน้าที่ |
|:---------|:--------|
| VPC `10.0.0.0/16` | Network หลัก |
| Public Subnet `10.0.1.0/24` | NAT GW + t4g.nano |
| Private Subnet `10.0.2.0/24` | EC2 Spot workers (no public IP) |
| NAT Gateway | Spot workers → internet (Docker pull) |
| t4g.nano ASG (1:1) | Tailscale Subnet Router — always-on |
| S3 VPC Gateway Endpoint | Spot workers → S3 (ไม่ผ่าน internet) |
| IAM User `virtuallab-skypilot` | SkyPilot credentials (minimum permissions) |

---

### Step 3 — ติดตั้ง K3s On-Prem

```bash
# บน Master node (on-prem machine)
bash 02-k3s/install-master.sh
# → script จะแสดง K3S_NODE_TOKEN และ join command

# บันทึก token ใน credentials.env:
# K3S_MASTER_IP=192.168.x.x
# K3S_NODE_TOKEN=K10...

# บน Worker node แต่ละตัว (source credentials.env ก่อน)
source credentials.env
bash 02-k3s/install-worker.sh

# ยืนยัน nodes
kubectl get nodes -o wide
```

---

### Step 4 — ติดตั้ง Tailscale (บน K3s master host)

```bash
# สร้าง Auth Key ก่อน:
# https://login.tailscale.com/admin/settings/keys
# ✅ Reusable ✅ Ephemeral + tag: tag:virtuallab-gateway
# บันทึกใน credentials.env: TAILSCALE_AUTH_KEY=tskey-auth-...

source credentials.env
bash 02-k3s/install-tailscale-host.sh

# ⚠️  หลัง script รัน: ไปที่ Tailscale Admin Console
# → คลิก machine "virtuallab-onprem-router"
# → Enable subnet route: 192.168.x.0/24 (K3S_ONPREM_CIDR ของคุณ)
```

---

### Step 5 — Setup SkyPilot

```bash
source credentials.env
bash 03-skypilot/setup-skypilot.sh
# → ติดตั้ง SkyPilot ใน venv
# → อ่าน Terraform outputs → เขียน ~/.sky/config.yaml อัตโนมัติ
# → รัน sky check → ต้อง pass ทั้ง kubernetes + aws
```

---

### Step 6 — ทดสอบ

```bash
source ~/skypilot-venv/bin/activate
source credentials.env

# ── Test A: K3s branch ────────────────────────────────────────────
sky launch 03-skypilot/task-k3s-test.yaml \
  --env S3_BUCKET=$ML_BUCKET_NAME \
  --cluster vlab-k3s-test
# Expected: รันบน on-prem, print hostname, เขียน result ไป S3

# ── Test B: AWS Spot branch ───────────────────────────────────────
sky launch 03-skypilot/task-aws-burst.yaml \
  --env S3_BUCKET=$ML_BUCKET_NAME \
  --cluster vlab-aws-test
# Expected: Spot instance, no public IP, S3 OK via VPC Endpoint

# ── Test C: 2-Tier AUTO routing (core concept) ────────────────────
sky launch 03-skypilot/task-2tier.yaml \
  --env S3_BUCKET=$ML_BUCKET_NAME
# K3s ว่าง → Branch A, K3s เต็ม → Branch B (อัตโนมัติ)

# ── หรือรัน validate ทุกอย่างทีเดียว ──────────────────────────────
bash 04-validate/validate-all.sh
```

---

## 🧹 Cleanup

```bash
# ลบ SkyPilot clusters หลังทดสอบ
sky down vlab-k3s-test
sky down vlab-aws-test

# ลบ AWS infrastructure (หยุดค่าใช้จ่าย)
cd 01-terraform && terraform destroy
```

---

## 🔑 Key Architecture Decisions

| ข้อ | สิ่งที่ทำ | ทำไม |
|:----|:---------|:-----|
| Tailscale on host | ไม่ใช้ Pod บน K3s | ง่ายกว่า POC, ทำงานเร็วกว่า |
| t4g.nano ASG 1:1 | Always-on On-Demand | Self-healing, ไม่ใช้ Spot สำหรับ gateway |
| Private Subnet only | Spot workers ไม่มี Public IP | Security + Constraint #4 |
| VPC S3 Endpoint | S3 access ไม่ผ่าน internet | ถูกกว่า, เร็วกว่า, secure กว่า |
| SkyPilot 2-tier spec | K3s → AWS ใน resources array | ไม่ต้องเขียน logic routing เอง |