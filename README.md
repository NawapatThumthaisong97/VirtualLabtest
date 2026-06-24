# AI Learner Lab — PoC Tracer Platform

> **Type:** Proof of Concept · Tracer Bullet  
> **Strategy:** 🏠 Local K3s First → ☁️ AWS Spot Burst Second  
> **Status:** Foundation Scaffold · Pre-Application Code

---

## 🧭 What Is This?

This repository is a **deliberately minimal, vertically integrated PoC**. It proves a single question end-to-end:

> *"Can we submit an ML job from a browser, have it automatically run on on-prem K3s nodes first, seamlessly overflow to private AWS EC2 Spot instances when K3s is saturated, and return results — all with zero hardcoded credentials and zero publicly open ports?"*

When the answer is **yes** across all 9 constraints below, the Tracer Bullet has succeeded.

📐 For the full system blueprint, constraint definitions, credential flow, and annotated data-flow decision tree — read **[`ARCHITECTURE.md`](./ARCHITECTURE.md)**.

---

## 🏛️ Tech Stack at a Glance

| What | Technology | Why |
|:-----|:-----------|:----|
| **Frontend** | Next.js 14 (App Router) | 3-column Tracer dashboard |
| **Backend API** | FastAPI (async/await) | Non-blocking; no Celery/Redis |
| **Database** | PostgreSQL | Job state machine, RBAC |
| **ML Orchestrator** | SkyPilot | 2-tier resource routing (K3s → AWS) |
| **Local Compute** | K3s bare-metal/VM nodes | First-priority ML workers |
| **Cloud Compute** | AWS EC2 Spot (Private Subnet) | Burst capacity only |
| **Deployment** | Kubernetes + Helm | Reproducible Control Plane |
| **Mesh VPN** | Tailscale (WireGuard) | On-Prem ↔ AWS private bridge |
| **Ingress** | Cloudflare Tunnel | Zero inbound ports |
| **Cloud Storage** | AWS S3 | Datasets in, model weights out |
| **Container Registry** | Docker Hub | Images pulled directly, not via VPN |
| **VPN Gateway** | AWS t4g.nano (ASG 1:1) | Persistent Tailscale Subnet Router |

---

## 📐 Nine Hard Constraints (TL;DR)

> Full rationale and implementation specs are in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

| # | Constraint | Implemented By |
|:--|:-----------|:---------------|
| 1 | Zero inbound public ports | Cloudflare Tunnel (outbound-init only) |
| 2 | No Redis / Celery / middleware | `asyncio.create_task()` + SkyPilot SDK |
| 3 | **K3s first, AWS burst second** | SkyPilot 2-tier resource YAML |
| 4 | No Public IP on AWS Spot workers | Private Subnet, `map_public_ip_on_launch=false` |
| 5 | No Tailscale on Spot instances | t4g.nano advertises full VPC CIDR to Tailnet |
| 6 | Fault-tolerant AWS VPN Gateway | t4g.nano in ASG Min=1, Max=1 (On-Demand) |
| 7 | Split tunneling — data never crosses VPN | NAT GW → Docker Hub; VPC Endpoint → S3 |
| 8 | **Credentials never hardcoded** | K8s Secret (AWS) + ServiceAccount (K3s) |
| 9 | **Day-0 manual vs Automated separation** | Terraform+Helm (human) / SkyPilot (runtime) |

---

## 🔀 The Hybrid Execution Strategy Explained

This is the **core concept** that makes this architecture unique.

```
Job Submitted
      │
      ▼
SkyPilot evaluates K3s capacity
      │
      ├── K3s nodes avvirtuallable? ─── YES ──► 🏠 BRANCH A: Run on local K3s worker
      │                                          - Fast, no cloud cost
      │                                          - Docker pull via on-prem ISP
      │                                          - S3 access via AWS credentials in env
      │
      └── K3s nodes full? ──────── YES ──► ☁️  BRANCH B: Burst to AWS EC2 Spot
                                                 - SkyPilot provisions Private Subnet instance
                                                 - SSH via Tailscale → t4g.nano → private IP
                                                 - Docker pull via NAT Gateway
                                                 - S3 access via VPC Gateway Endpoint
                                                 - autostop terminates instance on completion
```

No manual intervention is needed. SkyPilot handles the branching decision entirely at runtime.

---

## 🔑 Credential Management (Zero Hardcoding)

Two Kubernetes-native mechanisms handle all sensitive access:

### 1. AWS Credentials → Kubernetes Secret

```bash
# Day-0: Run once by Platform Engineer
kubectl create secret generic aws-credentials \
  --from-literal=AWS_ACCESS_KEY_ID=AKIA... \
  --from-literal=AWS_SECRET_ACCESS_KEY=... \
  -n virtuallab
```

The FastAPI `Deployment` mounts this as environment variables via `envFrom.secretRef`. The credentials are **never on disk, never in any image, never in git**.

### 2. K3s Access → Kubernetes ServiceAccount + RBAC

The FastAPI pod is assigned `virtuallab-fastapi-sa` — a ServiceAccount bound to a ClusterRole that grants SkyPilot the permissions it needs to manage local K3s workers (list nodes, create/delete pods, watch jobs). No kubeconfig file, no static tokens.

---

## 📋 Manual (Day-0) vs Automated Responsibilities

| Responsibility | Who | Frequency |
|:--------------|:----|:----------|
| Install K3s + join worker nodes | Platform Engineer | Once |
| Terraform: VPC, Subnets, NAT GW, S3 Endpoint | Platform Engineer | Once |
| Terraform: t4g.nano ASG + Tailscale bootstrap | Platform Engineer | Once |
| Create IAM user + minimum-permissions policy | Platform Engineer | Once |
| `kubectl create secret generic aws-credentials` | Platform Engineer | Once |
| `helm upgrade --install` Control Plane | Platform Engineer | On chart update |
| **K3s capacity evaluation** | SkyPilot SDK | Every job |
| **AWS EC2 Spot provisioning (if needed)** | SkyPilot SDK | On K3s saturation |
| **Worker setup: Docker pull, S3 fetch** | SkyPilot runtime | Every cloud job |
| **`autostop` — instance termination** | SkyPilot SDK | Job completion |
| **PostgreSQL state transitions** | FastAPI coroutine | Every job |

---

## 📁 Repository Map

```
VirtualLabtest/
│
├── 📄 ARCHITECTURE.md            ← Full blueprint: constraints, topology, data flow
├── 📄 README.md                  ← You are here
│
├── 📦 frontend-tracer/           ← Next.js Tracer UI
│   └── src/{app, components, lib}/
│
├── 📦 backend-fastapi/           ← Async FastAPI + SkyPilot SDK integration
│   ├── app/
│   │   ├── routers/              ← /api/launch, /api/jobs, /api/logs
│   │   ├── models/               ← SQLAlchemy ORM: Job, User
│   │   ├── schemas/              ← Pydantic v2: JobCreate, JobStatus
│   │   ├── services/
│   │   │   └── skypilot_service.py  ← ✅ SkyPilot SDK wrapper (async, non-blocking)
│   │   └── db/                   ← Async session, Alembic migrations
│   ├── sky_tasks/                ← SkyPilot task definitions
│   │   ├── ml_job.yaml           ← ✅ 2-tier: K3s first → AWS Spot fallback
│   │   ├── burst_test.yaml       ← ✅ Force-AWS task for Bullet 3B validation
│   │   └── sky_config.yaml       ← ✅ SkyPilot global config (private subnet, ServiceAccount)
│   └── requirements.txt          ← ✅ Python deps (FastAPI, SkyPilot, SQLAlchemy, etc.)
│
├── 📦 k8s-helm/                  ← Helm chart: Control Plane on K3s Master
│   └── templates/
│       ├── fastapi/              ← Includes ServiceAccount + RBAC + Secret ref
│       ├── frontend/
│       ├── postgresql/
│       ├── nginx-ingress/
│       ├── oauth2-proxy/
│       ├── cloudflared/          ← Cloudflare Tunnel pod
│       └── tailscale-router/     ← On-Prem Tailscale Subnet Router pod
│
└── 📦 infrastructure/            ← IaC + Scripts
    ├── terraform/                ← VPC, Subnets, NAT GW, S3 Endpoint, t4g.nano ASG, IAM
    ├── cloudflare/               ← Tunnel routing config
    └── scripts/                  ← Gateway bootstrap, network validation, secret creation helper
```

---

## 🚀 Getting Started

### Prerequisites

> ⚠️ **Linux / WSL Required**
> All backend work, SkyPilot CLI usage, and Terraform runs must be done inside **WSL (Ubuntu)**
> on Windows — or directly on a Linux machine. SkyPilot does **not** support Windows natively.
> Open a WSL terminal (`wsl`) for everything below.

Before running anything, ensure you have the following **inside your WSL/Linux environment**:

| Tool | Min Version | Status (WSL) |
|:-----|:------------|:-------------|
| K3s cluster (≥1 worker joined) | latest | ❓ Check manually |
| Node.js + npm | ≥ 20 / ≥ 10 | ❓ Check manually |
| Python + pip | ≥ 3.11 | ❓ Run `python3 --version` in WSL |
| Docker + Docker Compose | latest | ❓ Check manually |
| **kubectl** | ≥ 1.29 | ❓ Run `kubectl version --client` in WSL |
| **helm** | ≥ 3 | ❌ Not installed — see below |
| **Terraform** | ≥ 1.7 | ❌ Not installed — see below |
| **AWS CLI** | ≥ 2 | ❓ Run `aws --version` in WSL |
| **Tailscale** account + Reusable Auth Key | — | ❓ Manual step |
| **Cloudflare** account + Tunnel token | — | ❓ Manual step |
| **SkyPilot** (local dev only) | ≥ 0.7 | ❌ Not installed — see below |

#### Install missing tools (Linux / WSL — Ubuntu/Debian)

```bash
# ── Terraform ────────────────────────────────────────────────────────────────
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y terraform
terraform -version   # Verify

# ── Helm ─────────────────────────────────────────────────────────────────────
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version         # Verify

# ── AWS CLI v2 (if not already installed) ────────────────────────────────────
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install
aws --version        # Verify

# ── kubectl (if not already installed) ───────────────────────────────────────
curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
kubectl version --client   # Verify

# ── SkyPilot (local dev / testing only) ──────────────────────────────────────
# SkyPilot is Linux-only. It is also installed inside the FastAPI container
# via requirements.txt — this install is for running `sky` CLI locally.
#
# ⚠️  IMPORTANT: Install SkyPilot inside a Python virtual environment (venv).
#    Installing globally with sudo pip can break your system Python packages.
#
# Step 1 — Create a dedicated virtual environment (one-time setup)
python3 -m venv ~/skypilot-venv

# Step 2 — Activate the virtual environment
#   You MUST activate it every time you open a new terminal before using `sky`.
source ~/skypilot-venv/bin/activate
# Your prompt will change to show (skypilot-venv) — this means it is active.

# Step 3 — Upgrade pip inside the venv (prevents obscure install errors)
pip install --upgrade pip

# Step 4 — Install SkyPilot with AWS + Kubernetes support
pip install "skypilot[aws,kubernetes]"

# Step 5 — Verify: SkyPilot can see your AWS credentials and K8s cluster
sky check

# ── To use SkyPilot in future sessions ───────────────────────────────────────
# Every time you open a NEW terminal, run this first:
#   source ~/skypilot-venv/bin/activate
# Then you can run sky commands normally (sky launch, sky exec, sky down …)
```

---

### ⚡ TL;DR — Full Deploy in 3 Commands

> แก้ credential ที่เดียว → รัน deploy ได้เลย ไม่ต้องแตะไฟล์อื่น

```bash
# 1. ตั้งค่า credentials (ทำครั้งเดียว)
cp credentials.env.example credentials.env
nano credentials.env          # แก้ค่าให้ครบทุกช่อง

# 2. ติดตั้ง tools ที่จำเป็น (ทำครั้งเดียว)
bash setup.sh

# 3. Deploy ทุกอย่างในคำสั่งเดียว 🚀
bash deploy.sh
```

`deploy.sh` จะรันตามลำดับอัตโนมัติ:
1. `terraform apply` — สร้าง VPC, NAT GW, S3, t4g.nano ASG, IAM บน AWS
2. อ่าน Terraform outputs (subnet ID, SG ID)
3. `kubectl create secret aws-credentials` — ใส่ AWS key เข้า K3s
4. `helm upgrade --install` — deploy FastAPI, Frontend, PostgreSQL, Cloudflare Tunnel, oauth2-proxy, Tailscale Router ทั้งหมด

> 💡 **ต้องการแก้ค่าใดๆ?** แก้ใน `credentials.env` แล้วรัน `bash deploy.sh` ใหม่ได้เลย

```bash
# ตัวเลือกพิเศษ
bash deploy.sh --dry-run    # ดูแผนก่อนโดยไม่ deploy จริง
bash deploy.sh --tf-only    # รัน Terraform เท่านั้น
bash deploy.sh --helm-only  # รัน Helm เท่านั้น (ถ้า Terraform ทำไปแล้ว)
```

---

### Step 1 — Day-0 Infrastructure (อยู่ใน deploy.sh แล้ว)

> ✅ `bash deploy.sh` จัดการทั้งหมดนี้ให้อัตโนมัติ
> สำหรับ debug หรือรันแยก ใช้คำสั่งด้านล่าง:

```bash
# รัน Terraform แยก (ถ้าต้องการ)
cd infrastructure/terraform
terraform init
terraform plan
terraform apply

# ตรวจสอบ network connectivity
bash infrastructure/scripts/validate-network.sh

# สร้าง K8s Secret แยก (ถ้า Helm ล้มเหลว)
bash infrastructure/scripts/create-k8s-secrets.sh
```

---

### Step 2 — Deploy Control Plane (อยู่ใน deploy.sh แล้ว)

> ✅ `bash deploy.sh` จัดการทั้งหมดนี้ให้อัตโนมัติ
> สำหรับรัน Helm แยก:

```bash
source credentials.env
helm upgrade --install virtuallab ./k8s-helm \
  --namespace virtuallab --create-namespace \
  --set global.cloudflare.tunnelToken="$CLOUDFLARE_TUNNEL_TOKEN" \
  --set global.aws.region="$AWS_DEFAULT_REGION" \
  --set postgresql.password="$POSTGRES_PASSWORD"
  # (ดู deploy.sh สำหรับ --set flags ครบทั้งหมด)
```

This deploys: NGINX Ingress, Cloudflare Tunnel pod, oauth2-proxy, PostgreSQL, FastAPI (with ServiceAccount + Secret), Next.js UI, and Tailscale Subnet Router pod.

---

### Step 3 — Local Development (Backend)

```bash
cd backend-fastapi
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

cp .env.example .env          # Fill in DB URL, etc.
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

---

### Step 4 — Local Development (Frontend)

```bash
cd frontend-tracer
npm install
cp .env.local.example .env.local   # Set NEXT_PUBLIC_API_URL
npm run dev
```

UI: `http://localhost:3000`

---

### Step 5 — Tracer Bullet Validation

```bash
# Submit a normal job — should route to K3s (Branch A)
curl -X POST http://localhost:8000/api/launch \
  -H "Content-Type: application/json" \
  -d '{"job_type": "normal", "config": {}}'
# Expected: HTTP 202 + {"job_id": "<uuid>", "state": "PENDING"}

# Submit a burst job — forces Branch B for testing
curl -X POST http://localhost:8000/api/launch \
  -H "Content-Type: application/json" \
  -d '{"job_type": "burst", "config": {"force_cloud": true}}'
```

Watch the **State Table** in the Next.js UI update in real time through every transition:
`PENDING → EVALUATING → PROVISIONING → RUNNING → SUCCESS`

---

## 🤝 Development Rules

1. **Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) in full** before writing any code.
2. Any change violating one of the 9 constraints requires architectural review.
3. All backend endpoints must be `async def` — zero blocking I/O.
4. `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — **never in `.env` files committed to git**.
5. EC2 instances — **always private subnet**. Verify with `aws ec2 describe-instances --query "Reservations[].Instances[].PublicIpAddress"` (must return `null`).
6. PR title format: `[Bullet-<N>] <description>` — e.g., `[Bullet-3A] SkyPilot K3s local dispatch`.

---

## 📜 License

Internal PoC / Research Use. No license assigned until the project graduates from PoC status.