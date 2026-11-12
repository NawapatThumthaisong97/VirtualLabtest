# CI/CD ด้วย Argo CD — Solution Design

> สถานะ: **แผน ยังไม่ได้ลงมือ** (2026-11-09) — ต้องให้ Pete อนุมัติ decision ในข้อ 4 และตอบคำถามข้อ 11 ก่อนเริ่ม Phase 1
> คู่กับ [CICD_ARGOCD_PIPELINE.md](CICD_ARGOCD_PIPELINE.md) (workflow / manifest ทีละไฟล์ + วิธีใช้งานประจำวัน)
> แผนนี้อิง **โค้ดจริง** ใน repo ไม่ได้อิง `ARCHITECTURE.md` ซึ่งยังพูดถึง Helm chart `k8s-helm/`, Next.js และ Docker Hub ที่ไม่มีอยู่จริง
> เกี่ยวข้องกับ [AWS_LAB_GATEWAY.md](AWS_LAB_GATEWAY.md) ข้อ 16 เฟส 2A / 2C / 2D (frontend เรียก `/api` แบบ relative + nginx proxy) ซึ่งเป็น**ข้อกำหนดก่อน** Phase 3 ของแผนนี้

---

## 0. สรุปสั้น

- **Argo CD รันอยู่ใน K3s (namespace `argocd`) แล้วดึง Git เอง (pull)** ไม่เปิดพอร์ตขาเข้า (Constraint 1) และ GitHub Actions ไม่ต้องถือ kubeconfig หรือเข้า Tailscale
- **GitHub Actions ทำ CI**: test → build image **ครั้งเดียว** → scan → push GHCR → แก้ tag ใน `deploy/…/overlays/staging`
  **Argo CD ทำ CD**: sync จาก Git เข้า cluster, เห็น drift และ self-heal
- **web-portal ย้ายจาก docker compose บน VM เข้า K3s** เพราะ Argo CD deploy ได้เฉพาะ Kubernetes
  backend / frontend ใช้ `hostNetwork` บน **platform node** ที่แยกไว้ เพื่อให้ backend ยังเห็น IP จริงของเครื่องแลป (กฎ Start: เครื่องแลป → K8s, ที่อื่น → AWS)
- มี 2 environment ใน cluster เดียว:
  - `vlab-staging`: auto sync ทุกครั้งที่ merge เข้า `main` และปิด scheduler ทุกตัว
  - `vlab-prod`: promote ด้วย git tag → PR → merge และ sync ได้เฉพาะนอกเวลาเรียน (Argo CD sync window)
- secret ที่อยู่ใน Git ต้องเป็น **Sealed Secrets** เท่านั้น ค่าจริงยังเก็บในไฟล์ที่ gitignore เหมือนเดิม (`ansible/group_vars/all.yml`) แล้วใช้ script แปลง
- งานที่ Ansible ทำหลัง `compose up` (`init_db.py` → `run_rbac_seed.py` → verify) ย้ายไปเป็น **Argo CD hook Job** ทั้งหมด และเพิ่ม `pg_dump` ก่อน migrate ทุกครั้ง
- rollback ทำด้วย `git revert` commit ที่เปลี่ยน tag แล้ว Argo CD จะ sync กลับเอง ส่วน schema DB เดินหน้าอย่างเดียว ดังนั้น migration ต้อง backward compatible อย่างน้อย 1 release
- Ansible ยังเป็นเจ้าของงาน Day-0 (OS, Tailscale, K3s, camp registry, ecr-sync, SkyPilot Helm และ bootstrap Argo CD) ส่วน Terraform ยังรันด้วยมือ

---

## 1. สภาพปัจจุบัน (อ่านจากโค้ด 2026-11-09)

### 1.1 แต่ละส่วน deploy อย่างไร

| ส่วน | ตอนนี้ deploy ด้วย | รันที่ | ไฟล์ |
|---|---|---|---|
| web-portal (FastAPI + Vite/nginx + Postgres 17) | Ansible `web-service`: rsync source → render `.env` → `docker compose up -d --build` (**build บนเครื่อง prod**) → `init_db.py` → `run_rbac_seed.py` → verify `/health`, whoami, `sky api info` | VM group `webservice` ผูกพอร์ตกับ `BIND_IP` = Tailscale IP | `ansible/roles/web-service/tasks/main.yml`, `web-portal/docker-compose.prod.yml` |
| K3s | Ansible `k3s-server` / `k3s-agent` (flannel บน `tailscale0`, `--node-ip` = Tailscale IP) | master + เครื่องแลป | `ansible/roles/k3s-*` |
| SkyPilot API server + ingress-nginx + cloudflared | Ansible `skypilot-node` (`helm upgrade --install`) | master, ns `skypilot`, `skypilot-ingress` | `ansible/roles/skypilot-node/tasks/main.yml` |
| NetworkPolicy lab isolation, ns `vlab-scan` | Ansible (`kubectl apply` จาก `lookup`) | cluster | `k8s/lab-isolation-networkpolicy.yaml`, `k8s/scan-namespace.yaml` |
| SIEM 5 layers | `kubectl apply` ด้วยมือตาม `docs/SETUP_TEST.md` ขั้น 5.5 | ns `siem-system` | `k8s/siem/**` |
| oauth2-proxy + Ingress SSO | `kubectl apply` ด้วยมือ (ไม่แน่ใจว่ายังใช้ไหม เพราะ image `virtual-lab-backend:latest` ไม่มีใคร build) | ns `virtual-lab` | `k8s/auth/**` |
| camp registry / ecr-sync / scan-runner image | Ansible `registry`, `ecr-sync`, `scan-runner-image` | เครื่อง registry | `ansible/roles/*` |
| lab image (music-lab ฯลฯ) | `ansible-playbook build-images.yml` → camp registry → ecr-sync → ECR | เครื่อง registry | `ansible/build-images.yml` |
| AWS (VPC, router, ECR, S3) | `terraform apply` ด้วยมือ | — | `terraform/` |
| CI | GitHub Actions `Backend tests` (pytest 6 job, SIEM container จริง, vitest ของ AdminMonitor) **ไม่มี build / deploy** | GitHub-hosted | `.github/workflows/backend-tests.yml` |

ข้อเท็จจริงของ repo ที่มีผลกับการออกแบบ:
- repo เป็น **public** (`NawapatThumthaisong97/VirtualLabtest` ซึ่งเป็น account ส่วนตัว ไม่ใช่ org) ทำให้ GHCR แบบ public และ Actions ใช้ได้ฟรี และ Argo CD อ่าน repo ได้โดยไม่ต้องมี credential
- branch `main` **ยังไม่ได้ protect** (ruleset "PR to main" ตั้ง `enforcement: disabled` ไว้) ต้องเปิดใน Phase 0
- SIEM ฮาร์ดโค้ด IP `100.86.87.27` ไว้ 3 ที่ ได้แก่ datasource ของ Grafana, sink ของ vector aggregator และ sigma cronjob (`k8s/siem/layer3-processing/01-vector-aggregator-configmap.yaml:261`, `k8s/siem/layer5-detection/02-sigma-rules-cronjob.yaml:103`) ตอนย้ายต้องเปลี่ยนเป็นค่าของ env

### 1.2 ปัญหาที่ CI/CD ต้องแก้

1. **ไม่มี artifact** เพราะ image ถูก build บนเครื่อง prod ตอน deploy (`--build`) การย้อนกลับต้อง rsync commit เก่ามา build ใหม่ และไม่มีทางรู้ว่าที่รันอยู่คือ commit ไหน
2. **deploy ผูกกับตัวคน** ต้องมี SSH, `group_vars/all.yml` และรหัส `-K` บนเครื่องตัวเอง ไม่มี log ว่าใคร deploy อะไรเมื่อไหร่
3. **drift** เพราะ SIEM, auth และ NetworkPolicy บางส่วน apply ด้วยมือ ไม่มีใครบอกได้ว่าของใน cluster ตรงกับ Git ไหม
4. **frontend ฝัง `VITE_API_URL` ไว้ตอน build** (`web-portal/frontend/Dockerfile:17`) image หนึ่งจึงใช้ได้กับ host เดียว เอา image เดียวไปใช้หลาย env ไม่ได้
5. **backend ถือ kubeconfig ของ admin** (`/etc/rancher/k3s/k3s.yaml` ถูก copy เป็น `backend/kubeconfig.yaml`) ซึ่งมีสิทธิ์ cluster-admin ทั้ง cluster
6. backend `Dockerfile` โหลด kubectl รุ่น `stable.txt` ล่าสุดทุกครั้งที่ build เมื่อไม่ได้ส่ง `KUBECTL_VERSION` มา build แต่ละรอบจึงได้ไม่เหมือนกัน

### 1.3 ข้อจำกัดในโค้ดที่ห้ามพังตอนย้าย

| # | ข้อจำกัด | ที่มาในโค้ด | ผลกับการออกแบบ |
|---|---|---|---|
| C1 | backend ตัดสินว่าเป็นเครื่องแลปหรือไม่จาก **IP ของ connection** และไม่เชื่อ `X-Forwarded-For` | `web-portal/backend/app/routes/session_route.py:113`, `app/services/warm_pod_service.py:266` (`node_for_ip`) | หน้า backend ห้ามมี NAT หรือ proxy ที่ทำให้ IP จริงหาย จึงต้องใช้ `hostNetwork` (เทียบเท่า `network_mode: host` ใน compose) |
| C2 | scheduler ทุกตัวอยู่ใน process เดียวกับ API (session reconciler, prewarm/prelaunch, scan reconciler, health checker) และไม่มี leader election | `app/main.py:191-221` | backend ต้อง `replicas: 1` + `strategy: Recreate` เสมอ ถ้ามี 2 pod จะ launch / terminate ซ้ำกัน |
| C3 | node ที่ไม่มี label `node-role.kubernetes.io/control-plane` จะถูกนับเป็นเครื่องแลป | `warm_pod_service.py:153,275`, `prewarm_service.py:82,165` | ถ้าเพิ่ม node ให้ web-portal ต้องแก้โค้ดให้ข้าม node นั้น (D3) |
| C4 | schema สร้างด้วย `script/init_db.py` (Alembic + stamp legacy) และต้อง seed RBAC ทุกครั้งที่ deploy (ถ้าไม่มี ทุก API จะตอบ 403) | task "Create database schema" / "Seed RBAC roles" ใน role `web-service` | ต้องรันเป็น hook Job ก่อน backend ตัวใหม่ขึ้น |
| C5 | ห้ามมีพอร์ตขาเข้าจากสาธารณะ และ image pull / data ห้ามวิ่งผ่าน VPN | `ARCHITECTURE.md` Constraint 1, 7 | Argo CD ต้องเป็นแบบ pull และ image จาก GHCR ต้องดึงตรงทาง internet |
| C6 | secret ห้ามอยู่ในโค้ดหรือใน image | Constraint 8, `k8s/README.md` | ใช้ Sealed Secrets และห้าม bake `.env` ลง image |
| C7 | sky SDK มี timeout 2.5 วิ จึงต้องคุยกับ API server ผ่าน NodePort 30880 บน Tailscale ไม่ใช่ทาง Cloudflare | `k8s/skypilot-api-tailnet-service.yaml` | backend ใน K3s ยังใช้ endpoint เดิม `http://<master>:30880` |

---

## 2. เป้าหมาย / สิ่งที่ไม่ทำ

**ทำ**
- เมื่อ merge เข้า `main` ให้ test → build image ครั้งเดียว → scan → ขึ้น staging อัตโนมัติภายใน ~15 นาที
- prod ต้องใช้ image **ตัวเดียวกับที่ผ่าน staging** (retag โดยไม่ build ใหม่) และ promote ด้วย PR ที่มีคน approve
- ทุกอย่างของเราใน cluster ต้องมาจาก Git (Argo CD เห็น drift และ self-heal ได้)
- rollback ให้ได้ภายใน 5 นาทีด้วย `git revert`
- deploy prod ต้องไม่ชนช่วงที่มีคาบเรียน

**ไม่ทำในรอบนี้**
- ให้ Argo CD ติดตั้ง K3s / Tailscale / OS (ยังเป็นงานของ Ansible เพราะ Argo CD ต้องมี cluster อยู่ก่อนถึงจะทำงานได้)
- Terraform ผ่าน GitOps (เพิ่มแค่ `terraform validate` ใน CI ได้ ส่วน plan / apply ยังทำด้วยมือ)
- pipeline ของ lab image ที่อาจารย์อัป (มีอยู่แล้ว: R2 → scan-runner → camp registry → ECR)
- scale backend เป็นหลาย replica (ติด C2 ต้องทำ leader election ก่อน ซึ่งใช้ Postgres advisory lock ได้โดยไม่ผิด Constraint 2)
- Argo Rollouts / canary (backend มี replica เดียวและใช้ hostNetwork ทำ canary ไม่ได้อยู่แล้ว)

---

## 3. ภาพรวม

```
 Developer ── PR ──┐
                   ▼
┌───────────────────────────────── GitHub (public repo) ───────────────────────────────────┐
│  PR checks (CI)                       push main                       tag vX.Y.Z           │
│  ├ Backend tests (มีแล้ว)             images.yml                       release.yml          │
│  ├ Frontend CI                        ├ build backend+frontend        ├ retag sha → vX.Y.Z │
│  ├ Images (build ไม่ push)            ├ Trivy (CRITICAL = fail)       ├ verify cosign      │
│  └ Deploy lint (kustomize+kubeconform)├ push ghcr.io/…:sha-abc1234     └ PR: overlays/prod  │
│                                       ├ cosign sign (keyless)            (คน approve+merge) │
│                                       └ bot commit → overlays/staging                      │
└──────────────────────────────────────────────▲───────────────────────────────────────────┘
                                               │ HTTPS ขาออกจาก cluster (poll ทุก 3 นาที)
┌──────────────────────────────── K3s cluster (บน Tailscale) ─────────────────────────────┐
│  ns argocd ── Argo CD ── sync ──┬─► cluster-config  (ns, NetworkPolicy, RBAC, NodePort)  │
│                                 ├─► sealed-secrets  (controller ใน kube-system)          │
│                                 ├─► siem            (ns siem-system)                     │
│                                 ├─► db-staging / web-portal-staging   (auto)             │
│                                 └─► db-prod    / web-portal-prod      (auto + sync window)│
│  kubelet ── pull image ──► ghcr.io  (ทาง internet ตรง ไม่ผ่าน VPN — Constraint 7)        │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Flow ของการเปลี่ยนแปลง 1 ครั้ง:
1. เปิด PR แล้วต้องผ่าน required checks (Pipeline doc ข้อ 3)
2. merge แล้ว `images.yml` จะ build backend และ frontend ที่ commit นั้น → push `ghcr.io/nawapatthumthaisong97/vlab-{backend,frontend}:sha-<7>` → Trivy → cosign จากนั้น bot commit tag ลง `deploy/apps/web-portal/overlays/staging/kustomization.yaml`
3. Argo CD เห็น commit แล้ว sync `web-portal-staging` ตามลำดับ: backup DB → migrate → Deployment ใหม่ → smoke test
4. เมื่อทดสอบบน staging ผ่าน ให้สร้าง tag `v1.4.0` ที่ commit นั้น `release.yml` จะ retag image และเปิด PR เปลี่ยน overlay ของ prod (pin ด้วย digest)
5. maintainer approve + merge แล้ว Argo CD จะ sync prod ทันทีถ้าอยู่นอก deny window ถ้าอยู่ใน window จะรอจนพ้นเวลาเรียนแล้วค่อย sync

---

## 4. Decisions

### D1 — ใช้ Argo CD แบบ pull แทนการ push จาก GitHub Actions

| ทางเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| A. Actions → `ansible-playbook` / `kubectl apply` (push) | ใช้ของเดิมได้ทันที | runner ต้องเข้า Tailscale (auth key ใน GitHub), ต้องถือ kubeconfig / SSH key ของ prod, ไม่เห็น drift |
| **B. Argo CD ใน cluster (pull)** | ไม่มี credential ของ cluster อยู่นอก cluster, ไม่เปิดพอร์ต, มี drift detection / self-heal / UI / ประวัติ sync | ต้องย้าย web-portal เข้า K8s และกิน RAM ~0.7–1 GB |
| C. Flux | เบากว่า Argo CD | ไม่มี UI ให้ทีม / อาจารย์ดู ซึ่งสำคัญกับโปรเจกต์นี้ |

**เลือก B** เพราะตรงกับ Constraint 1 และ 8 ที่สุด ส่วน UI ช่วยให้คนในทีมที่ไม่มี SSH ดูได้ว่าตอนนี้อะไรรันอยู่

### D2 — ย้าย web-portal เข้า K3s

Argo CD จัดการได้เฉพาะ resource ใน Kubernetes การปล่อยให้ web-portal เป็น compose บน VM จะได้ CI/CD แค่ครึ่งเดียว (ยังต้องมีคนรัน Ansible อยู่ดี)
การย้ายครั้งนี้ยังแก้ปัญหาข้อ 1.2 ข้อ 5 ด้วย (เปลี่ยนจาก kubeconfig admin เป็น ServiceAccount + RBAC)

### D3 — web-portal รันบน "platform node"

| ทางเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| **A. node ใหม่ (VM ที่เปิดตลอด) join เป็น K3s agent** ติด label `vlab.io/role=platform` + taint `vlab.io/dedicated=platform:NoSchedule` | แยกทรัพยากรจาก control-plane และเครื่องแลป, IP ของ portal คงที่ | ต้องแก้ backend ให้ข้าม node นี้ (C3) ซึ่งเป็นการแก้ 3 จุดเล็ก ๆ |
| B. รันบน master | ไม่ต้องแก้โค้ดเพราะ control-plane ถูกข้ามอยู่แล้ว | master รับ SkyPilot API + SIEM + scan Job (quota สูงสุด 4 CPU / 6 Gi) อยู่แล้ว ถ้าเพิ่ม backend + Postgres + Argo CD ไปอีก จะเสี่ยงให้ control-plane หน่วงทั้ง cluster และพอร์ต 80 ชนกับ svclb ของ Traefik |

**เลือก A** ถ้ามีเครื่อง (สเปกขั้นต่ำ 4 vCPU / 8 GB / disk 60 GB) ถ้าไม่มีเครื่องให้ใช้ B ชั่วคราว แต่ต้องปิด Traefik ของ k3s (`disable: [traefik]`) หรือย้ายพอร์ตของ frontend
taint จะกัน warm pod / prewarm DaemonSet ของ backend (ซึ่งใช้ affinity แค่ "ไม่ใช่ control-plane") และ svclb ไม่ให้ลงบน node นี้ ส่วนโค้ดที่ต้องแก้คือ `node_for_ip`, การ list worker ใน prewarm และ affinity ของ DaemonSet (Pipeline doc ข้อ 9)

### D4 — backend / frontend ใช้ `hostNetwork` + `Recreate`

เป้าหมายคือคงพฤติกรรมเดิมของ compose ไว้ทุกอย่าง และให้ตรงกับ เฟส 2D (nginx ต้องใช้ host network ด้วย ตามข้อ D4 ใน AWS_LAB_GATEWAY.md ข้อ 16.0)

```
เครื่องแลป (100.x.worker) ──Tailscale──► nginx  hostNetwork  listen <platform-ip>:80
                                          │  /api/ → proxy_pass http://127.0.0.1:8000
                                          │  X-Real-IP = $remote_addr (เขียนทับเสมอ)
                                          ▼
                                       uvicorn  hostNetwork  127.0.0.1:8000
                                          เชื่อ X-Real-IP เฉพาะเมื่อ peer = 127.0.0.1 (AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2A)
```

- ห้ามใช้ Service / Ingress / Traefik อยู่หน้า backend เพราะ kube-proxy และ svclb จะ SNAT ทำให้ C1 พัง
- ห้ามตั้ง trusted proxy เป็น pod CIDR (`10.42.0.0/16`) เพราะ pod ของ lab (โค้ดนักศึกษา, egress เปิดอยู่) จะยิง backend พร้อม `X-Real-IP` ปลอม แล้วได้ pod บนเครื่องของคนอื่นไป ต้องเชื่อแค่ `127.0.0.1` ซึ่งเป็นไปได้เพราะ nginx กับ backend อยู่ใน network namespace ของ host เดียวกัน
- `BIND_IP` ได้จาก downward API `status.hostIP` ซึ่งเท่ากับ Tailscale IP เพราะ k3s ติดตั้งด้วย `--node-ip {{ ansible_host }}` จึงไม่ต้องฮาร์ดโค้ด IP
- `Recreate` จำเป็น 2 เหตุผล คือ 2 pod ผูกพอร์ตเดียวกันบน host เดียวกันไม่ได้ และมี C2 ผลคือ **downtime ~20–40 วิ ต่อการ deploy** ซึ่งแก้ด้วย sync window (D10)

ถ้าต้องขึ้น staging ก่อนที่ เฟส 2A/2C จะเสร็จ (โหมดเดิม: frontend เรียก `http://<ip>:8000/api` ตรง) ทำได้ แต่ต้อง build frontend แยกต่อ env ด้วย build-arg ซึ่งผิดหลัก build ครั้งเดียว จึงแนะนำให้รอ 2A/2C ก่อน

### D5 — เก็บ image ของ platform ที่ GHCR

| ทางเลือก | เหตุผลที่ไม่เลือก / เลือก |
|---|---|
| camp registry (`:5002`) | เป็น HTTP ล้วนและอยู่บน tailnet ทำให้ runner ของ GitHub ต้องเข้า Tailscale และการ push ข้าม Tailscale ช้า (comment ใน `ansible/build-images.yml` บอก ~0.5 MB/s เพราะ RTT 132 ms) ควรเก็บไว้ใช้กับ lab image ตามเดิม |
| ECR | token หมดอายุทุก 12 ชม. K3s จึงต้องมี CronJob คอย refresh pull secret และมีค่า transfer |
| **GHCR (public package)** | repo เป็น public อยู่แล้ว จึงฟรีทั้ง storage และ bandwidth, push ด้วย `GITHUB_TOKEN` ได้เลย, K3s ดึงได้โดยไม่ต้องมี pull secret และดึงตรงทาง internet ตาม Constraint 7 |

ชื่อ image ต้องเป็นตัวเล็ก: `ghcr.io/nawapatthumthaisong97/vlab-backend` และ `…/vlab-frontend`
image ทั้งสองไม่มี secret อยู่ข้างใน (secret มาจาก env ตอนรัน) จึงเปิดเป็น public ได้ เพราะ source ก็ public อยู่แล้ว
scan-runner ยังอยู่กับ Ansible ไปก่อน แล้วย้ายมา GHCR ใน Phase 5 โดยใช้ `SCAN_RUNNER_IMAGE` override ได้

### D6 — ใช้ Kustomize กับแอปของเรา และ Helm กับของ third-party

- manifest ของเราเดิมเป็น YAML ล้วน (`k8s/`) Kustomize จึงต่อยอดได้ทันที และ Argo CD รองรับในตัว
- `kustomize edit set image` เป็นวิธีที่ CI ใช้แก้ tag ได้ง่ายที่สุด
- ของ third-party (argo-cd, sealed-secrets และ SkyPilot ในอนาคต) ใช้ Helm chart ที่ pin เวอร์ชัน

### D7 — เก็บ manifest ไว้ใน repo เดียวกันที่ `deploy/` และให้ bot commit tag ของ staging

| ทางเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| **A. mono-repo `deploy/`** | เพิ่ม env var ใหม่ได้ใน PR เดียวกับโค้ด (`backend.env` + `settings.py`), review พร้อมกัน, doc / code / manifest อยู่ที่เดียว | commit ของ bot ปนใน history ของ `main` และ bot ต้องได้สิทธิ์ bypass ruleset |
| B. repo แยก `vlab-gitops` | history สะอาด และ bot ไม่ต้อง bypass | เพิ่ม env var ทีต้องเปิด 2 PR แล้วประสานกัน ซึ่งพลาดบ่อยกับทีมเล็ก |

**เลือก A** โดยให้ bot (GitHub App `vlab-deploy-bot`) ทำได้แค่ push ไฟล์ `overlays/staging/kustomization.yaml` (workflow ตรวจ `git diff --name-only` ก่อน push) และ commit message ต้องมี `[skip ci]`
ส่วน prod จะ**ไม่มีทาง**เปลี่ยนได้โดยไม่ผ่าน PR + CODEOWNERS approve
ถ้า ruleset ของ repo ส่วนตัวใส่ GitHub App เป็น bypass actor ไม่ได้ ให้ใช้ deploy key (write) เป็น bypass actor แทน แล้วให้ bot push ผ่าน SSH

### D8 — Secret ใช้ Sealed Secrets

| ทางเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| **Sealed Secrets** | ไม่พึ่ง cloud, ฟรี, ใช้ง่าย (`kubeseal` + public cert ใน Git), ทำงานได้แม้เน็ตออกนอกไม่ได้ | ถ้า private key ของ controller หาย ต้อง seal ใหม่ทั้งหมด จึงต้อง backup |
| External Secrets + AWS SSM Parameter Store | rotate secret ที่เดียวได้ | ต้องมี IAM user / key ใหม่ใน cluster ซึ่งเป็นไก่กับไข่ และพึ่งพา AWS ตอนบูต |
| SOPS + KSOPS | ไฟล์ diff ได้ | ต้องติดตั้ง plugin ให้ repo-server ของ Argo CD ซึ่งซับซ้อนกว่า |

**เลือก Sealed Secrets** โดยค่าจริงยังเก็บในไฟล์ที่ gitignore (`ansible/group_vars/all.yml` สำหรับ prod และ `ansible/secrets/staging.yml` สำหรับ staging) แล้วใช้ `script/seal-secrets.py` แปลงโดยไม่เขียน plaintext ลง disk

### D9 — Postgres อยู่ใน cluster แยกเป็น Application ของตัวเอง

- ใช้ `StatefulSet` `postgres:17-alpine` (major เดียวกับตอนนี้) บน platform node และใช้ PVC `local-path` (มากับ k3s)
- แยกเป็น Application `db-<env>` ที่ใส่ `Prune=false,Delete=false` เพื่อกันไม่ให้การลบหรือย้ายแอปพาข้อมูลหายไปด้วย และใช้ app-of-apps wave ให้ DB ขึ้นก่อน web-portal
- backup มี 2 ชั้น: hook Job ทำ `pg_dump` ก่อน migrate ทุกครั้ง + CronJob ทุกคืน (เก็บใน PVC และส่งขึ้น S3 ได้)
- Grafana ของ SIEM อ่าน DB ผ่าน `postgres.vlab-prod.svc:5432` แทน Tailscale IP ทำให้ไม่ต้องเปิด DB บน Tailscale อีก (`DB_SIEM_BIND_IP` ไม่จำเป็นแล้ว)
- ภายหลังเปลี่ยนเป็น CloudNativePG ได้ถ้าต้องการ PITR แต่ไม่จำเป็นสำหรับรอบนี้

### D10 — 2 environment ใน cluster เดียว

| | `vlab-staging` | `vlab-prod` |
|---|---|---|
| trigger | ทุก merge เข้า `main` (bot commit) | tag `vX.Y.Z` → PR → merge |
| Argo CD sync | auto + prune + selfHeal | auto + prune + selfHeal **+ deny window ช่วงมีคาบ** (manual sync ได้สำหรับ hotfix) |
| image | `sha-<7>` | digest ของ `vX.Y.Z` |
| พอร์ตบน platform node | nginx `:8180`, uvicorn `127.0.0.1:8100` | nginx `:80`, uvicorn `127.0.0.1:8000` |
| DB | Postgres แยก (`db-staging`) | `db-prod` |
| namespace ของ lab | `vlab-staging-labs` | `default` (ตามเดิม) |
| scheduler | `PREWARM_ENABLED`, `WARM_POD_ENABLED`, `PRELAUNCH_ENABLED`, `LAB_IMAGE_SCAN_ENABLED`, `AWS_COST_EXPLORER_ENABLED` = **false** | ตามค่าใน `backend.env.j2` |
| SkyPilot | server กลางตัวเดียวกัน แต่ใช้ **service account token แยก** (`vlab-backend-staging`) ให้ audit ได้ | `vlab-backend` |
| เมล | `MAIL_REDIRECT_TO` = inbox ของทีม | ตามจริง |

ถ้าเครื่อง platform มี RAM ไม่พอ ให้ทำ staging ทีหลัง (Phase 3 ข้ามได้ แล้วให้ main ขึ้น prod โดยตรงผ่าน PR) แต่ไม่แนะนำ

### D11 — การเข้าถึง Argo CD

- `argocd-server` เป็น `NodePort 30808` ที่ platform node และเข้าได้เฉพาะ `autogroup:member` ตาม Tailscale ACL (tag:vlab-worker ซึ่งเป็นเครื่องนักศึกษาเข้าไม่ได้)
- ไม่เปิดผ่าน Cloudflare (ตาม Constraint 1) จนกว่าจะมี SSO
- Phase 5: เปิด Dex + Google SSO (`hd: dome.tu.ac.th`) แล้วปิด user `admin`, RBAC แบบ `role:readonly` เป็นค่าเริ่มต้น และให้ maintainer เป็น `role:admin`
- ปิด `exec.enabled` (web terminal) ไว้

### D12 — แบ่งความเป็นเจ้าของระหว่าง Ansible กับ Argo CD

กติกาคือ resource หนึ่งตัวต้องมีเจ้าของคนเดียว ถ้าสองฝ่าย apply ตัวเดียวกัน Argo CD self-heal กับ Ansible จะผลัดกันเขียนทับไม่จบ
ตอนย้ายความเป็นเจ้าของ ให้ลบ task ของ Ansible **ใน PR เดียวกัน**

| Resource | ตอนนี้ | หลังย้าย |
|---|---|---|
| OS, Tailscale, K3s, `registries.yaml`, `resolv.conf` ของ k3s, `coredns-custom` | Ansible | Ansible (ระดับ node) |
| camp registry, ecr-sync, scan-runner image, build lab image | Ansible | Ansible |
| SkyPilot Helm, ingress-nginx, cloudflared ของ SkyPilot | Ansible | Ansible (Phase 5 ค่อยพิจารณาย้ายเป็น Helm app) |
| Argo CD | — | Ansible ติดตั้งครั้งแรก (role ใหม่ `argocd`) |
| `skypilot-api-tailnet` Service | Ansible `skypilot-node` | Argo CD `cluster-config` |
| lab isolation NetworkPolicy (`default`, `skypilot`, `vlab-staging-labs`) | Ansible `k3s-server`, `skypilot-node` | Argo CD `cluster-config` |
| ns / quota / NetworkPolicy / PriorityClass ของ `vlab-scan` | Ansible `k3s-server` | Argo CD `cluster-config` (แทน `REGISTRY_IP` ด้วย kustomize patch) |
| Secret `registry-push` ใน `vlab-scan` | Ansible `k3s-server` | SealedSecret ใน `cluster-config` |
| SIEM ทั้ง 5 layer + secret | ทำมือ | Argo CD `siem` |
| web-portal + Postgres | Ansible `web-service` + compose | Argo CD `web-portal-*`, `db-*` |
| `k8s/auth/**` (oauth2-proxy) | ทำมือ | **ยังไม่ย้าย** เพราะซ้ำกับ backend ใน `vlab-prod` ต้องตัดสินใจก่อน (คำถามข้อ 11) |

---

## 5. Target state ใน cluster

### 5.1 Namespaces

| Namespace | เจ้าของ (Argo app) | มีอะไร |
|---|---|---|
| `argocd` | Ansible bootstrap | Argo CD |
| `kube-system` | `sealed-secrets` | sealed-secrets-controller (ชื่อต้องตรงค่า default ของ `kubeseal`) |
| `vlab-prod` | `db-prod`, `web-portal-prod` | postgres, backend, frontend, hook Job, backup CronJob |
| `vlab-staging` | `db-staging`, `web-portal-staging` | เหมือน prod แต่ปิด scheduler |
| `vlab-staging-labs` | `cluster-config` | pod lab ที่ staging สร้าง (มี NetworkPolicy isolation) |
| `default`, `skypilot` | (ns ไม่ใช่ของเรา) `cluster-config` ดูแลแค่ NetworkPolicy / Service | pod lab, warm pod |
| `vlab-scan` | `cluster-config` | Job สแกนของ backend prod |
| `siem-system` | `siem` | SIEM 5 layer |

### 5.2 Nodes

| Node | label / taint | รันอะไร |
|---|---|---|
| master (`tag:vlab-server`) | `node-role.kubernetes.io/control-plane` (k3s ใส่ให้เอง) | K3s API, SkyPilot API, SIEM layer 2–5, scan Job |
| **platform** (ใหม่, `tag:vlab-platform`) | label `vlab.io/role=platform`, taint `vlab.io/dedicated=platform:NoSchedule` | Argo CD, sealed-secrets, postgres ×2, backend ×2, frontend ×2 |
| เครื่องแลป (`tag:vlab-worker`) | (เดิม) | pod lab, warm pod, SIEM layer 1 (DaemonSet) |

ตัวอย่างเพิ่ม label + taint ตอน join ผ่าน Ansible (role `k3s-agent` ส่ง flag เพิ่มเฉพาะ host ใน group `platform`):

```
--node-label vlab.io/role=platform --node-taint vlab.io/dedicated=platform:NoSchedule
```

### 5.3 การเปลี่ยนแปลง network / Tailscale ACL

| จาก | ไป | พอร์ต | เหตุผล |
|---|---|---|---|
| `tag:vlab-worker` | `tag:vlab-platform` | tcp 80 | นักศึกษาในห้องแลปเปิด portal |
| `tag:vlab-worker` | `tag:vlab-platform` | udp 8472 | flannel VXLAN (เหมือนที่ worker ↔ server มีอยู่แล้ว) |
| `tag:vlab-platform` | `tag:vlab-server` | tcp 6443, 30880 | kube API และ SkyPilot API (C7) |
| `tag:vlab-platform` | `tag:vlab-worker`, `tag:vlab-server` | udp 8472, tcp 10250 | flannel + kubelet (ถ้าใส่ platform ใน `tag:vlab-server` แทน ก็ได้สิทธิ์ `*:*` อยู่แล้ว) |
| `tag:vlab-platform` | `tag:vlab-registry` | tcp 5001 | kubelet ดึง lab image (กรณีมี pod lab ลงที่นี่ ซึ่งปกติไม่มีเพราะ taint) |
| `autogroup:member` | `tag:vlab-platform` | 30808, 8180 | ทีมเปิด Argo CD UI และ staging |

ต้องเพิ่ม test case ใน `tailscale/vlab-acl.hujson.example` ด้วย เช่น worker ต้อง**เข้าไม่ได้** `tag:vlab-platform:30808`, `:8180` และ `:22`

### 5.4 ภาพ pod ของ web-portal บน platform node

```
platform node (Tailscale IP = P)
├── vlab-prod
│   ├── frontend   hostNetwork  nginx  P:80          /api/ → 127.0.0.1:8000
│   ├── backend    hostNetwork  uvicorn 127.0.0.1:8000  SA vlab-backend (RBAC แทน kubeconfig)
│   └── postgres   pod network  Service postgres:5432 (NetworkPolicy: ns ตัวเอง + siem grafana)
└── vlab-staging
    ├── frontend   hostNetwork  nginx  P:8180        /api/ → 127.0.0.1:8100
    ├── backend    hostNetwork  uvicorn 127.0.0.1:8100
    └── postgres   pod network  Service postgres:5432
```

backend ใช้ `dnsPolicy: ClusterFirstWithHostNet` เพื่อให้ resolve `postgres.vlab-prod.svc` ได้แม้จะอยู่บน host network

---

## 6. ความปลอดภัย

| เรื่อง | มาตรการ |
|---|---|
| credential ของ cluster | ไม่มีอยู่นอก cluster เลย เพราะ Argo CD เป็นฝ่ายดึง Git เอง (repo public จึงไม่ต้องมี repo credential) |
| สิทธิ์ของ backend | เปลี่ยนจาก kubeconfig admin เป็น ServiceAccount `vlab-backend` + ClusterRole (อ่าน nodes / namespaces / pods ทั้ง cluster) + Role ใน `default`, `vlab-scan` (สร้าง / ลบ pod, daemonset, deployment, job, secret) โดยรายการ verb มาจาก grep การเรียก API ใน `app/` (Pipeline doc ข้อ 7.3) |
| Argo CD | AppProject จำกัด source repo + destination namespace + cluster-scoped kind ที่อนุญาต, UI อยู่บน Tailscale เท่านั้น, ปิด exec, SSO ใน Phase 5 |
| GitHub Actions | `permissions:` ระบุทีละ job (ค่าเริ่มต้น `contents: read`), pin action ด้วย commit SHA, ใช้ `GITHUB_TOKEN` push GHCR (ไม่ใช้ PAT), cosign keyless ด้วย OIDC (ไม่มี private key ให้หลุด) |
| bot | GitHub App ที่ได้แค่ `contents: write` + `pull_requests: write` บน repo นี้ repo เดียว และ workflow ตรวจว่า bot แก้ได้เฉพาะ `overlays/staging/kustomization.yaml` |
| prod | CODEOWNERS ของ `deploy/**/overlays/prod/**` ต้อง approve, image pin ด้วย digest, release workflow ตรวจลายเซ็น cosign ก่อน retag |
| image | Trivy fail เมื่อเจอ CRITICAL ที่มี fix, SBOM + provenance แนบไปกับ image, ทุก base image pin version (และ digest ถ้าทำได้) |
| secret | ใน Git มีแค่ SealedSecret (scope `strict` คือผูกกับชื่อ + namespace), CI มี guard ห้าม `kind: Secret` ธรรมดาใน `deploy/`, private key ของ controller backup แยกไว้ offline |
| ช่องทาง X-Real-IP | backend เชื่อเฉพาะ peer `127.0.0.1` (D4) |

---

## 7. Rollback และ Disaster Recovery

| สถานการณ์ | ทำอย่างไร | เวลา |
|---|---|---|
| release ใหม่ใน prod พัง (โค้ด) | `git revert <commit ที่ bump prod>` → PR → merge แล้ว Argo CD sync กลับเอง (ถ้าอยู่ใน deny window ให้กด Sync เองเพราะ `manualSync: true`) | ~5 นาที |
| ต้องย้อนด่วนโดยไม่รอ PR | `argocd app rollback web-portal-prod <id>` ซึ่งจะปิด auto-sync ให้อัตโนมัติ ต้องตามด้วย revert ใน Git แล้วเปิด auto-sync คืน | ~1 นาที |
| migration ทำข้อมูลเสีย | ปิด auto-sync → scale backend เป็น 0 → `pg_restore` จาก dump ของ hook ล่าสุด (`/backups/presync-*.dump`) → revert release | 15–30 นาที |
| platform node ตาย | ติดตั้งเครื่องใหม่ด้วย Ansible (`k3s-agent` + label / taint) แล้ว Argo CD จะวาง pod ลงเอง ส่วน DB กู้จาก dump (CronJob ส่งขึ้น S3) | 1–2 ชม. |
| key ของ Sealed Secrets หาย | กู้จาก backup offline (`kubectl apply -f sealed-secrets-key.yaml` แล้ว restart controller) ถ้าไม่มี backup ต้องรัน `seal-secrets.py` ใหม่จากค่าใน group_vars | 15 นาที |
| Argo CD พัง | แอปที่รันอยู่ยังทำงานต่อได้ (Argo CD ไม่ได้อยู่บน data path) แล้วติดตั้งใหม่ด้วย Ansible role `argocd` ซึ่งจะ sync root app กลับมาเอง | 15 นาที |
| ช่วง cutover (Phase 4) | compose เดิม `stop` ไว้ ไม่ `down` และเก็บไว้ 2 สัปดาห์ ถ้าย้อนให้ scale แอปใน K3s เป็น 0 แล้ว `docker compose start` | 5 นาที |

กติกาของ migration (expand / contract) ต้องเขียนลงใน PR template:
1. release N: เพิ่ม column / table แบบ nullable หรือมี default โดยโค้ดเดิมต้องยังทำงานได้
2. release N+1: โค้ดเลิกใช้ของเก่า
3. release N+2: ค่อย drop ของเก่า
ห้าม rename / drop ใน release เดียวกับโค้ดที่เลิกใช้ เพราะตอน `Recreate` จะมีช่วงที่ backend ตัวเก่ารันบน schema ใหม่ และการ rollback ก็จะเจอแบบเดียวกัน

---

## 8. แผนลงมือ (Phases)

แต่ละ phase มี "ผ่านเมื่อ" ถ้ายังไม่ผ่านห้ามไป phase ถัดไป รายละเอียดไฟล์อยู่ใน Pipeline doc

| Phase | ทำอะไร | แตะ prod ไหม | ผ่านเมื่อ |
|---|---|---|---|
| **0 เตรียม** | อนุมัติ decision, ตอบคำถามข้อ 11, เตรียมเครื่อง platform, สร้าง GitHub App `vlab-deploy-bot`, เปิด ruleset ของ `main` (required checks + PR + bot bypass), CODEOWNERS | ไม่ | ruleset เป็น `active` และ PR ทดสอบถูกบังคับให้รอ check |
| **1 CI** | `frontend-ci.yml`, `images.yml` (build + push อย่างเดียว ยังไม่ bump), `deploy-lint.yml`, pin `KUBECTL_VERSION`, `.trivyignore` | ไม่ | ทุก commit บน main มี image `sha-*` บน GHCR พร้อมลายเซ็น และ check ทุกตัวเขียว |
| **2 Argo CD + platform apps** | Ansible role `argocd`, root app, `sealed-secrets`, `cluster-config` (ย้ายความเป็นเจ้าของจาก Ansible), `siem` (manual sync รอบแรก) | น้อย (NetworkPolicy ถูก apply ซ้ำด้วยเนื้อหาเดิม) | ทุก app เป็น `Synced/Healthy`, task ที่ย้ายถูกลบออกจาก Ansible แล้ว, รัน `site.yml` ซ้ำแล้วไม่เกิด diff ใน Argo CD |
| **3 staging** | AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2A / 2C (ข้อกำหนดก่อน), แก้โค้ด (in-cluster config, ข้าม platform node, nginx template), manifest `db-staging` + `web-portal-staging`, เปิดให้ bot bump | ไม่ (คนละ ns คนละพอร์ต) | merge แล้ว staging เปลี่ยนเองภายใน 15 นาที, hook smoke เขียว, whoami จาก worker ได้ `labMachine` |
| **4 prod cutover** | ประกาศช่วงปิดปรับปรุง (นอกคาบ) → `pg_dump` จาก compose → restore เข้า `db-prod` → ย้าย storage (หรือเปลี่ยนเป็น S3) → `docker compose stop` → sync `web-portal-prod` → ทดสอบ → เปลี่ยน URL / ACL | **ใช่** (downtime ~30 นาที) | ทดสอบตาม `docs/SETUP_TEST.md` ข้อ 3 ผ่าน (กด Start จากเครื่องแลป → K8s, จากข้างนอก → AWS), SIEM Grafana อ่าน DB ใหม่ได้ |
| **5 hardening** | Argo CD SSO + notifications, Renovate (pin action / chart / image), scan-runner ไป GHCR, ย้าย SkyPilot Helm เข้า Argo, ลบ role `web-service` และ compose | น้อย | ไม่มี deploy ไหนต้องพึ่ง SSH อีก |

ประมาณเวลา (ทีม 1–2 คน part-time): Phase 0–1 ~1 สัปดาห์, Phase 2 ~1 สัปดาห์, Phase 3 ~1–2 สัปดาห์ (ขึ้นกับ เฟส 2), Phase 4 ~1 วัน + เฝ้าดู 2 สัปดาห์

---

## 9. ความเสี่ยง

| ความเสี่ยง | โอกาส | ผลกระทบ | ลดอย่างไร |
|---|---|---|---|
| พอร์ต 80 บน platform node ถูก svclb ของ Traefik จองไว้ | กลาง | frontend ขึ้นไม่ได้ | taint จะกัน svclb ได้ แต่ต้องเช็กด้วย `kubectl get pods -A -o wide \| grep svclb` ถ้ายังมี ให้ติด label `svccontroller.k3s.cattle.io/enablelb=true` ที่ master เท่านั้น |
| node_for_ip นับ platform node เป็นเครื่องแลป | สูงถ้าไม่แก้โค้ด | prewarm รอ node ที่ไม่มีวันพร้อม | แก้โค้ด C3 ก่อน join node (Phase 3) |
| migration ไม่ backward compatible | กลาง | rollback ไม่ได้ | กติกา expand / contract + checklist ใน PR template + backup ก่อน migrate ทุกครั้ง |
| deploy ระหว่างคาบเรียน (downtime 20–40 วิ + scheduler หยุดชั่วคราว) | กลาง | นักศึกษากด Start ไม่ได้ / prelaunch พลาด | sync window ของ prod และ staging ไม่แตะ prod |
| staging ใช้เครื่องแลป / AWS จริง | กลาง | เปลืองเงิน / แย่งเครื่อง | ปิด scheduler, ใช้ namespace แยก, ใช้ SkyPilot token แยก, ใช้ AWS เฉพาะตอนเทสด้วยมือ |
| key ของ Sealed Secrets หาย | ต่ำ | ต้อง seal ใหม่ทั้งหมด | backup offline + ซ้อมกู้ใน Phase 2 |
| platform node เป็น single point of failure | — | portal ล่ม | เท่ากับตอนนี้ (VM เดียว) + backup DB ขึ้น S3 + กู้ด้วย Ansible |
| เครื่องเล็ก RAM ไม่พอ | กลาง | pod ถูก OOM | ปิด `dex` / `applicationSet` ของ Argo CD ที่ยังไม่ใช้, ตั้ง requests / limits ทุก pod, ดูด้วย `kubectl top` |
| bot ถูกใช้ในทางที่ผิด | ต่ำ | push อะไรก็ได้เข้า main | App ได้สิทธิ์แค่ repo เดียว, private key อยู่ใน Actions secret, workflow ตรวจไฟล์ก่อน push, ตรวจ audit log ได้ |

---

## 10. ตัวชี้วัดว่าสำเร็จ

- เวลาจาก merge จนถึง staging < 15 นาที (median)
- เวลาจาก approve PR ของ release จนถึง prod < 10 นาที (นอก deny window)
- rollback < 5 นาที
- deploy prod ที่ต้องมีคน SSH = 0
- drift ใน Argo CD (`OutOfSync` ที่ไม่ได้มาจาก Git) = 0 ต่อสัปดาห์

---

## 11. คำถามที่ต้องตอบก่อนเริ่ม

| # | คำถาม | ผลกับแผน |
|---|---|---|
| 1 | มีเครื่องที่เปิดตลอดสำหรับ platform node ไหม (สเปก / IP) หรือต้องใช้ master (D3) | ถ้าใช้ master ต้องปิด Traefik และเช็ก capacity |
| 2 | ตอนนี้ portal prod รันอยู่ที่ไหนจริง (`tailscale/vlab-tags.tsv.example` บอกว่าบางช่วงรันบน WSL ของคนในทีม) | ขั้นตอน cutover และ IP / URL ที่นักศึกษาใช้ |
| 3 | ใครเป็น maintainer ที่ approve release prod (CODEOWNERS) | ruleset / CODEOWNERS |
| 4 | ช่วงเวลาที่ห้าม deploy prod (คาบเรียนปกติ เช่น จ–ศ 08:00–18:00) | sync window |
| 5 | เฟส 2A / 2C จะเสร็จก่อน Phase 3 ไหม | ถ้าไม่ ต้องใช้โหมดชั่วคราว (build frontend ต่อ env) |
| 6 | ไฟล์เว็บจะยังเก็บบน disk หรือย้ายไป S3 (`STORAGE_BACKEND=s3`, `terraform/storage`) ตอน cutover | PVC `backend-storage` หรือไม่ต้องมี |
| 7 | `k8s/auth` (oauth2-proxy) ยังอยู่ในแผนไหม | ถ้าใช่ ต้องออกแบบ ingress ใหม่ให้ไม่ชนกับ C1 |
| 8 | แจ้งเตือน deploy ส่งไปที่ไหน (Discord / LINE / Slack) | config ของ notifications |
| 9 | staging ได้รับอนุญาตให้ launch EC2 จริงไหม | ถ้าไม่ ต้องเพิ่ม flag ปิด AWS ใน backend |
