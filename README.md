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
      ├── K3s nodes available? ─── YES ──► 🏠 BRANCH A: Run on local K3s worker
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
  -n ailab
```

The FastAPI `Deployment` mounts this as environment variables via `envFrom.secretRef`. The credentials are **never on disk, never in any image, never in git**.

### 2. K3s Access → Kubernetes ServiceAccount + RBAC

The FastAPI pod is assigned `ailab-fastapi-sa` — a ServiceAccount bound to a ClusterRole that grants SkyPilot the permissions it needs to manage local K3s workers (list nodes, create/delete pods, watch jobs). No kubeconfig file, no static tokens.

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
│   ├── app/{routers, models, schemas, services, db}/
│   └── sky_tasks/                ← SkyPilot 2-tier YAML task definitions
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

Before running anything, ensure you have:

- [ ] **K3s cluster** installed with at least 1 worker node joined
- [ ] **Node.js** ≥ 20 + **npm** ≥ 10
- [ ] **Python** ≥ 3.11 + `pip`
- [ ] **Docker** + **Docker Compose**
- [ ] **kubectl** + **helm** ≥ 3 (pointing at your K3s cluster)
- [ ] **Terraform** ≥ 1.7
- [ ] **AWS CLI** + IAM credentials with EC2/S3 permissions
- [ ] **Tailscale** account + Reusable Auth Key generated
- [ ] **Cloudflare** account + Tunnel token
- [ ] **SkyPilot**: `pip install "skypilot[aws,kubernetes]"`

---

### Step 1 — Day-0 Infrastructure (Manual, once only)

```bash
# 1a. Provision AWS: VPC, Private Subnet, NAT GW, S3 Endpoint, t4g.nano ASG
cd infrastructure/terraform
terraform init
terraform apply

# 1b. Verify On-Prem → AWS private IP reachability via Tailscale
bash infrastructure/scripts/validate-network.sh

# 1c. Create the AWS credentials Kubernetes Secret
bash infrastructure/scripts/create-k8s-secrets.sh
# (This is a reference script — review before running. Never commit secrets to git.)
```

---

### Step 2 — Deploy Control Plane (Helm)

```bash
cd k8s-helm
helm dependency update
helm upgrade --install ailab . -f values.yaml -n ailab --create-namespace
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