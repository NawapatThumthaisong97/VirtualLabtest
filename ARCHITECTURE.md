# ARCHITECTURE.md — AI Learner Lab (PoC Tracer Platform)

> **Classification:** Proof of Concept · Tracer Bullet  
> **Strategy:** Hybrid Execution — Local K3s First, AWS Spot Burst Second  
> **Last Updated:** 2026-06-17  
> **Maintainer:** Platform Team

---

## 🎯 Project Vision

This repository is a **Proof-of-Concept Tracer Bullet**: a single, thin, end-to-end vertical slice that validates data and control flow through a full Enterprise Hybrid-Cloud MLOps stack. The architecture is opinionated and constraint-driven — no decision is arbitrary.

**What this PoC must prove:**
1. ML jobs are routed intelligently: on-prem K3s nodes are always tried first.
2. When K3s capacity is exhausted, SkyPilot bursts automatically to AWS EC2 Spot — securely, privately, without heavy data crossing the VPN.
3. Credentials are never hardcoded. All sensitive access is mediated through Kubernetes-native mechanisms.
4. The entire system ingresses through a single zero-trust tunnel — no publicly open ports exist on any component.

---

## 🏗️ Core Technology Stack

| Layer | Component | Technology | Role |
|:------|:----------|:-----------|:-----|
| **Ingress** | Public Gateway | Cloudflare Tunnel (`cloudflared`) | Zero-inbound-port secure ingress |
| **Frontend** | Tracer UI | Next.js 14 (App Router) | 3-column PoC dashboard |
| **Auth** | SSO Guard | oauth2-proxy + Google SSO | Authenticates all inbound sessions |
| **API** | Control Plane | FastAPI (async/await) | Non-blocking API; orchestrates jobs via SkyPilot SDK |
| **State** | Database | PostgreSQL | Job state machine, RBAC, user sessions |
| **Orchestrator** | Job Manager | SkyPilot | Evaluates K3s vs AWS capacity; manages full worker lifecycle |
| **Local Compute** | On-Prem Workers | K3s nodes (bare-metal / VM) | First-priority ML execution targets |
| **Burst Compute** | Cloud Workers | AWS EC2 Spot (Private Subnet) | Overflow burst capacity; no Public IP; no Tailscale agent |
| **Deployment** | Packaging | Kubernetes + Helm | Deploys all Control Plane pods on the K3s Master Node |
| **Mesh VPN** | Network Fabric | Tailscale (WireGuard) | Encrypted overlay bridging On-Prem ↔ AWS Private VPC |
| **Cloud Gateway** | VPN Bridge | AWS EC2 t4g.nano (ASG 1:1) | Always-on Tailscale Subnet Router for the AWS VPC |
| **Storage** | Artifact Store | AWS S3 | Dataset input, model weight output |
| **Registry** | Image Store | Docker Hub | Container images; pulled directly, never through VPN |

---

## 🛡️ Non-Negotiable Architectural Constraints

All nine constraints are **hard rules**. Any PR or infrastructure change violating them requires explicit architectural review.

---

### CONSTRAINT 1 — Zero Inbound Public Ports

**Rule:** No component on-prem or in AWS may have a publicly reachable inbound port.

**Implementation:**
- `cloudflared` daemon runs inside the K3s cluster as a pod. It initiates an **outbound** HTTPS connection to Cloudflare's edge. No firewall rule, port-forward, or load balancer listener is ever opened.
- On AWS, Security Groups have **no inbound rules** from `0.0.0.0/0`.

---

### CONSTRAINT 2 — No Middleware (No Redis, No Celery)

**Rule:** FastAPI must be purely asynchronous and interface directly with SkyPilot's SDK. No message broker intermediaries.

**Implementation:**
- `POST /api/launch` validates the request, creates a job record (`state=PENDING`), returns `HTTP 202 Accepted` immediately.
- An `asyncio.create_task()` coroutine in the background calls `sky.launch()` directly.
- SkyPilot's own managed queue and state machine govern the worker lifecycle.
- PostgreSQL is the durable audit log for all state transitions.

---

### CONSTRAINT 3 — Hybrid Execution: Local K3s First, AWS Burst Second *(Core Concept)*

**Rule:** SkyPilot MUST evaluate and prefer on-prem K3s worker capacity before provisioning any AWS EC2 instance.

**Implementation:**
SkyPilot is configured with two **Resource Tiers** in priority order:

```yaml
# sky_tasks/ml_job.yaml (conceptual)
resources:
  - cloud: kubernetes          # Tier 1: On-Prem K3s
    region: local-k3s
    accelerators: null
    instance_type: local-worker
  - cloud: aws                 # Tier 2: Burst to AWS Spot
    region: ap-southeast-1
    use_spot: true
    instance_type: g4dn.xlarge
```

SkyPilot evaluates Tier 1 first. If local K3s nodes are at capacity, it falls through to Tier 2 and provisions an EC2 Spot instance automatically. This branching is fully automated — no manual intervention required at runtime.

**See the [Branching Data Flow](#-branching-data-flow--a-single-ml-job) section below for the complete decision tree.**

---

### CONSTRAINT 4 — AWS EC2 Spot Workers in Private Subnets Only

**Rule:** No AWS EC2 worker instance may have a Public IP. All workers reside exclusively in Private Subnets.

**Implementation:**
- The VPC contains a **Public Subnet** (hosts the t4g.nano Gateway + NAT Gateway) and a **Private Subnet** (hosts all Spot workers).
- Private Subnet has `map_public_ip_on_launch = false`.
- SkyPilot's AWS configuration targets the Private Subnet ID explicitly.
- Outbound internet access (for Docker Hub, S3) flows through the NAT Gateway.

---

### CONSTRAINT 5 — No Tailscale on Ephemeral Spot Instances

**Rule:** Tailscale must NOT be installed on AWS EC2 Spot worker instances.

**Rationale:** Spot instances are ephemeral. Installing Tailscale requires auth key registration and device lifecycle management — operationally fragile at scale and a security surface liability.

**Implementation:** The dedicated **AWS Tailscale Subnet Router** (Constraint 6) advertises the entire AWS VPC CIDR to the Tailnet. The SkyPilot Master on On-Prem reaches any private worker IP without requiring a Tailscale agent on that worker.

---

### CONSTRAINT 6 — Tailscale Gateway: Always-On t4g.nano in ASG (Min=1, Max=1)

**Rule:** AWS VPC connectivity to the Tailnet is provided by a dedicated, always-on `t4g.nano` EC2 instance in an Auto Scaling Group with `MinSize=1`, `MaxSize=1`.

**Rationale:** This single On-Demand instance acts as the **AWS Subnet Router**, advertising the VPC CIDR (e.g., `10.0.0.0/16`) to the Tailnet. The ASG ensures automatic self-healing if the instance fails, without manual intervention.

**Implementation:**
- `t4g.nano` runs `tailscaled` + `tailscale up --advertise-routes=<VPC_CIDR> --accept-routes`.
- The Tailscale Admin Panel approves the subnet route advertisement.
- On-Prem SkyPilot Master (`100.x.x.x` Tailscale IP) reaches workers at `10.0.x.x` via this gateway.
- This instance is **On-Demand**, never Spot. It must be persistent.

---

### CONSTRAINT 7 — Split Tunneling: Heavy Data Never Traverses the VPN

**Rule:** Docker image pulls and all S3 dataset/model transfers must use the direct internet path, not the Tailscale VPN.

**Rationale:** VPN bandwidth is finite and intended for low-volume control traffic (SSH, health checks). Routing GB-scale data through it creates a bottleneck and on-prem egress costs.

**Split-Tunnel Traffic Table:**

| Traffic Type | Route | Reason |
|:------------|:------|:--------|
| SSH / Control (Master → Worker) | Tailscale VPN → t4g.nano GW → Worker private IP | Encrypted, low-bandwidth |
| Docker Image Pull (K3s nodes) | On-Prem ISP → Docker Hub | Direct internet, no VPN |
| Docker Image Pull (Spot workers) | NAT GW → Internet → Docker Hub | AWS internet, not VPN |
| S3 Dataset Read (Spot workers) | VPC S3 Endpoint → S3 | AWS backbone, free |
| S3 Model Write (Spot workers) | VPC S3 Endpoint → S3 | AWS backbone, free |
| UI Response | Cloudflare Tunnel ← FastAPI | Zero inbound ports |

**Implementation:**
- AWS Spot workers use their default route (via NAT GW) for all internet traffic. No routes to on-prem CIDRs are injected for data.
- An **S3 VPC Gateway Endpoint** is created in the VPC so S3 traffic stays within the AWS backbone (no NAT GW charges, no internet hops).

---

### CONSTRAINT 8 — Credentials & Auth: Kubernetes-Native, Never Hardcoded

**Rule:** AWS credentials and K3s cluster access must be injected via Kubernetes-native mechanisms. No secrets in code, environment files, or Docker images.

**Implementation — Two-Part Strategy:**

#### Part A: AWS Credentials (for Spot provisioning)
- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are stored as a **Kubernetes Secret** in the `ailab` namespace.
- The FastAPI `Deployment` manifest mounts this Secret as environment variables via `envFrom.secretRef`.
- SkyPilot SDK (running inside the FastAPI pod) reads these env vars to authenticate to AWS APIs.
- The IAM user/role is scoped to minimum permissions: `ec2:*` on the target VPC + `s3:GetObject/PutObject` on the ML bucket only.

```yaml
# k8s-helm/templates/fastapi/deployment.yaml (conceptual)
envFrom:
  - secretRef:
      name: aws-credentials   # kubectl create secret generic aws-credentials ...
```

#### Part B: K3s Local Access (for local job dispatch)
- The FastAPI pod is assigned a **Kubernetes ServiceAccount** (`ailab-fastapi-sa`).
- This ServiceAccount is bound to a **ClusterRole** granting SkyPilot the permissions it needs to list nodes, create pods, and monitor jobs on the local K3s cluster.
- No kubeconfig file, no static tokens — Kubernetes RBAC handles it entirely.

```yaml
# k8s-helm/templates/fastapi/serviceaccount.yaml (conceptual)
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ailab-fastapi-sa
  namespace: ailab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ailab-fastapi-crb
subjects:
  - kind: ServiceAccount
    name: ailab-fastapi-sa
    namespace: ailab
roleRef:
  kind: ClusterRole
  name: ailab-skypilot-role
  apiGroup: rbac.authorization.k8s.io
```

---

### CONSTRAINT 9 — Separation of Concerns: Day-0 (Manual) vs Automated (SkyPilot)

**Rule:** Clearly delineate which tasks require human hands-on setup (once) and which are fully automated at runtime.

| Phase | Scope | Who/What Does It | Frequency |
|:------|:------|:----------------|:----------|
| **Day-0 Manual** | K3s cluster installation & node join | Platform Engineer | Once at setup |
| **Day-0 Manual** | AWS VPC, subnets, NAT GW, S3 VPC Endpoint (Terraform) | Platform Engineer | Once at setup |
| **Day-0 Manual** | t4g.nano ASG creation & Tailscale bootstrap | Platform Engineer | Once at setup |
| **Day-0 Manual** | IAM user creation, minimum-permissions policy | Platform Engineer | Once at setup |
| **Day-0 Manual** | `kubectl create secret generic aws-credentials` | Platform Engineer | Once at setup |
| **Day-0 Manual** | Helm chart deployment of Control Plane | Platform Engineer | On chart update |
| **Automated** | K3s capacity evaluation (Tier 1) | SkyPilot SDK | Every job |
| **Automated** | AWS EC2 Spot provisioning (Tier 2 fallback) | SkyPilot SDK | On K3s saturation |
| **Automated** | Worker environment prep (Docker pull, S3 fetch) | SkyPilot runtime | Every cloud job |
| **Automated** | `autostop` instance termination | SkyPilot SDK | Job completion |
| **Automated** | PostgreSQL state transitions (PENDING→RUNNING→SUCCESS) | FastAPI coroutine | Every job |

---

## 🗺️ Component Topology

### On-Premises (K3s Cluster)

```
┌──────────────────────────────────────────────────────────────────────┐
│                     ON-PREM K3S CLUSTER                              │
│                                                                      │
│  [Cloudflare Tunnel Pod] ──outbound──► Cloudflare Edge               │
│           │                                                          │
│           ▼                                                          │
│  [NGINX Ingress Controller]                                          │
│           │                                                          │
│           ▼                                                          │
│  [oauth2-proxy Pod] ──── Google SSO ──────────────────────────────► │
│           │                                                          │
│    ┌──────┴──────┐                                                   │
│    ▼             ▼                                                   │
│ [Next.js Pod]  [FastAPI Pod]  ◄─── K8s ServiceAccount (RBAC)        │
│                    │          ◄─── aws-credentials Secret (envFrom)  │
│                    ▼                                                  │
│            [SkyPilot SDK]                                            │
│            /            \                                            │
│    [K3s Workers]    [AWS API → EC2 Spot]                             │
│    (Tier 1 Local)   (Tier 2 Burst)                                   │
│                                                                      │
│  [PostgreSQL StatefulSet]                                            │
│  [Tailscale Router Pod] ── advertises On-Prem CIDR ──► Tailnet      │
└──────────────────────────────────────────────────────────────────────┘
                          │ Tailnet (WireGuard)
                          ▼
```

### AWS Cloud (Private VPC)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        AWS VPC (10.0.0.0/16)                        │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  PUBLIC SUBNET (10.0.1.0/24)                                │    │
│  │  [Internet Gateway]  ◄──  [NAT Gateway]                     │    │
│  │  [t4g.nano] ── ASG(Min=1,Max=1) ── tailscale subnet router  │    │
│  │   └─ advertises 10.0.0.0/16 → Tailnet                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │ routes via NAT GW                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  PRIVATE SUBNET (10.0.2.0/24)                               │    │
│  │  [EC2 Spot Workers]  (No Public IP, No Tailscale agent)     │    │
│  │   ├─ docker pull ──► NAT GW ──► Docker Hub                  │    │
│  │   ├─ s3 read/write ──► VPC S3 Endpoint ──► S3               │    │
│  │   └─ SSH from Master ──► Via t4g.nano Tailscale GW          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  [S3 VPC Gateway Endpoint]   [AWS S3 Bucket: ailab-ml-artifacts]    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🎬 Branching Data Flow — A Single ML Job

This is the canonical sequence validating the entire system. **Branch A** proves local-first execution. **Branch B** proves secure AWS burst.

```
USER (Browser)
 │
 │  POST /api/launch  (through Cloudflare Tunnel → NGINX → OAuth2 Proxy)
 ▼
FASTAPI POD
 ├─ Validate request
 ├─ INSERT job (state=PENDING) → PostgreSQL
 ├─ Return HTTP 202 Accepted + {job_id: "xyz"}   ◄── immediate, non-blocking
 └─ asyncio.create_task(dispatch_job("xyz"))
           │
           ▼
     SKYPILOT SDK  (inside FastAPI pod)
           │
           │  UPDATE job state=EVALUATING → PostgreSQL
           │
           ├─── EVALUATE K3S CAPACITY ──────────────────────────────────────
           │         │
           │    K3s nodes available?
           │         │
           │   YES ──┴────────────────────────────────────────────────────────
           │                        BRANCH A: LOCAL EXECUTION
           │
           │         SkyPilot targets K3s (Kubernetes cloud, local)
           │         UPDATE state=RUNNING → PostgreSQL
           │
           │         K3s Worker Node (On-Prem)
           │          ├─ docker pull trainer:v1 ──► On-Prem ISP → Docker Hub
           │          ├─ aws s3 cp s3://ailab-ml-artifacts/dataset.tar .
           │          │   (credentials from pod env → S3 VPC Endpoint or direct)
           │          ├─ [RUN ML TRAINING SCRIPT]
           │          └─ aws s3 cp model.pt s3://ailab-ml-artifacts/models/xyz/
           │
           │         SkyPilot detects job completion
           │         UPDATE state=SUCCESS → PostgreSQL
           │         ◄─────────────────────────────────────────────────────────
           │
           │   NO  ──┴────────────────────────────────────────────────────────
           │                        BRANCH B: AWS SPOT BURST
           │
           │         SkyPilot falls through to Tier 2 (AWS)
           │         UPDATE state=PROVISIONING → PostgreSQL
           │
           │         AWS API: RunInstances
           │          └─ Private Subnet (10.0.2.0/24), No Public IP
           │          └─ Instance: 10.0.2.15 (example)
           │
           │         SkyPilot SSH to 10.0.2.15:
           │          └─ Route: On-Prem(100.x.x.x) → Tailscale
           │                    → t4g.nano GW → 10.0.2.15 (private IP)
           │
           │         UPDATE state=RUNNING → PostgreSQL
           │
           │         EC2 Spot Worker (10.0.2.15)
           │          ├─ docker pull trainer:v1 ──► NAT GW → Docker Hub
           │          ├─ aws s3 cp s3://ailab-ml-artifacts/dataset.tar .
           │          │   (→ VPC S3 Gateway Endpoint → S3, stays on AWS backbone)
           │          ├─ [RUN ML TRAINING SCRIPT]
           │          └─ aws s3 cp model.pt s3://ailab-ml-artifacts/models/xyz/
           │
           │         Job exits 0
           │         SkyPilot autostop → AWS terminates 10.0.2.15
           │         UPDATE state=SUCCESS → PostgreSQL
           │
           ▼
     NEXT.JS UI
      └─ JobStateTable polls GET /api/jobs → renders SUCCESS
      └─ LiveLogTerminal shows streamed logs from FastAPI (SSE)
```

---

## 🔑 Credential Flow Diagram

```
Day-0 Setup (Manual):
  Platform Engineer
    │
    ├─► kubectl create secret generic aws-credentials \
    │       --from-literal=AWS_ACCESS_KEY_ID=AKIA... \
    │       --from-literal=AWS_SECRET_ACCESS_KEY=... \
    │       -n ailab
    │
    └─► Helm Chart deploys FastAPI with:
            spec.serviceAccountName: ailab-fastapi-sa  ◄── K3s RBAC
            envFrom:
              - secretRef:
                  name: aws-credentials               ◄── AWS API access

Runtime (Automated):
  FastAPI Pod
    ├─ env: AWS_ACCESS_KEY_ID  ◄── injected from Secret (never on disk/image)
    ├─ env: AWS_SECRET_ACCESS_KEY  ◄── injected from Secret
    └─ ServiceAccount Token (auto-mounted) ◄── SkyPilot uses to list K3s nodes
```

---

## ✅ Constraint Verification Matrix

| # | Constraint | Implementation | Status |
|:--|:-----------|:---------------|:-------|
| 1 | Zero inbound public ports | Cloudflare Tunnel (outbound-init only) | ✅ ENFORCED |
| 2 | No Redis / Celery | `asyncio.create_task()` + SkyPilot SDK | ✅ ENFORCED |
| 3 | K3s-first, AWS burst second | SkyPilot 2-tier resource config | ✅ ENFORCED |
| 4 | No Public IP on Spot workers | Private Subnet, `map_public_ip_on_launch=false` | ✅ ENFORCED |
| 5 | No Tailscale on Spot instances | t4g.nano GW advertises full VPC CIDR | ✅ ENFORCED |
| 6 | Fault-tolerant t4g.nano Gateway | ASG Min=1, Max=1, On-Demand instance | ✅ ENFORCED |
| 7 | Split tunneling for data | NAT GW for Docker Hub; VPC Endpoint for S3 | ✅ ENFORCED |
| 8 | Credentials never hardcoded | K8s Secret (AWS) + ServiceAccount (K3s) | ✅ ENFORCED |
| 9 | Day-0 vs Automated separation | Terraform+Helm (manual) / SkyPilot (automated) | ✅ ENFORCED |

---

## 🛠️ Implementation Roadmap (Tracer Bullets)

| Bullet | Scope | Deliverables | Constraints Proven |
|:-------|:------|:------------|:-------------------|
| **Bullet 0** | Prerequisites | IAM user, Tailscale Auth Keys, Cloudflare Token, K3s join tokens | #8, #9 |
| **Bullet 1** | AWS Infrastructure | Terraform: VPC, Subnets, NAT GW, S3 Endpoint, t4g.nano ASG | #4, #5, #6, #7 |
| **Bullet 2** | K3s Control Plane | Helm: PostgreSQL, FastAPI stub + ServiceAccount, NGINX, oauth2-proxy, cloudflared | #1, #2, #8 |
| **Bullet 3A** | Local Vertical Slice | `/launch` → SkyPilot → K3s worker → S3 round-trip | #3, #7 |
| **Bullet 3B** | Burst Vertical Slice | Saturate K3s → SkyPilot auto-bursts → AWS Spot → S3 | #3, #4, #5, #6, #7 |
| **Bullet 4** | Visual Slice | Next.js 3-column dashboard: Job Panel, State Table, Live Log Terminal | End-to-end UX |

---

## 📁 Repository Structure

```
VirtualLabtest/
├── ARCHITECTURE.md               ← This document
├── README.md                     ← Developer quick-start
│
├── frontend-tracer/              ← Next.js Tracer UI
│   ├── src/
│   │   ├── app/                  ← App Router pages
│   │   ├── components/           ← JobCommandPanel, JobStateTable, LiveLogTerminal
│   │   └── lib/                  ← API client (fetch wrappers to FastAPI)
│   ├── public/
│   └── Dockerfile
│
├── backend-fastapi/              ← FastAPI async Control Plane API
│   ├── app/
│   │   ├── main.py               ← Entrypoint, lifespan, CORS
│   │   ├── routers/              ← /api/launch, /api/jobs, /api/logs
│   │   ├── models/               ← SQLAlchemy ORM: Job, User
│   │   ├── schemas/              ← Pydantic: JobCreate, JobStatus
│   │   ├── services/             ← skypilot_service.py (SDK wrapper)
│   │   └── db/                   ← Async session, Alembic migrations
│   ├── sky_tasks/                ← SkyPilot YAML task definitions
│   │   ├── ml_job.yaml           ← 2-tier resource spec (K3s → AWS Spot)
│   │   └── burst_test.yaml       ← Force-AWS burst for Bullet 3B testing
│   └── Dockerfile
│
├── k8s-helm/                     ← Helm chart: Control Plane deployment
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── fastapi/              ← Deployment, Service, ServiceAccount, RBAC
│       ├── frontend/             ← Deployment, Service
│       ├── postgresql/           ← StatefulSet, PVC, Service
│       ├── nginx-ingress/        ← IngressClass, Ingress
│       ├── oauth2-proxy/         ← Deployment, Service
│       ├── cloudflared/          ← Deployment for Cloudflare Tunnel pod
│       └── tailscale-router/     ← Pod advertising On-Prem CIDR to Tailnet
│
└── infrastructure/               ← Infrastructure as Code & Scripts
    ├── terraform/
    │   ├── vpc.tf                ← VPC, Subnets (Public/Private), IGW, NAT GW
    │   ├── s3_endpoint.tf        ← VPC S3 Gateway Endpoint
    │   ├── tailscale_gateway.tf  ← t4g.nano ASG (Min=1,Max=1) + UserData
    │   └── iam.tf                ← IAM user + minimum-permissions policy
    ├── cloudflare/
    │   └── tunnel.yaml           ← cloudflared ingress routing config
    └── scripts/
        ├── bootstrap-gateway.sh  ← UserData: installs tailscaled, advertises VPC CIDR
        ├── validate-network.sh   ← Smoke test: On-Prem → Worker private IP via Tailscale
        └── create-k8s-secrets.sh ← `kubectl create secret` command (reference, not CI)
```