# CI/CD ด้วย Argo CD — Pipeline

> สถานะ: **แผน ยังไม่ได้ลงมือ** (2026-11-09) — เหตุผลของแต่ละ decision (D1–D12) อยู่ใน [CICD_ARGOCD_SOLUTION.md](CICD_ARGOCD_SOLUTION.md)
> YAML ใน doc นี้เป็น**ร่างที่ตั้งใจให้ใช้ได้จริง** แต่ยังไม่ได้ commit เป็นไฟล์ใน `.github/` หรือ `deploy/` ให้ copy ไปทีละ phase
> เลขเวอร์ชันของ action / chart / tool ในนี้คือ major ณ วันที่เขียน ตอนลงมือให้ **pin action ด้วย commit SHA** และ pin chart / binary ด้วยเวอร์ชันเต็มที่ออกมาแล้วอย่างน้อย 2 สัปดาห์ (หลักเดียวกับ `skypilot_chart_version` ใน `group_vars`)
> ค่าในวงเล็บมุม เช่น `<PLATFORM_IP>`, `<MASTER_IP>`, `<REGISTRY_IP>` ให้ใส่ Tailscale IP จริงจาก `ansible/inventory.yml`

---

## 1. Stage ทั้งหมด

| # | Stage | Trigger | รันที่ | ทำอะไร | ล้มเมื่อ | เวลาโดยประมาณ |
|---|---|---|---|---|---|---|
| 1 | PR checks | `pull_request` | GitHub Actions | pytest (มีแล้ว), lint / test / build frontend, build image (ไม่ push), render + validate manifest | test / lint / build / schema ไม่ผ่าน | 5–12 นาที |
| 2 | Build & publish | push `main` ที่แตะ `web-portal/**` | GitHub Actions | build backend + frontend → Trivy → push GHCR `sha-<7>` → cosign sign | CRITICAL CVE ที่มี fix, build พัง | 6–10 นาที |
| 3 | Deploy staging | ต่อจาก 2 | Actions (bot commit) → Git → Argo CD | แก้ tag ใน overlay staging → Argo CD sync → hook (backup, migrate, smoke) | hook Job fail → Sync `Failed` | 3–5 นาที |
| 4 | Release | push tag `vX.Y.Z` | GitHub Actions | ตรวจลายเซ็น → retag `sha-<7>` เป็น `vX.Y.Z` (ไม่ build ใหม่) → เปิด PR pin digest ใน overlay prod | ไม่มี image ของ commit นั้น / ลายเซ็นไม่ตรง | ~2 นาที |
| 5 | Deploy prod | merge PR ของ release | Argo CD | sync เมื่ออยู่นอก deny window → hook (backup, migrate, smoke, whoami จากเครื่องแลป) | hook fail | 3–5 นาที |
| 6 | แจ้งผล | ผลการ sync / health เปลี่ยน | Argo CD Notifications | ส่งข้อความไปช่องของทีม | — | ทันที |

```
PR ──► [1 PR checks] ──merge──► [2 build/scan/push] ──► [3 bot bump staging] ──► Argo CD ──► vlab-staging
                                                                                     │ ทดสอบผ่าน
git tag vX.Y.Z ──► [4 retag + PR prod] ──approve+merge──► Argo CD (นอกเวลาเรียน) ──► vlab-prod ──► [6 แจ้งผล]
```

---

## 2. ไฟล์ที่จะเพิ่ม

```
.github/
  CODEOWNERS                              # deploy/**/overlays/prod/** ต้องให้ maintainer approve
  pull_request_template.md                # checklist migration / env / secret
  workflows/
    backend-tests.yml                     # มีแล้ว — แก้ trigger ให้เป็น required check ได้ (ข้อ 3.1)
    frontend-ci.yml                       # ใหม่ (ข้อ 3.2)
    images.yml                            # ใหม่ (ข้อ 4)
    deploy-lint.yml                       # ใหม่ (ข้อ 3.3)
    release.yml                           # ใหม่ (ข้อ 5)
    infra-lint.yml                        # ใหม่ ไม่บังคับ (ข้อ 3.4)
.trivyignore                              # CVE ที่ยอมรับ + เหตุผล + วันหมดอายุ
ansible/roles/argocd/                     # ใหม่ — ติดตั้ง Argo CD ครั้งแรก (ข้อ 6.1)
deploy/
  README.md                               # ชี้มาที่ doc นี้
  sealed-secrets/pub-cert.pem             # public cert ของ controller (commit ได้)
  argocd/
    bootstrap/root.yaml                   # Ansible apply ครั้งเดียว
    apps/                                 # ลูกของ root (app-of-apps)
      projects.yaml
      sealed-secrets.yaml
      cluster-config.yaml
      siem.yaml
      db-staging.yaml       db-prod.yaml
      web-portal-staging.yaml web-portal-prod.yaml
  platform/
    cluster-config/                       # ns, NetworkPolicy, vlab-scan, RBAC ของ backend, NodePort SkyPilot
    siem/                                 # อ้าง k8s/siem + SealedSecret + patch IP
  apps/
    postgres/
      base/                               # StatefulSet, Service, NetworkPolicy, PVC backup, CronJob
      overlays/{staging,prod}/
    web-portal/
      base/                               # backend, frontend, SA, PVC, hooks
      components/whoami-from-lab/         # PostSync จากเครื่องแลป (prod)
      components/grafana-ro/              # user grafana_ro ให้ SIEM (prod)
      overlays/{staging,prod}/            # kustomization (tag/digest), backend.env, frontend.env, *.sealed.yaml
k8s/siem/kustomization.yaml (+ ใน layer*/)  # ใหม่ — ลำดับ layer ด้วย sync-wave (ข้อ 7.7)
script/seal-secrets.py                    # ใหม่ — group_vars → SealedSecret (ข้อ 8.3)
```

---

## 3. CI บน Pull Request

### 3.1 `backend-tests.yml` (มีอยู่แล้ว) — แก้ 2 จุดก่อนเปิด ruleset

**จุดที่ 1: path filter ที่ระดับ trigger ทำให้ required check ค้าง**
ถ้า workflow ไม่ถูก trigger (PR ไม่ได้แตะ path) check จะไม่รายงานผลเลย และ PR จะรอไปตลอด
ให้ย้ายการกรองเข้าไปเป็น job `changes` แทน job ที่ถูกข้ามด้วย `if:` จะนับเป็นผ่านตามกฎของ GitHub

```yaml
on:
  pull_request:            # ไม่มี paths: แล้ว — กรองใน job changes
  push:
    branches: [main]
    paths: [...]           # คงไว้ตามเดิม (main ไม่มีปัญหา required check)
  workflow_dispatch:

jobs:
  changes:
    name: Detect backend changes
    runs-on: ubuntu-24.04
    outputs:
      backend: ${{ steps.filter.outputs.backend }}
    steps:
      - uses: actions/checkout@v5
      - id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            backend:
              - "web-portal/backend/**"
              - "web-portal/frontend/src/pages/AdminMonitor.tsx"
              - "web-portal/frontend/src/__tests__/AdminMonitor.test.tsx"
              - "k8s/siem/**"
              - "ansible/roles/siem-layer1-collector/**"
              - "script/test_siem_*.py"
              - ".github/workflows/backend-tests.yml"

  session:
    name: Sky launch & session tests      # ชื่อเดิม ห้ามเปลี่ยน (ruleset ผูกด้วยชื่อนี้)
    needs: changes
    if: needs.changes.outputs.backend == 'true' || github.event_name != 'pull_request'
    # ... steps เดิม ...
  # ทำแบบเดียวกันกับ course / prewarm / monitor / auth / lab_image
```

**จุดที่ 2: `tests/admin/` ไม่มี job ไหนรัน**
comment บนหัวไฟล์บอกว่า "มีโฟลเดอร์เทสใหม่ → เพิ่ม job ใหม่" แต่ `web-portal/backend/tests/admin/test_system_status.py` ยังไม่มี job ไหนรัน
ให้เพิ่ม job `Admin tests` (copy จาก `auth` แล้วเปลี่ยนเป็น `pytest tests/admin`)

### 3.2 `frontend-ci.yml` (ใหม่)

```yaml
# lint + test + build ของ frontend — ชื่อ job คือชื่อ required check
name: Frontend CI

on:
  pull_request:
  push:
    branches: [main]
    paths:
      - "web-portal/frontend/**"
      - ".github/workflows/frontend-ci.yml"

permissions:
  contents: read

jobs:
  changes:
    name: Detect frontend changes
    runs-on: ubuntu-24.04
    outputs:
      frontend: ${{ steps.filter.outputs.frontend }}
    steps:
      - uses: actions/checkout@v5
      - id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            frontend:
              - "web-portal/frontend/**"
              - ".github/workflows/frontend-ci.yml"

  frontend:
    name: Frontend lint, test & build
    needs: changes
    if: needs.changes.outputs.frontend == 'true' || github.event_name != 'pull_request'
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    defaults:
      run:
        working-directory: web-portal/frontend
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-node@v5
        with:
          node-version: "22"          # ตรงกับ node:22-alpine ใน Dockerfile
          cache: npm
          cache-dependency-path: web-portal/frontend/package-lock.json
      - run: npm ci
      - run: npm run lint             # oxlint
      - run: npm test                 # vitest run
      - run: npm run build            # tsc -b && vite build
        env:
          VITE_API_URL: /api          # relative ตาม AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2C
```

> ก่อนตั้งให้เป็น required check ให้รันบน `main` ดูก่อนว่าเขียวทั้ง lint และ test ถ้ายังแดง ให้แก้ก่อนหรือตั้งเป็น non-required ไปก่อน

### 3.3 `deploy-lint.yml` (ใหม่)

render ทุก overlay ด้วย Kustomize → ตรวจ schema ด้วย kubeconform → ตรวจกติกาของโปรเจกต์

```yaml
name: Deploy lint

on:
  pull_request:
  push:
    branches: [main]
    paths:
      - "deploy/**"
      - "k8s/**"
      - ".github/workflows/deploy-lint.yml"

permissions:
  contents: read

jobs:
  changes:
    name: Detect manifest changes
    runs-on: ubuntu-24.04
    outputs:
      deploy: ${{ steps.filter.outputs.deploy }}
    steps:
      - uses: actions/checkout@v5
      - id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            deploy:
              - "deploy/**"
              - "k8s/**"
              - ".github/workflows/deploy-lint.yml"

  render:
    name: Render & validate manifests
    needs: changes
    if: needs.changes.outputs.deploy == 'true' || github.event_name != 'pull_request'
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    env:
      KUSTOMIZE_VERSION: "5.7.1"      # ← ตรวจเลขล่าสุดตอนทำ
      KUBECONFORM_VERSION: "0.7.0"    # ← ตรวจเลขล่าสุดตอนทำ
      K8S_VERSION: "1.35.0"           # ตาม k3s_version ใน group_vars ถ้ายังไม่มี schema ของรุ่นนี้ ใช้ minor ก่อนหน้า
    steps:
      - uses: actions/checkout@v5

      - name: Install kustomize + kubeconform
        run: |
          set -euo pipefail
          curl -fsSL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv${KUSTOMIZE_VERSION}/kustomize_v${KUSTOMIZE_VERSION}_linux_amd64.tar.gz" \
            | sudo tar -xz -C /usr/local/bin kustomize
          curl -fsSL "https://github.com/yannh/kubeconform/releases/download/v${KUBECONFORM_VERSION}/kubeconform-linux-amd64.tar.gz" \
            | sudo tar -xz -C /usr/local/bin kubeconform

      - name: Render every app
        run: |
          set -euo pipefail
          mkdir -p rendered
          for dir in deploy/platform/* deploy/apps/*/overlays/*; do
            [ -f "$dir/kustomization.yaml" ] || continue
            out="rendered/$(echo "$dir" | tr '/' '_').yaml"
            echo "render $dir → $out"
            kustomize build "$dir" > "$out"
          done

      - name: Validate schemas
        run: |
          kubeconform -strict -summary \
            -kubernetes-version "$K8S_VERSION" \
            -schema-location default \
            -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
            rendered/ deploy/argocd/

      - name: Project guard rails
        run: |
          set -euo pipefail
          # 1) ห้าม Secret ธรรมดาใน Git — ต้องเป็น SealedSecret (Constraint 8)
          if grep -l -E '^kind:[[:space:]]*Secret[[:space:]]*$' rendered/*.yaml; then
            echo "::error::พบ kind: Secret ธรรมดา ให้ใช้ script/seal-secrets.py"; exit 1
          fi
          # 2) prod ต้อง pin digest ไม่ใช่ tag
          f=deploy/apps/web-portal/overlays/prod/kustomization.yaml
          if yq -e '.images[] | select(.digest == null)' "$f" >/dev/null 2>&1; then
            echo "::error::$f: image ของ prod ต้อง pin ด้วย digest (release.yml เขียนให้)"; exit 1
          fi
          # 3) backend ต้อง replicas 1 + Recreate (scheduler อยู่ใน process — Solution C2)
          for f in rendered/deploy_apps_web-portal_overlays_*.yaml; do
            yq -e 'select(.kind == "Deployment" and .metadata.name == "backend")
                   | (.spec.replicas == 1 and .spec.strategy.type == "Recreate")' "$f" >/dev/null \
              || { echo "::error::$f: backend ต้อง replicas: 1 + Recreate"; exit 1; }
          done
```

`yq` (mikefarah v4) ติดมากับ runner `ubuntu-24.04` อยู่แล้ว

### 3.4 `infra-lint.yml` (ใหม่ ไม่บังคับ)

```yaml
name: Infra lint
on:
  pull_request:
    paths: ["ansible/**", "terraform/**", ".github/workflows/infra-lint.yml"]
permissions:
  contents: read
jobs:
  ansible:
    name: Ansible syntax
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v5
      - run: pip install ansible-core
      - run: ansible-galaxy collection install ansible.posix
      - run: ansible-playbook -i ansible/inventory.yml.example ansible/site.yml --syntax-check
      - run: ansible-playbook -i ansible/inventory.yml.example ansible/build-images.yml --syntax-check
  terraform:
    name: Terraform validate
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v5
      - uses: hashicorp/setup-terraform@v3
      - run: terraform fmt -check -recursive terraform
      - run: terraform -chdir=terraform init -backend=false && terraform -chdir=terraform validate
```

### 3.5 Ruleset ของ `main` (Phase 0)

ตอนนี้ ruleset "PR to main" มี `enforcement: disabled` และ `main` ยังไม่ได้ protect ให้ตั้งค่าดังนี้:

| กฎ | ค่า |
|---|---|
| Require a pull request | 1 approval, dismiss stale approvals, require review from Code Owners |
| Required status checks | `Sky launch & session tests`, `Course & RBAC tests`, `Prewarm & class schedule tests`, `Monitor & SIEM telemetry tests`, `SSO & JWT auth tests`, `Lab image upload (R2) tests`, `Admin tests`, `Frontend lint, test & build`, `Images OK`, `Render & validate manifests` |
| Block force pushes / deletions | เปิด |
| Bypass list | GitHub App `vlab-deploy-bot` (ถ้า repo ส่วนตัวใส่ App ไม่ได้ ให้ใช้ deploy key แบบ write แทน) |

`.github/CODEOWNERS`:

```
# release prod ต้องให้ maintainer approve
/deploy/apps/web-portal/overlays/prod/   @<maintainer-1> @<maintainer-2>
/deploy/apps/postgres/overlays/prod/     @<maintainer-1> @<maintainer-2>
/deploy/argocd/                          @<maintainer-1>
/.github/workflows/                      @<maintainer-1>
```

---

## 4. Build & publish — `images.yml`

กติกา:
- บน `main` จะ build **ทั้ง backend และ frontend ทุกครั้ง** โดยใช้ tag `sha-<7>` เดียวกัน (มี layer cache จึงช้าเพิ่มแค่ ~1–2 นาที) ข้อดีคือ staging ได้คู่ backend / frontend ที่มาจาก commit เดียวกันเสมอ และไม่ต้องตามว่า commit ไหนเปลี่ยน component ไหน
- รันทีละรอบตามลำดับ push (`cancel-in-progress: false`) ถ้ามีรอบรอคิวอยู่แล้วมีรอบใหม่กว่าเข้ามา GitHub จะยกเลิกรอบที่รอให้เอง ไม่เป็นปัญหาเพราะรอบใหม่ build จาก tree ล่าสุดที่รวมทุกอย่างแล้ว ทำให้ staging ไม่มีทางถอยไปใช้ tag เก่า
- บน PR จะ build + scan แต่ไม่ push เพื่อจับ Dockerfile พังก่อน merge

```yaml
# build image ของ web-portal → GHCR → bump staging overlay
# image ที่ build บน main คือ artifact ตัวเดียวที่ใช้ทั้ง staging และ prod (prod แค่ retag ใน release.yml)
name: Images

on:
  pull_request:
  push:
    branches: [main]
    paths:
      - "web-portal/backend/**"
      - "web-portal/frontend/**"
      - ".github/workflows/images.yml"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: images-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  changes:
    name: Detect image changes
    runs-on: ubuntu-24.04
    outputs:
      web: ${{ steps.filter.outputs.web }}
    steps:
      - uses: actions/checkout@v5
      - id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            web:
              - "web-portal/backend/**"
              - "web-portal/frontend/**"
              - ".github/workflows/images.yml"

  build:
    name: Build ${{ matrix.component }} image
    needs: changes
    if: needs.changes.outputs.web == 'true' || github.event_name != 'pull_request'
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    permissions:
      contents: read
      packages: write          # push GHCR ด้วย GITHUB_TOKEN
      id-token: write          # cosign keyless (OIDC) — ไม่มี private key ให้หลุด
    strategy:
      fail-fast: false
      matrix:
        component: [backend, frontend]
    env:
      PUSH: ${{ github.event_name != 'pull_request' }}
    steps:
      - uses: actions/checkout@v5

      - name: Resolve image name and tag
        run: |
          # GHCR ต้องเป็นตัวเล็ก — owner คือ NawapatThumthaisong97
          echo "IMAGE=ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/vlab-${{ matrix.component }}" >> "$GITHUB_ENV"
          echo "TAG=sha-${GITHUB_SHA::7}" >> "$GITHUB_ENV"

      - uses: docker/setup-buildx-action@v3

      - if: env.PUSH == 'true'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE }}
          tags: |
            type=raw,value=${{ env.TAG }}
            type=raw,value=main,enable=${{ github.ref == 'refs/heads/main' }}
          labels: |
            org.opencontainers.image.title=vlab-${{ matrix.component }}

      - id: build
        uses: docker/build-push-action@v6
        with:
          context: web-portal/${{ matrix.component }}
          platforms: linux/amd64
          push: ${{ env.PUSH == 'true' }}
          load: ${{ env.PUSH != 'true' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          # backend : pin kubectl ให้ตรง k3s_version (ไม่ส่ง = Dockerfile ดึง stable ล่าสุด build ไม่ซ้ำเดิม)
          # frontend: API แบบ relative (AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2C) → image เดียวใช้ได้ทุก env
          # ARG ที่ Dockerfile ไม่ได้ประกาศจะถูกเตือนแล้วข้ามไป ไม่ทำให้ build พัง
          build-args: |
            KUBECTL_VERSION=v1.35.5
            VITE_API_URL=/api
            VITE_SIEM_GRAFANA_URL=${{ vars.VITE_SIEM_GRAFANA_URL }}
          cache-from: type=gha,scope=${{ matrix.component }}
          cache-to: type=gha,mode=max,scope=${{ matrix.component }}
          provenance: ${{ env.PUSH == 'true' && 'mode=max' || 'false' }}
          sbom: ${{ env.PUSH == 'true' }}

      # main: push ไปแล้วก่อน scan — ถ้า scan ล้ม image จะค้างอยู่ใน GHCR แต่ไม่ถูก bump เข้า staging
      - name: Scan (Trivy) — CRITICAL ที่มี fix = fail
        uses: aquasecurity/trivy-action@<PIN_SHA>
        with:
          image-ref: ${{ env.IMAGE }}:${{ env.TAG }}
          severity: CRITICAL
          ignore-unfixed: true
          exit-code: "1"
          trivyignores: .trivyignore

      - if: env.PUSH == 'true'
        uses: sigstore/cosign-installer@v3

      - if: env.PUSH == 'true'
        name: Sign image (keyless)
        run: cosign sign --yes "${IMAGE}@${{ steps.build.outputs.digest }}"

  bump-staging:
    name: Bump staging overlay
    needs: build
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      # push ด้วย token ของ App (ไม่ใช้ GITHUB_TOKEN) เพราะ App อยู่ใน bypass list ของ ruleset
      - id: app
        uses: actions/create-github-app-token@v2
        with:
          app-id: ${{ vars.DEPLOY_BOT_APP_ID }}
          private-key: ${{ secrets.DEPLOY_BOT_PRIVATE_KEY }}

      - uses: actions/checkout@v5
        with:
          ref: main
          token: ${{ steps.app.outputs.token }}

      - name: Set image tags in staging overlay
        run: |
          set -euo pipefail
          export TAG="sha-${GITHUB_SHA::7}"
          f=deploy/apps/web-portal/overlays/staging/kustomization.yaml
          yq -i '(.images[] | select(.name == "vlab-backend" or .name == "vlab-frontend")).newTag = strenv(TAG)' "$f"
          git diff --stat

      - name: Commit and push (bot แก้ได้ไฟล์เดียวเท่านั้น)
        env:
          APP_SLUG: ${{ steps.app.outputs.app-slug }}
        run: |
          set -euo pipefail
          f=deploy/apps/web-portal/overlays/staging/kustomization.yaml
          changed="$(git diff --name-only)"
          if [ -z "$changed" ]; then echo "staging ใช้ tag นี้อยู่แล้ว"; exit 0; fi
          if [ "$changed" != "$f" ]; then echo "::error::bot แก้ไฟล์อื่น: $changed"; exit 1; fi
          git config user.name  "${APP_SLUG}[bot]"
          git config user.email "${APP_SLUG}[bot]@users.noreply.github.com"
          git commit -m "chore(deploy): staging → sha-${GITHUB_SHA::7} [skip ci]" -- "$f"
          for i in 1 2 3; do
            git push origin HEAD:main && exit 0
            git pull --rebase origin main
          done
          echo "::error::push ไม่สำเร็จหลังลอง 3 รอบ"; exit 1

  # required check ตัวเดียวของ workflow นี้ — job matrix ที่ถูกข้ามด้วย if: จะรายงานชื่อแบบยังไม่แทนค่า
  # ("Build ${{ matrix.component }} image") ทำให้ผูกชื่อ "Build backend image" เป็น required check ไม่ได้
  images-ok:
    name: Images OK
    needs: [changes, build]
    if: always()
    runs-on: ubuntu-24.04
    steps:
      - name: All image builds passed or were not needed
        run: |
          [ "${{ needs.changes.result }}" = "success" ] || exit 1
          case "${{ needs.build.result }}" in success|skipped) ;; *) exit 1;; esac
```

ตั้งค่าที่ต้องทำครั้งเดียว:
- **GHCR**: ครั้งแรกที่ push แล้ว package อาจถูกตั้งเป็น private ให้เข้าไปที่ Package settings → Change visibility → Public และ "Manage Actions access" ให้ repo นี้ได้ `Write` (K3s จะดึงได้โดยไม่ต้องมี pull secret)
- **GitHub App `vlab-deploy-bot`**: ติดตั้งบน repo นี้ repo เดียว สิทธิ์ `Contents: Read & write`, `Pull requests: Read & write` แล้วเก็บ App ID ไว้ใน repo variable `DEPLOY_BOT_APP_ID` และ private key ไว้ใน secret `DEPLOY_BOT_PRIVATE_KEY`
- **repo variable** `VITE_SIEM_GRAFANA_URL` เช่น `http://<MASTER_IP>:30300`
- **`.trivyignore`**: ทุกบรรทัดต้องมี comment บอกเหตุผลและวันที่จะกลับมาดู
- (ไม่บังคับ) ลบ tag `sha-*` เก่าด้วย `actions/delete-package-versions` ที่ตั้งให้เก็บ 30 version ล่าสุด และห้ามลบ `v*`

---

## 5. Promote to prod — `release.yml`

ขั้นตอนของคน:
1. ดูใน Argo CD ว่า `web-portal-staging` ใช้ `sha-abc1234` อะไร และทดสอบบน staging (`http://<PLATFORM_IP>:8180`) ผ่านแล้ว
2. `git tag v1.4.0 abc1234 && git push origin v1.4.0`
3. workflow จะเปิด PR "release: v1.4.0 → prod" ให้ maintainer review checklist แล้ว approve + merge
4. Argo CD จะ sync เองเมื่อพ้น deny window ถ้าเป็นเรื่องด่วนดูข้อ 10.3

```yaml
# tag vX.Y.Z → retag image ที่ผ่าน staging แล้ว (ไม่ build ใหม่) → เปิด PR pin digest ใน prod overlay
name: Release

on:
  push:
    tags: ["v*.*.*"]

permissions:
  contents: read

concurrency:
  group: release
  cancel-in-progress: false

jobs:
  promote:
    name: Promote ${{ github.ref_name }} to prod
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: read
      packages: write          # crane tag
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Tag must point at a commit on main
        run: git merge-base --is-ancestor "$GITHUB_SHA" origin/main

      - name: Resolve
        run: |
          echo "OWNER=${GITHUB_REPOSITORY_OWNER,,}" >> "$GITHUB_ENV"
          echo "SRC_TAG=sha-${GITHUB_SHA::7}" >> "$GITHUB_ENV"

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: sigstore/cosign-installer@v3
      - uses: imjasonh/setup-crane@v0.4

      - name: Verify signature and retag (no rebuild)
        run: |
          set -euo pipefail
          : > /tmp/digests
          for c in backend frontend; do
            repo="ghcr.io/${OWNER}/vlab-${c}"
            digest="$(crane digest "${repo}:${SRC_TAG}")"   # ไม่มี = commit นี้ไม่เคย build ผ่าน → fail
            # ต้องถูก sign โดย images.yml บน main เท่านั้น (ไม่ใช่ fork / branch อื่น)
            cosign verify "${repo}@${digest}" \
              --certificate-oidc-issuer https://token.actions.githubusercontent.com \
              --certificate-identity "https://github.com/${GITHUB_REPOSITORY}/.github/workflows/images.yml@refs/heads/main" \
              > /dev/null
            crane tag "${repo}@${digest}" "${GITHUB_REF_NAME}"
            echo "${c} ${digest}" >> /tmp/digests
          done
          cat /tmp/digests

      - id: app
        uses: actions/create-github-app-token@v2
        with:
          app-id: ${{ vars.DEPLOY_BOT_APP_ID }}
          private-key: ${{ secrets.DEPLOY_BOT_PRIVATE_KEY }}

      - name: Pin prod overlay to digests (on top of latest main)
        run: |
          set -euo pipefail
          git checkout -B release-work origin/main
          f=deploy/apps/web-portal/overlays/prod/kustomization.yaml
          while read -r c digest; do
            export NAME="vlab-${c}" DIGEST="${digest}"
            yq -i '(.images[] | select(.name == strenv(NAME))) |= (.digest = strenv(DIGEST) | del(.newTag))' "$f"
          done < /tmp/digests
          yq -i '.commonAnnotations."vlab.io/release" = strenv(GITHUB_REF_NAME)' "$f"
          git diff

      # ใช้ token ของ App — PR ที่เปิดด้วย GITHUB_TOKEN จะไม่ trigger workflow (required check จะไม่รัน)
      - uses: peter-evans/create-pull-request@v7
        with:
          token: ${{ steps.app.outputs.token }}
          base: main
          branch: release/${{ github.ref_name }}
          add-paths: deploy/apps/web-portal/overlays/prod/kustomization.yaml
          commit-message: "chore(deploy): prod → ${{ github.ref_name }}"
          title: "release: ${{ github.ref_name }} → prod"
          labels: release
          body: |
            Promote `sha-${{ github.sha }}` (ผ่าน staging แล้ว) เป็น **${{ github.ref_name }}** บน prod
            image ถูก retag (ไม่ได้ build ใหม่) และ pin ด้วย digest ตรวจลายเซ็น cosign แล้ว

            - [ ] staging ใช้ commit นี้แล้ว และ smoke / ทดสอบมือผ่าน
            - [ ] migration ใน release นี้เป็น expand-only (backend ตัวเก่ายังรันบน schema ใหม่ได้)
            - [ ] env var ใหม่ใส่ใน `overlays/prod/backend.env` แล้ว / secret ใหม่ seal แล้ว
            - [ ] merge นอกเวลาเรียน หรือยอมให้ Argo CD รอจนพ้น deny window
```

---

## 6. Argo CD

### 6.1 Ansible role `argocd` (bootstrap ครั้งเดียว)

`ansible/site.yml` เพิ่ม play นี้หลัง play ของ master (ต้องมี K3s และ platform node แล้ว)

```yaml
- name: Bootstrap Argo CD
  hosts: master
  become: yes
  roles:
    - { role: argocd, tags: ['argocd'] }
```

`ansible/roles/argocd/defaults/main.yml`

```yaml
argocd_namespace: argocd
# stable เท่านั้น: helm search repo argo/argo-cd --versions แล้วเลือกตัวบนสุดที่ไม่ใช่ rc และออกมาแล้ว ≥ 2 สัปดาห์
argocd_chart_version: "<ARGOCD_CHART_VERSION>"
argocd_node_port: 30808
argocd_repo_url: https://github.com/NawapatThumthaisong97/VirtualLabtest.git
```

`ansible/roles/argocd/tasks/main.yml`

```yaml
- name: Add Argo Helm repo
  ansible.builtin.command: helm repo add argo https://argoproj.github.io/argo-helm --force-update
  environment: { KUBECONFIG: /etc/rancher/k3s/k3s.yaml }
  changed_when: false

- name: Render Argo CD values
  ansible.builtin.template:
    src: values.yaml.j2
    dest: /etc/rancher/k3s/argocd-values.yaml
    mode: "0600"

- name: Install / upgrade Argo CD
  ansible.builtin.command: >-
    helm upgrade --install argocd argo/argo-cd
    --version {{ argocd_chart_version }}
    --namespace {{ argocd_namespace }} --create-namespace
    -f /etc/rancher/k3s/argocd-values.yaml
    --wait --timeout 10m
  environment: { KUBECONFIG: /etc/rancher/k3s/k3s.yaml }
  changed_when: true    # helm ไม่บอกว่ามีอะไรเปลี่ยนจริงหรือไม่

# ครั้งเดียว ที่เหลือ (projects + app ลูก) root app ดึงจาก Git เอง
- name: Apply root Application
  ansible.builtin.shell: |
    cat <<'YAML' | k3s kubectl apply -f -
    {{ lookup('file', playbook_dir + '/../deploy/argocd/apps/projects.yaml') }}
    ---
    {{ lookup('file', playbook_dir + '/../deploy/argocd/bootstrap/root.yaml') }}
    YAML
  register: root_app
  changed_when: "'unchanged' not in root_app.stdout"
```

`ansible/roles/argocd/templates/values.yaml.j2`

```yaml
global:
  # ให้ Argo CD อยู่บน platform node ด้วย เพื่อให้ control-plane เบาลง
  nodeSelector:
    vlab.io/role: platform
  tolerations:
    - { key: vlab.io/dedicated, operator: Equal, value: platform, effect: NoSchedule }

configs:
  params:
    server.insecure: true            # ไม่มี TLS ใน cluster — เข้าได้ผ่าน Tailscale (WireGuard) เท่านั้น
  cm:
    timeout.reconciliation: 180s     # poll Git ทุก ~3 นาที (ไม่ใช้ webhook เพราะต้องเปิดพอร์ตขาเข้า)
    exec.enabled: "false"
    admin.enabled: "true"            # ปิดหลังเปิด SSO (Phase 5)
    # ให้ app-of-apps รอ app ลูกที่ wave ก่อนหน้า Healthy ก่อน (ค่าเริ่มต้นของ Argo CD ไม่ประเมิน health ของ Application)
    resource.customizations.health.argoproj.io_Application: |
      hs = {}
      hs.status = "Progressing"
      hs.message = ""
      if obj.status ~= nil then
        if obj.status.health ~= nil then
          hs.status = obj.status.health.status
          if obj.status.health.message ~= nil then
            hs.message = obj.status.health.message
          end
        end
      end
      return hs
  rbac:
    policy.default: role:readonly

server:
  service:
    type: NodePort
    nodePortHttp: {{ argocd_node_port }}

dex:
  enabled: false                     # เปิดตอนทำ Google SSO (Phase 5)

notifications:
  enabled: true                      # config อยู่ข้อ 6.5
```

เข้า UI ครั้งแรก:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
```

```bash
argocd login <PLATFORM_IP>:30808 --plaintext --username admin
```

```bash
argocd account update-password
```

```bash
kubectl -n argocd delete secret argocd-initial-admin-secret
```

### 6.2 AppProjects — `deploy/argocd/apps/projects.yaml`

```yaml
# vlab-root: app-of-apps สร้างได้เฉพาะ Application / AppProject ใน ns argocd
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: vlab-root
  namespace: argocd
spec:
  sourceRepos: ["https://github.com/NawapatThumthaisong97/VirtualLabtest.git"]
  destinations:
    - { server: https://kubernetes.default.svc, namespace: argocd }
  clusterResourceWhitelist: []
  namespaceResourceWhitelist:
    - { group: argoproj.io, kind: Application }
    - { group: argoproj.io, kind: AppProject }
---
# vlab-platform: ของระดับ cluster (ns, NetworkPolicy, RBAC, sealed-secrets, SIEM)
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: vlab-platform
  namespace: argocd
spec:
  sourceRepos:
    - https://github.com/NawapatThumthaisong97/VirtualLabtest.git
    - https://bitnami-labs.github.io/sealed-secrets
  destinations:
    - { server: https://kubernetes.default.svc, namespace: kube-system }
    - { server: https://kubernetes.default.svc, namespace: default }
    - { server: https://kubernetes.default.svc, namespace: skypilot }
    - { server: https://kubernetes.default.svc, namespace: vlab-scan }
    - { server: https://kubernetes.default.svc, namespace: vlab-staging-labs }
    - { server: https://kubernetes.default.svc, namespace: siem-system }
  clusterResourceWhitelist:
    - { group: "", kind: Namespace }
    - { group: rbac.authorization.k8s.io, kind: ClusterRole }
    - { group: rbac.authorization.k8s.io, kind: ClusterRoleBinding }
    - { group: scheduling.k8s.io, kind: PriorityClass }
    - { group: apiextensions.k8s.io, kind: CustomResourceDefinition }   # CRD ของ SealedSecret
---
# vlab-apps: web-portal + postgres — namespaced เท่านั้น
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: vlab-apps
  namespace: argocd
spec:
  sourceRepos: ["https://github.com/NawapatThumthaisong97/VirtualLabtest.git"]
  destinations:
    - { server: https://kubernetes.default.svc, namespace: vlab-staging }
    - { server: https://kubernetes.default.svc, namespace: vlab-prod }
  clusterResourceWhitelist: []
  namespaceResourceBlacklist:
    - { group: "", kind: ResourceQuota }
    - { group: "", kind: LimitRange }
  syncWindows:
    # ห้าม sync prod ช่วงมีคาบ (auto-sync จะรอจนพ้น window) — hotfix กด Sync เองได้
    - kind: deny
      schedule: "0 8 * * 1-5"        # จ–ศ 08:00
      duration: 10h                  # ถึง 18:00 — ปรับตามคำตอบคำถามข้อ 4 ใน Solution doc
      timeZone: Asia/Bangkok
      applications: ["web-portal-prod", "db-prod"]
      manualSync: true
```

### 6.3 Applications

`deploy/argocd/bootstrap/root.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
spec:
  project: vlab-root
  source:
    repoURL: https://github.com/NawapatThumthaisong97/VirtualLabtest.git
    targetRevision: main
    path: deploy/argocd/apps
  destination: { server: https://kubernetes.default.svc, namespace: argocd }
  syncPolicy:
    automated: { prune: true, selfHeal: true }
```

ลำดับใน app-of-apps (ใช้ `argocd.argoproj.io/sync-wave` กับ Application แต่ละตัว):

| wave | Application | project | path / chart | finalizer | sync |
|---|---|---|---|---|---|
| -3 | `sealed-secrets` | vlab-platform | chart `sealed-secrets` | **ไม่มี** (ลบ app แล้ว CRD หาย → SealedSecret + Secret หายทั้ง cluster) | auto |
| -2 | `cluster-config` | vlab-platform | `deploy/platform/cluster-config` | ไม่มี | auto |
| -1 | `siem` | vlab-platform | `deploy/platform/siem` | **ไม่มี** (ลบ app แล้ว ns `siem-system` + ข้อมูล NATS / VictoriaLogs จะหายไปด้วย) | manual ในรอบแรก แล้วค่อยเปิด auto |
| 0 | `db-staging`, `db-prod` | vlab-apps | `deploy/apps/postgres/overlays/<env>` | **ไม่มี** | auto (prod อยู่ใต้ deny window) |
| 1 | `web-portal-staging`, `web-portal-prod` | vlab-apps | `deploy/apps/web-portal/overlays/<env>` | มี | auto (prod อยู่ใต้ deny window) |

`deploy/argocd/apps/sealed-secrets.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sealed-secrets
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-3"
spec:
  project: vlab-platform
  source:
    repoURL: https://bitnami-labs.github.io/sealed-secrets
    chart: sealed-secrets
    targetRevision: "<SEALED_SECRETS_CHART_VERSION>"
    helm:
      valuesObject:
        fullnameOverride: sealed-secrets-controller   # ชื่อที่ kubeseal หาเป็นค่าเริ่มต้น
        nodeSelector: { vlab.io/role: platform }
        tolerations:
          - { key: vlab.io/dedicated, operator: Equal, value: platform, effect: NoSchedule }
  destination: { server: https://kubernetes.default.svc, namespace: kube-system }
  syncPolicy:
    automated: { prune: false, selfHeal: true }
    syncOptions: [ServerSideApply=true]
```

`deploy/argocd/apps/web-portal-prod.yaml` (ตัว staging เหมือนกัน เปลี่ยนแค่ชื่อ / path / namespace และเพิ่ม `retry`)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: web-portal-prod
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"
  finalizers: [resources-finalizer.argocd.argoproj.io]
spec:
  project: vlab-apps
  source:
    repoURL: https://github.com/NawapatThumthaisong97/VirtualLabtest.git
    targetRevision: main
    path: deploy/apps/web-portal/overlays/prod
  destination: { server: https://kubernetes.default.svc, namespace: vlab-prod }
  revisionHistoryLimit: 20
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions:
      - CreateNamespace=false      # ns มาจาก cluster-config
      - PruneLast=true
    # prod ไม่ตั้ง retry — migration / smoke ล้มต้องให้คนดู ไม่ให้วนซ้ำเอง
```

`deploy/argocd/apps/db-prod.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: db-prod
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "0"
  # ไม่มี finalizer: ลบ Application นี้ (เช่น ย้ายไฟล์ผิด) ต้องไม่ลบ StatefulSet / PVC ของ DB
spec:
  project: vlab-apps
  source:
    repoURL: https://github.com/NawapatThumthaisong97/VirtualLabtest.git
    targetRevision: main
    path: deploy/apps/postgres/overlays/prod
  destination: { server: https://kubernetes.default.svc, namespace: vlab-prod }
  syncPolicy:
    automated: { prune: false, selfHeal: true }
```

### 6.4 สรุปพฤติกรรม sync

| สถานการณ์ | staging | prod |
|---|---|---|
| merge โค้ด | bot bump → sync ภายใน ~3 นาที | ไม่มีอะไรเกิดขึ้น (prod pin digest ไว้) |
| merge PR release ระหว่างคาบ | — | `OutOfSync` แล้วรอจนพ้น 18:00 จึงค่อย sync เอง |
| มีคนแก้ของใน cluster ด้วยมือ (`kubectl edit`) | self-heal คืนตาม Git | self-heal คืนตาม Git (ใน deny window จะยังไม่คืนจนพ้น window) |
| hook ล้ม | Sync `Failed`, retry 2 ครั้ง, แจ้งเตือน | Sync `Failed`, แจ้งเตือน, ของเก่ายังรันอยู่ถ้าล้มที่ backup / migrate |

ถ้า hook ล้ม**ก่อน** wave ของ Deployment (backup / migrate) backend ตัวเก่าจะยังรันอยู่เพราะ Argo CD ไม่ไปต่อ wave ถัดไป
ถ้าล้มที่ **PostSync** (smoke) แปลว่า Deployment ใหม่ขึ้นไปแล้ว ให้ดูข้อ 10.4

### 6.5 Notifications

ค่าใน Helm values (`notifications:`) ส่วน webhook URL เก็บใน SealedSecret `argocd-notifications-secret` (key `discord-webhook-url`) ถ้าทีมใช้ Slack / LINE ให้เปลี่ยน service ตาม doc ของ Argo CD Notifications

```yaml
notifications:
  enabled: true
  secret:
    create: false                    # มาจาก SealedSecret
  notifiers:
    service.webhook.discord: |
      url: $discord-webhook-url
      headers:
        - name: Content-Type
          value: application/json
  templates:
    template.app-sync-status: |
      webhook:
        discord:
          method: POST
          body: |
            {"content": "[{{.app.metadata.name}}] sync {{.app.status.operationState.phase}} · health {{.app.status.health.status}} · rev {{.app.status.sync.revision | trunc 7}}"}
  triggers:
    trigger.on-sync-succeeded: |
      - when: app.status.operationState != nil and app.status.operationState.phase in ['Succeeded']
        oncePer: app.status.operationState.syncResult.revision
        send: [app-sync-status]
    trigger.on-sync-failed: |
      - when: app.status.operationState != nil and app.status.operationState.phase in ['Error', 'Failed']
        send: [app-sync-status]
    trigger.on-health-degraded: |
      - when: app.status.health.status == 'Degraded'
        send: [app-sync-status]
  subscriptions:
    - recipients: [discord]
      triggers: [on-sync-succeeded, on-sync-failed, on-health-degraded]
```

(ไม่บังคับ) ใช้ service `github` ของ Notifications กับ GitHub App เดิม เพื่อเขียน commit status / deployment กลับไปที่ commit จะได้เห็นใน PR ว่า commit นั้นขึ้น staging / prod แล้ว

---

## 7. Manifests

### 7.1 `deploy/platform/cluster-config/`

```yaml
# kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespaces.yaml                       # vlab-prod, vlab-staging, vlab-staging-labs
  - lab-isolation.yaml                    # NetworkPolicy เดิม × 3 ns (default, skypilot, vlab-staging-labs)
  - scan-namespace.yaml                   # ย้ายมาจาก k8s/scan-namespace.yaml
  - registry-push.sealed.yaml             # Secret ที่ Job สแกนใช้ push :5002 (เดิม Ansible สร้าง)
  - skypilot-api-tailnet-service.yaml     # ย้ายมาจาก k8s/
  - backend-rbac.yaml                     # ข้อ 7.3
patches:
  # แทน REGISTRY_IP ที่ Ansible เคย replace ตอน apply
  - target: { kind: NetworkPolicy, name: restrict-egress, namespace: vlab-scan }
    patch: |
      - op: replace
        path: /spec/egress/1/to/0/ipBlock/cidr
        value: <REGISTRY_IP>/32
```

```yaml
# namespaces.yaml — ห้าม Argo CD ลบ ns (ลบแล้ว pod lab / Job สแกน / DB หายหมด)
apiVersion: v1
kind: Namespace
metadata:
  name: vlab-prod
  annotations:
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
---
apiVersion: v1
kind: Namespace
metadata:
  name: vlab-staging
  annotations:
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
---
apiVersion: v1
kind: Namespace
metadata:
  name: vlab-staging-labs
  annotations:
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
```

ย้ายความเป็นเจ้าของออกจาก Ansible ใน PR เดียวกัน (Solution D12):
- `ansible/roles/k3s-server/tasks/main.yml`: ลบ task "Apply lab isolation NetworkPolicy (default namespace)", "Apply lab image scan namespace (vlab-scan)", "Read current registry push credentials", "Store registry push credentials for scan Jobs"
- `ansible/roles/skypilot-node/tasks/main.yml`: ลบ task "Apply lab isolation NetworkPolicy (skypilot namespace)" และ "Apply SkyPilot API NodePort for the backend (Tailscale)"
- ข้อควรรู้: `skypilot_reset=true` ลบ ns `skypilot` ทิ้ง ระหว่างนั้น Argo CD จะขึ้น error ว่าไม่มี ns พอ Ansible สร้าง ns ใหม่แล้ว Argo CD จะ self-heal NetworkPolicy / Service คืนเอง

### 7.2 web-portal base — `deploy/apps/web-portal/base/`

```yaml
# kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
labels:
  - pairs: { app.kubernetes.io/part-of: virtual-lab }
    includeSelectors: false
resources:
  - serviceaccount.yaml
  - storage-pvc.yaml
  - backend.yaml
  - frontend.yaml
  - hooks/db-backup.yaml
  - hooks/db-migrate.yaml
  - hooks/smoke.yaml
```

```yaml
# serviceaccount.yaml — สิทธิ์ผูกใน cluster-config (ข้อ 7.3) แทน kubeconfig admin
apiVersion: v1
kind: ServiceAccount
metadata:
  name: vlab-backend
```

```yaml
# storage-pvc.yaml — ไฟล์เอกสารแลป / รูปปกวิชา (STORAGE_ROOT) ถ้าเปลี่ยนเป็น STORAGE_BACKEND=s3 ลบไฟล์นี้ได้
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: backend-storage
  annotations:
    argocd.argoproj.io/sync-wave: "-3"
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path            # ของ k3s — ไม่จำกัดขนาดจริง ดูพื้นที่ disk ของ platform node เอง
  resources: { requests: { storage: 20Gi } }
```

```yaml
# backend.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  replicas: 1                             # Solution C2 — scheduler อยู่ใน process ห้ามเกิน 1
  strategy:
    type: Recreate                        # hostNetwork: 2 pod ผูกพอร์ตเดียวกันบน node เดียวกันไม่ได้
  revisionHistoryLimit: 5
  selector:
    matchLabels: { app.kubernetes.io/name: vlab-backend }
  template:
    metadata:
      labels: { app.kubernetes.io/name: vlab-backend }
      annotations:
        vlab.io/secrets-rev: "1"          # เพิ่มเลขเมื่อ rotate secret → pod restart อ่านค่าใหม่
    spec:
      serviceAccountName: vlab-backend
      hostNetwork: true                   # Solution C1/D4 — ไม่มี NAT คั่นระหว่าง nginx กับ backend
      dnsPolicy: ClusterFirstWithHostNet  # ยัง resolve postgres.<ns>.svc ได้
      nodeSelector: { vlab.io/role: platform }
      tolerations:
        - { key: vlab.io/dedicated, operator: Equal, value: platform, effect: NoSchedule }
      terminationGracePeriodSeconds: 60   # ให้ lifespan หยุด reconciler / scheduler ให้จบ (app/main.py:230)
      containers:
        - name: backend
          image: vlab-backend
          # ผูก loopback เท่านั้น — เข้าจากข้างนอกได้ทาง nginx อย่างเดียว (เชื่อ X-Real-IP จาก 127.0.0.1 — AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2A)
          command: ["/bin/sh", "-c", 'exec uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"']
          envFrom:
            - configMapRef: { name: backend-config }
            - secretRef: { name: backend-secrets }
          ports:
            - { name: http, containerPort: 8000 }   # staging patch เป็น 8100 (ต้องตรงกับ API_PORT)
          startupProbe:
            httpGet: { host: 127.0.0.1, path: /health, port: http }
            periodSeconds: 5
            failureThreshold: 24          # รอได้ 2 นาที (lifespan ต่อ DB + K8s + SkyPilot)
          readinessProbe:
            httpGet: { host: 127.0.0.1, path: /health, port: http }
            periodSeconds: 10
          livenessProbe:
            httpGet: { host: 127.0.0.1, path: /health, port: http }
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
          resources:
            requests: { cpu: 250m, memory: 512Mi }
            limits: { memory: 2Gi }
          volumeMounts:
            - { name: storage, mountPath: /app/storage }
            - { name: aws, mountPath: /root/.aws, readOnly: true }   # profile [skypilot] (AWS_PROFILE=skypilot)
      volumes:
        - name: storage
          persistentVolumeClaim: { claimName: backend-storage }
        - name: aws
          secret:
            secretName: backend-aws
            items: [{ key: credentials, path: credentials }]
```

```yaml
# frontend.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  replicas: 1
  strategy: { type: Recreate }
  revisionHistoryLimit: 5
  selector:
    matchLabels: { app.kubernetes.io/name: vlab-frontend }
  template:
    metadata:
      labels: { app.kubernetes.io/name: vlab-frontend }
    spec:
      hostNetwork: true                   # $remote_addr = Tailscale IP จริงของเครื่องแลป (AWS_LAB_GATEWAY.md ข้อ 16.0 D4)
      dnsPolicy: ClusterFirstWithHostNet
      automountServiceAccountToken: false
      nodeSelector: { vlab.io/role: platform }
      tolerations:
        - { key: vlab.io/dedicated, operator: Equal, value: platform, effect: NoSchedule }
      containers:
        - name: nginx
          image: vlab-frontend
          env:
            - name: BIND_IP               # = Tailscale IP ของ node (k3s --node-ip)
              valueFrom: { fieldRef: { fieldPath: status.hostIP } }
          envFrom:
            - configMapRef: { name: frontend-config }   # HTTP_PORT, API_UPSTREAM
          ports:
            - { name: http, containerPort: 80 }         # staging patch เป็น 8180
          readinessProbe:
            httpGet: { path: /, port: http }            # host = pod IP = node IP = BIND_IP
            periodSeconds: 10
          livenessProbe:
            httpGet: { path: /, port: http }
            periodSeconds: 30
          resources:
            requests: { cpu: 20m, memory: 32Mi }
            limits: { memory: 128Mi }
```

ไฟล์ใหม่ `web-portal/frontend/nginx.conf.template` (ถ้า AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2D เขียน nginx.conf ใหม่แล้ว ให้ใช้ของนั้นเป็นตัวตั้ง แล้วเปลี่ยนแค่ `listen` / `proxy_pass` ให้เป็นตัวแปร)
image `nginx:alpine` รัน `envsubst` กับ `/etc/nginx/templates/*.template` ตอนเริ่ม และแทนเฉพาะตัวแปรที่มีใน env เท่านั้น ตัวแปรของ nginx อย่าง `$uri` และ `$remote_addr` จึงไม่โดนแทน

```nginx
server {
    listen ${BIND_IP}:${HTTP_PORT};
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://${API_UPSTREAM};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;      # เขียนทับเสมอ — client ปลอมค่านี้ไม่ได้
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;                      # Start (AWS) รอได้ ~2 นาที จนกว่า AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2B จะเสร็จ
        client_max_body_size 100m;                    # ← ตั้งให้ ≥ ขนาดไฟล์ที่ backend รับ (default ของ nginx = 1m)
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    # (คง block /assets/ และ .mjs เดิมจาก nginx.conf ไว้ทั้งหมด)

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1000;
}
```

แก้ `web-portal/frontend/Dockerfile` stage 2:

```dockerfile
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# ค่าเริ่มต้นให้ compose ใช้ได้เหมือนเดิม — K8s ส่งค่าจริงมาทาง env
ENV BIND_IP=0.0.0.0 HTTP_PORT=80 API_UPSTREAM=127.0.0.1:8000
```

### 7.3 RBAC ของ backend — `deploy/platform/cluster-config/backend-rbac.yaml`

รายการ verb ได้จากการ grep การเรียก kubernetes client ใน `web-portal/backend/app` (`list_node`, `list_pod_for_all_namespaces`, `create/delete/patch_namespaced_pod`, `read_namespaced_pod_log`, `create/delete/list_namespaced_daemon_set`, `create/delete/read/list_namespaced_deployment`, `create/delete/read/list_namespaced_job`, `create/replace_namespaced_secret`, `list_namespaced_service`, `list_namespaced_event`)
ก่อนใช้กับ prod ให้ deploy บน staging แล้วหา `403` ใน log หรือเช็กด้วย `kubectl auth can-i --as=system:serviceaccount:vlab-staging:vlab-backend ...`

```yaml
# อ่านทั้ง cluster: node (เครื่องแลป), ns, pod (หน้า monitor)
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: { name: vlab-backend-read }
rules:
  - apiGroups: [""]
    resources: [nodes, namespaces, pods]
    verbs: [get, list, watch]
---
# งานใน ns ของ lab / scan: pod lab, warm pod DaemonSet, Job สแกน, secret ของ Job
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: { name: vlab-backend-labs }
rules:
  - apiGroups: [""]
    resources: [pods]
    verbs: [get, list, watch, create, delete, patch]
  - apiGroups: [""]
    resources: [pods/log, events, services]
    verbs: [get, list]
  - apiGroups: [""]
    resources: [secrets]
    verbs: [get, create, update]
  - apiGroups: [apps]
    resources: [daemonsets, deployments]
    verbs: [get, list, watch, create, delete]
  - apiGroups: [batch]
    resources: [jobs]
    verbs: [get, list, watch, create, delete]
---
# prod: อ่านทั้ง cluster + ทำงานใน default (K8S_DEFAULT_NAMESPACE) และ vlab-scan
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: { name: vlab-backend-read-prod }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: vlab-backend-read }
subjects: [{ kind: ServiceAccount, name: vlab-backend, namespace: vlab-prod }]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: vlab-backend-prod, namespace: default }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: vlab-backend-labs }
subjects: [{ kind: ServiceAccount, name: vlab-backend, namespace: vlab-prod }]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: vlab-backend-prod, namespace: vlab-scan }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: vlab-backend-labs }
subjects: [{ kind: ServiceAccount, name: vlab-backend, namespace: vlab-prod }]
---
# staging: อ่านทั้ง cluster + ทำงานได้แค่ vlab-staging-labs (ไม่แตะ default / vlab-scan ของ prod)
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: { name: vlab-backend-read-staging }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: vlab-backend-read }
subjects: [{ kind: ServiceAccount, name: vlab-backend, namespace: vlab-staging }]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: vlab-backend-staging, namespace: vlab-staging-labs }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: vlab-backend-labs }
subjects: [{ kind: ServiceAccount, name: vlab-backend, namespace: vlab-staging }]
```

### 7.4 Hook Jobs — `deploy/apps/web-portal/base/hooks/`

ลำดับใน 1 sync:

```
wave -3  ConfigMap (hash) · SealedSecret → Secret · PVC              ← ค่าใหม่พร้อมก่อน
wave -2  Job db-backup     (hook: Sync)   pg_dump → PVC db-backups
wave -1  Job db-migrate    (hook: Sync)   init_db.py → run_rbac_seed.py  ← backend ตัวเก่ายังรันอยู่
wave  1  Deployment backend   (Recreate: หยุดตัวเก่า → ขึ้นตัวใหม่)
wave  2  Deployment frontend
PostSync Job smoke · whoami-from-lab (prod) · grafana-ro (prod)
```

ใช้ `hook: Sync` + wave แทน `PreSync` เพราะ PreSync จะรัน**ก่อน**ที่ ConfigMap / Secret ของ release นั้นถูก apply ทำให้ sync รอบแรกของ env ใหม่ล้ม (ยังไม่มี `backend-secrets`)
ส่วน `BeforeHookCreation` จะเก็บ Job ของรอบล่าสุดไว้ให้อ่าน log และลบทิ้งก่อนรอบถัดไปสร้างใหม่

```yaml
# hooks/db-backup.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-backup
  annotations:
    argocd.argoproj.io/hook: Sync
    argocd.argoproj.io/sync-wave: "-2"
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 900
  template:
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      nodeSelector: { vlab.io/role: platform }        # PVC local-path อยู่บน node นี้
      tolerations:
        - { key: vlab.io/dedicated, operator: Equal, value: platform, effect: NoSchedule }
      containers:
        - name: pg-dump
          image: postgres:17-alpine                   # major ต้องตรงกับ server
          env:
            - name: DATABASE_URL
              valueFrom: { secretKeyRef: { name: backend-secrets, key: DATABASE_URL } }
          command: ["/bin/sh", "-ec"]
          args:
            - |
              f="/backups/presync-$(date -u +%Y%m%dT%H%M%SZ).dump"
              pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" --file="$f"
              ls -1t /backups/presync-*.dump | tail -n +11 | xargs -r rm -f   # เก็บ 10 ไฟล์ล่าสุด
              ls -lh /backups
          volumeMounts: [{ name: backups, mountPath: /backups }]
      volumes:
        - name: backups
          persistentVolumeClaim: { claimName: db-backups }   # สร้างใน app db-<env>
```

```yaml
# hooks/db-migrate.yaml — แทน task "Create database schema" + "Seed RBAC roles" ของ role web-service
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migrate
  annotations:
    argocd.argoproj.io/hook: Sync
    argocd.argoproj.io/sync-wave: "-1"
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  backoffLimit: 0                                     # migration ล้ม ห้ามลองซ้ำเอง
  activeDeadlineSeconds: 600
  template:
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      nodeSelector: { vlab.io/role: platform }
      tolerations:
        - { key: vlab.io/dedicated, operator: Equal, value: platform, effect: NoSchedule }
      containers:
        - name: migrate
          image: vlab-backend                         # image ตัวใหม่ของ release นี้ (kustomize แทนให้)
          command: ["/bin/sh", "-ec", "python script/init_db.py && python script/run_rbac_seed.py"]
          envFrom:
            - configMapRef: { name: backend-config }
            - secretRef: { name: backend-secrets }
          resources:
            requests: { cpu: 100m, memory: 256Mi }
            limits: { memory: 1Gi }
```

```yaml
# hooks/smoke.yaml — แทน task verify ของ role web-service (health, query DB, nginx, sky api info)
apiVersion: batch/v1
kind: Job
metadata:
  name: smoke
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  backoffLimit: 1
  activeDeadlineSeconds: 300
  template:
    spec:
      restartPolicy: Never
      hostNetwork: true                               # ยิง 127.0.0.1 / BIND_IP ของ platform node
      dnsPolicy: ClusterFirstWithHostNet
      automountServiceAccountToken: false
      nodeSelector: { vlab.io/role: platform }
      tolerations:
        - { key: vlab.io/dedicated, operator: Equal, value: platform, effect: NoSchedule }
      containers:
        - name: smoke
          image: vlab-backend                         # มี curl + sky CLI อยู่แล้ว
          env:
            - name: BIND_IP
              valueFrom: { fieldRef: { fieldPath: status.hostIP } }
          envFrom:
            - configMapRef: { name: backend-config }  # API_PORT, API_PREFIX, SKYPILOT_API_SERVER_ENDPOINT
            - configMapRef: { name: frontend-config } # HTTP_PORT
            - secretRef: { name: backend-secrets }    # SKYPILOT_SERVICE_ACCOUNT_TOKEN
          command: ["/bin/sh", "-ec"]
          args:
            - |
              # 1) backend ขึ้นและต่อ DB ได้
              curl -fsS "http://127.0.0.1:${API_PORT}/health"
              # 2) query ตารางจริงได้ (/health เช็กแค่ต่อ DB ติด)
              code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${API_PORT}${API_PREFIX}/sessions")
              case "$code" in 200|401|403) ;; *) echo "GET ${API_PREFIX}/sessions = $code"; exit 1;; esac
              # 3) nginx ตอบ และ proxy /api ไป backend ได้
              curl -fsS -o /dev/null "http://${BIND_IP}:${HTTP_PORT}/"
              curl -fsS -o /dev/null "http://${BIND_IP}:${HTTP_PORT}${API_PREFIX}/v1/whoami"
              # 4) คุยกับ SkyPilot กลางได้ด้วย token (Solution C7)
              if [ -n "${SKYPILOT_API_SERVER_ENDPOINT:-}" ]; then
                out="$(sky api info)"; echo "$out"
                echo "$out" | grep -q "$SKYPILOT_API_SERVER_ENDPOINT"
                echo "$out" | grep -q HEALTHY
              fi
              echo "smoke OK"
```

`components/whoami-from-lab/` (prod เท่านั้น) แทน task "Verify backend sees the real IP of a lab machine"
ถ้า backend เห็น IP ไม่ตรงกับเครื่องแลปจริง ทุกการกด Start จะไป AWS (เจอมาแล้ว 2026-10-23) ต้องเลือกเครื่องแลปที่เปิดตลอด ถ้าไม่มีเครื่องแบบนั้น ให้ตัด component นี้ออกแล้วรันมือหลัง deploy

```yaml
# components/whoami-from-lab/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
resources: [job.yaml]
---
# components/whoami-from-lab/job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: whoami-from-lab
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 180
  template:
    spec:
      restartPolicy: Never
      hostNetwork: true                               # ต้องออกจาก IP ของเครื่องแลปจริง ไม่ใช่ pod IP
      automountServiceAccountToken: false
      nodeSelector:
        kubernetes.io/hostname: <LAB_NODE_NAME>       # เครื่องแลปที่เปิดตลอด (overlay patch)
      containers:
        - name: whoami
          image: python:3.12-alpine                   # เล็ก — ไม่ต้องดึง image backend ลงเครื่องแลป
          env:
            - name: NODE_IP
              valueFrom: { fieldRef: { fieldPath: status.hostIP } }
            - name: PORTAL
              value: http://<PLATFORM_IP>
          command: ["python", "-c"]
          args:
            - |
              import json, os, urllib.request
              data = json.load(urllib.request.urlopen(os.environ["PORTAL"] + "/api/v1/whoami", timeout=10))["data"]
              print(data)
              assert data["clientIp"] == os.environ["NODE_IP"], "มี NAT / proxy คั่น: backend ไม่เห็น IP จริงของเครื่องแลป"
              assert data["labMachine"], "IP ของเครื่องนี้ไม่ถูกนับเป็นเครื่องแลป"
```

`components/grafana-ro/` (prod เท่านั้น) แทน task "SIEM read-only DB user for Grafana" เป็น PostSync Job ใช้ image `postgres:17-alpine` ส่ง SQL ทาง heredoc (stdin) เพื่อไม่ให้รหัสไปอยู่ใน argv แบบเดียวกับที่ Ansible ทำ
ต้องอยู่ใน app web-portal ไม่ใช่ app db เพราะตาราง `infrastructure_logs` จะมีหลัง `db-migrate` รันแล้วเท่านั้น

### 7.5 Overlays

`deploy/apps/web-portal/overlays/prod/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: vlab-prod
resources:
  - ../../base
  - backend-secrets.sealed.yaml
  - backend-aws.sealed.yaml
components:
  - ../../components/whoami-from-lab
  - ../../components/grafana-ro
configMapGenerator:
  - name: backend-config
    envs: [backend.env]
    options:
      annotations: { argocd.argoproj.io/sync-wave: "-3" }
  - name: frontend-config
    envs: [frontend.env]
    options:
      annotations: { argocd.argoproj.io/sync-wave: "-3" }
patches:
  - target: { kind: Job, name: whoami-from-lab }
    patch: |
      - { op: replace, path: /spec/template/spec/nodeSelector/kubernetes.io~1hostname, value: <LAB_NODE_NAME> }
      - { op: replace, path: /spec/template/spec/containers/0/env/1/value, value: "http://<PLATFORM_IP>" }
images:                                   # release.yml เขียน — ห้ามแก้ด้วยมือ
  - name: vlab-backend
    newName: ghcr.io/nawapatthumthaisong97/vlab-backend
    digest: sha256:0000000000000000000000000000000000000000000000000000000000000000
  - name: vlab-frontend
    newName: ghcr.io/nawapatthumthaisong97/vlab-frontend
    digest: sha256:0000000000000000000000000000000000000000000000000000000000000000
commonAnnotations:
  vlab.io/release: v0.0.0                 # release.yml เขียน
```

`deploy/apps/web-portal/overlays/prod/backend.env` เป็นค่าที่**ไม่ลับ** โดยย้ายมาจาก `ansible/roles/web-service/templates/backend.env.j2` แบบตรงตัว ยกเว้น 3 บรรทัดที่มีหมายเหตุ

```dotenv
APP_NAME=Virtual Lab Backend
APP_VERSION=1.0.0
DEBUG=false
API_PREFIX=/api
API_PORT=8000
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
CORS_ORIGINS_STR=http://<PLATFORM_IP>
# AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2A — เชื่อ X-Real-IP เฉพาะ nginx บนเครื่องเดียวกัน (ชื่อตัวแปรตามที่ 2A ตั้งจริง)
TRUSTED_PROXY_CIDRS_STR=127.0.0.1/32
STORAGE_ROOT=storage
STORAGE_BACKEND=local
STORAGE_S3_BUCKET=
K8S_ENABLED=true
# ไม่มี KUBECONFIG / KUBECONFIG_PATH แล้ว — ใช้ ServiceAccount (in-cluster config, ข้อ 9 #1)
K8S_DEFAULT_NAMESPACE=default
K8S_TIMEOUT=30
DOCKER_REGISTRY_HOST=<REGISTRY_IP>:5001
SKYPILOT_API_SERVER_ENDPOINT=http://<MASTER_IP>:30880
AWS_REGION=ap-southeast-1
AWS_LAB_AMI=ami-0da9046ec7f57f3af
AWS_INSTANCE_TYPE=m7i-flex.large
AWS_DISK_SIZE=30
ECR_REGISTRY_HOST=568318158381.dkr-ecr.ap-southeast-1.on.aws
AWS_PROFILE=skypilot
AWS_COST_EXPLORER_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
MAIL_FROM_NAME=Virtual Lab Team
MAIL_REDIRECT_TO=
MAIL_ALLOWED_RECIPIENTS=
LAB_IMAGE_SCAN_ENABLED=false
R2_ACCOUNT_ID=<R2_ACCOUNT_ID>
R2_BUCKET_NAME=<R2_BUCKET_NAME>
R2_ENDPOINT_URL=https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com
PREWARM_ENABLED=true
PREWARM_LEAD_MINUTES=30
WARM_POD_ENABLED=true
LAB_ISOLATION_ENABLED=true
LAB_MACHINE_LAUNCH=pod
PRELAUNCH_ENABLED=false
PRELAUNCH_LEAD_MINUTES=10
PRELAUNCH_CLAIM_MINUTES=15
PRELAUNCH_MAX_PARALLEL=5
```

`overlays/prod/frontend.env`

```dotenv
HTTP_PORT=80
API_UPSTREAM=127.0.0.1:8000
```

`deploy/apps/web-portal/overlays/staging/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: vlab-staging
resources:
  - ../../base
  - backend-secrets.sealed.yaml
  - backend-aws.sealed.yaml
configMapGenerator:
  - name: backend-config
    envs: [backend.env]
    options:
      annotations: { argocd.argoproj.io/sync-wave: "-3" }
  - name: frontend-config
    envs: [frontend.env]
    options:
      annotations: { argocd.argoproj.io/sync-wave: "-3" }
patches:
  # hostNetwork: containerPort = พอร์ตจริงบน host ถ้าซ้ำกับ prod scheduler จะไม่วาง pod (Pending)
  - target: { kind: Deployment, name: backend }
    patch: |
      - { op: replace, path: /spec/template/spec/containers/0/ports/0/containerPort, value: 8100 }
  - target: { kind: Deployment, name: frontend }
    patch: |
      - { op: replace, path: /spec/template/spec/containers/0/ports/0/containerPort, value: 8180 }
images:                                   # images.yml (bot) เขียน
  - name: vlab-backend
    newName: ghcr.io/nawapatthumthaisong97/vlab-backend
    newTag: sha-0000000
  - name: vlab-frontend
    newName: ghcr.io/nawapatthumthaisong97/vlab-frontend
    newTag: sha-0000000
```

`overlays/staging/backend.env` ใช้ค่าเดียวกับ prod **ยกเว้น**:

```dotenv
API_PORT=8100
CORS_ORIGINS_STR=http://<PLATFORM_IP>:8180
K8S_DEFAULT_NAMESPACE=vlab-staging-labs
AWS_COST_EXPLORER_ENABLED=false
MAIL_REDIRECT_TO=<TEAM_INBOX>
MAIL_ALLOWED_RECIPIENTS=
PREWARM_ENABLED=false
WARM_POD_ENABLED=false
PRELAUNCH_ENABLED=false
LAB_IMAGE_SCAN_ENABLED=false
```

`overlays/staging/frontend.env`: `HTTP_PORT=8180`, `API_UPSTREAM=127.0.0.1:8100`

### 7.6 Postgres — `deploy/apps/postgres/base/`

```yaml
# statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  annotations:
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels: { app.kubernetes.io/name: postgres }
  template:
    metadata:
      labels: { app.kubernetes.io/name: postgres }
    spec:
      nodeSelector: { vlab.io/role: platform }
      tolerations:
        - { key: vlab.io/dedicated, operator: Equal, value: platform, effect: NoSchedule }
      securityContext: { fsGroup: 70 }              # uid/gid ของ postgres ใน image alpine
      containers:
        - name: postgres
          image: postgres:17-alpine                 # pin minor + digest ตอนทำ (major ต้องตรงกับ compose เดิม)
          envFrom:
            - secretRef: { name: postgres-secrets } # POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
          env:
            - { name: PGDATA, value: /var/lib/postgresql/data/pgdata }
          ports: [{ name: pg, containerPort: 5432 }]
          readinessProbe:
            exec: { command: ["sh", "-c", 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'] }
            periodSeconds: 10
          livenessProbe:
            exec: { command: ["sh", "-c", 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'] }
            periodSeconds: 30
            failureThreshold: 6
          resources:
            requests: { cpu: 100m, memory: 256Mi }
            limits: { memory: 1Gi }
          volumeMounts: [{ name: data, mountPath: /var/lib/postgresql/data }]
  volumeClaimTemplates:
    - metadata: { name: data }
      spec:
        accessModes: [ReadWriteOnce]
        storageClassName: local-path
        resources: { requests: { storage: 20Gi } }
```

ไฟล์อื่นใน base:
- `service.yaml`: `ClusterIP` ชื่อ `postgres` พอร์ต 5432
- `backups-pvc.yaml`: PVC `db-backups` (`Prune=false,Delete=false`) ใช้ร่วมกับ hook `db-backup` และ CronJob
- `backup-cronjob.yaml`: `schedule: "0 3 * * *"`, `timeZone: Asia/Bangkok`, ทำ `pg_dump` ลง `/backups/nightly-*.dump` เก็บ 14 ไฟล์ (prod เพิ่ม container ที่สองส่งขึ้น S3 ด้วย IAM user ที่มีแค่ `s3:PutObject` บน prefix `db-backups/`)
- `networkpolicy.yaml`: ขาเข้าพอร์ต 5432 รับเฉพาะ pod ใน ns เดียวกัน (hook / CronJob) และ (prod) `namespaceSelector: kubernetes.io/metadata.name=siem-system` + `podSelector: app.kubernetes.io/name=grafana-siem`
  backend ใช้ hostNetwork จึงต่อมาจาก IP ของ node ซึ่ง kube-router ของ k3s ปล่อยให้ traffic จาก node เดียวกันผ่านอยู่แล้ว (ดู comment ใน `k8s/lab-isolation-networkpolicy.yaml`) ถ้าพบว่าโดนบล็อก ให้เพิ่ม `ipBlock: <PLATFORM_IP>/32`

### 7.7 SIEM — `deploy/platform/siem/` + `k8s/siem/kustomization.yaml`

ใส่ `kustomization.yaml` ให้แต่ละ layer เพื่อกำหนด wave ตามลำดับใน `docs/SETUP_TEST.md` ขั้น 5.5 (Argo CD จะรอให้ wave ก่อนหน้า Healthy ก่อน)
ถ้าทำแบบนี้ `kubectl apply -f k8s/siem/layer2-buffer/` แบบเดิมจะใช้ไม่ได้แล้ว (จะเจอ kind `Kustomization`) ต้องแก้ SETUP_TEST เป็น `kubectl apply -k k8s/siem` ส่วน `backend-tests.yml` อ่านไฟล์ YAML ตรง ๆ จึงไม่กระทบ

```yaml
# k8s/siem/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - layer1-collector/00-namespace-rbac.yaml   # wave 0 — ns + RBAC ต้องมาก่อนทุก layer
  - layer2-buffer                              # wave 1
  - layer4-storage                             # wave 2
  - layer3-processing                          # wave 3
  - layer1-collector                           # wave 4 (ไม่รวม 00-namespace-rbac.yaml)
  - layer5-detection                           # wave 4
```

```yaml
# k8s/siem/layer2-buffer/kustomization.yaml (layer อื่นทำเหมือนกัน เปลี่ยนเลข wave)
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
commonAnnotations:
  argocd.argoproj.io/sync-wave: "1"
resources:
  - 00-nats-configmap.yaml
  - 01-nats-services.yaml
  - 02-nats-statefulset.yaml
  - 03-nats-streams-kv-bootstrap.yaml          # Job รอ JetStream เองอยู่แล้ว (until … server check)
```

`layer4-storage/kustomization.yaml` ให้ใส่แค่ `00-victorialogs-hot-storage.yaml` (SETUP_TEST ไม่ได้ apply `01-aws-s3-cold-storage.yaml` ให้เปิดเมื่อพร้อมเท่านั้น)

`deploy/platform/siem/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../k8s/siem
  - siem-secrets.sealed.yaml                   # siem-collector-secrets + siem-collector-token (เดิมสร้างด้วยมือ)
```

ต้องแก้ไฟล์ต้นทางที่ฮาร์ดโค้ด `100.86.87.27` (IP ของ backend เครื่องเก่า) ไว้ 3 จุด ดูข้อ 9 #8

---

## 8. Secrets

### 8.1 รายการ secret

| Secret (namespace) | key | มาจาก (`group_vars/all.yml` สำหรับ prod / `ansible/secrets/staging.yml` สำหรับ staging) |
|---|---|---|
| `backend-secrets` (`vlab-<env>`) | `DATABASE_URL` | `postgresql://<webservice_postgres_user>:<vault_postgres_password>@postgres.vlab-<env>.svc.cluster.local:5432/<webservice_postgres_db>` |
| | `SECRET_KEY`, `ADMIN_SESSION_SECRET_KEY` | `vault_backend_secret_key`, `vault_admin_session_secret_key` |
| | `SKYPILOT_SERVICE_ACCOUNT_TOKEN` | `skypilot_backend_token` (staging ใช้ token แยก) |
| | `SMTP_USER`, `SMTP_PASSWORD` | `vault_smtp_user`, `vault_smtp_password` (ตัดช่องว่างออกแบบใน template) |
| | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_WEBHOOK_SECRET` | `vault_r2_*` |
| | `SIEM_COLLECTOR_TOKEN` | `vault_siem_collector_token` |
| `backend-aws` (`vlab-<env>`) | `credentials` (ไฟล์ profile `[skypilot]`) | `skypilot_aws_access_key_id`, `skypilot_aws_secret_access_key` |
| `postgres-secrets` (`vlab-<env>`) | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `GRAFANA_RO_PASSWORD` | `webservice_postgres_*`, `vault_siem_grafana_ro_password` |
| `registry-push` (`vlab-scan`) | `username`, `password` (type `basic-auth`) | `registry_users.scanner.password` |
| `siem-collector-secrets`, `siem-collector-token` (`siem-system`) | ตาม `docs/SETUP_TEST.md` ขั้น 5.5 | `siem_collector_token`, รหัสของ `grafana_ro` |
| `argocd-notifications-secret` (`argocd`) | `discord-webhook-url` | ใหม่ |

### 8.2 ขั้นตอนใช้งาน

```bash
# ครั้งเดียวหลัง controller ขึ้น: เอา public cert มา commit (ไม่ลับ)
kubeseal --fetch-cert --controller-namespace kube-system --controller-name sealed-secrets-controller > deploy/sealed-secrets/pub-cert.pem
```

```bash
# backup private key ของ controller — เก็บใน password manager ของทีม ห้ามเข้า Git
kubectl -n kube-system get secret -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml > sealed-secrets-key.backup.yaml
```

```bash
# seal / seal ใหม่ทุกครั้งที่ค่าเปลี่ยน
python script/seal-secrets.py --env prod --vars ansible/group_vars/all.yml
```

```bash
python script/seal-secrets.py --env staging --vars ansible/secrets/staging.yml
```

หลัง seal ใหม่ ให้เพิ่มเลข `vlab.io/secrets-rev` ใน `base/backend.yaml` (หรือใช้ patch ของ overlay) ใน PR เดียวกัน เพราะ pod ไม่ได้อ่าน env ใหม่เองเมื่อ Secret เปลี่ยน
(Phase 5 จะติดตั้ง Stakater Reloader แทนการเพิ่มเลขเองก็ได้)

### 8.3 `script/seal-secrets.py` (ร่าง)

```python
#!/usr/bin/env python3
"""ค่าลับใน group_vars → SealedSecret ใน deploy/ โดยไม่เขียน plaintext ลง disk

  python script/seal-secrets.py --env prod    --vars ansible/group_vars/all.yml
  python script/seal-secrets.py --env staging --vars ansible/secrets/staging.yml

ต้องมี kubeseal และ deploy/sealed-secrets/pub-cert.pem
ถ้าไฟล์เข้ารหัสด้วย ansible-vault: ansible-vault view <file> | python script/seal-secrets.py --env prod --vars -
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CERT = ROOT / "deploy/sealed-secrets/pub-cert.pem"
WAVE = {"argocd.argoproj.io/sync-wave": "-3"}


def seal(name: str, namespace: str, data: dict, secret_type: str = "Opaque") -> str:
    secret = {
        "apiVersion": "v1", "kind": "Secret", "type": secret_type,
        "metadata": {"name": name, "namespace": namespace},
        "stringData": data,
    }
    out = subprocess.run(
        ["kubeseal", "--cert", str(CERT), "--format", "yaml", "--scope", "strict"],
        input=json.dumps(secret), capture_output=True, text=True, check=True,
    ).stdout
    sealed = yaml.safe_load(out)
    sealed["metadata"].setdefault("annotations", {}).update(WAVE)  # wave ของ SealedSecret เอง
    return yaml.safe_dump(sealed, sort_keys=False)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--env", choices=["staging", "prod"], required=True)
    p.add_argument("--vars", required=True, help="ไฟล์ group_vars หรือ - (stdin)")
    a = p.parse_args()
    v = yaml.safe_load(sys.stdin if a.vars == "-" else Path(a.vars).read_text(encoding="utf-8"))

    ns = f"vlab-{a.env}"
    user = v.get("webservice_postgres_user", "postgres")
    db = v.get("webservice_postgres_db", "virtual_lab")
    pw = v["vault_postgres_password"]
    out = ROOT / f"deploy/apps/web-portal/overlays/{a.env}"

    (out / "backend-secrets.sealed.yaml").write_text(seal("backend-secrets", ns, {
        "DATABASE_URL": f"postgresql://{user}:{pw}@postgres.{ns}.svc.cluster.local:5432/{db}",
        "SECRET_KEY": v["vault_backend_secret_key"],
        "ADMIN_SESSION_SECRET_KEY": v["vault_admin_session_secret_key"],
        "SKYPILOT_SERVICE_ACCOUNT_TOKEN": v.get("skypilot_backend_token", ""),
        "SMTP_USER": v.get("vault_smtp_user", ""),
        "SMTP_PASSWORD": v.get("vault_smtp_password", "").replace(" ", ""),
        "R2_ACCESS_KEY_ID": v.get("vault_r2_access_key_id", ""),
        "R2_SECRET_ACCESS_KEY": v.get("vault_r2_secret_access_key", ""),
        "R2_WEBHOOK_SECRET": v.get("vault_r2_webhook_secret", ""),
        "SIEM_COLLECTOR_TOKEN": v.get("vault_siem_collector_token", ""),
    }), encoding="utf-8")

    (out / "backend-aws.sealed.yaml").write_text(seal("backend-aws", ns, {
        "credentials": "[skypilot]\n"
                       f"aws_access_key_id = {v.get('skypilot_aws_access_key_id', '')}\n"
                       f"aws_secret_access_key = {v.get('skypilot_aws_secret_access_key', '')}\n",
    }), encoding="utf-8")

    pg_out = ROOT / f"deploy/apps/postgres/overlays/{a.env}"
    (pg_out / "postgres-secrets.sealed.yaml").write_text(seal("postgres-secrets", ns, {
        "POSTGRES_USER": user, "POSTGRES_PASSWORD": pw, "POSTGRES_DB": db,
        "GRAFANA_RO_PASSWORD": v.get("vault_siem_grafana_ro_password", ""),
    }), encoding="utf-8")
    # registry-push (vlab-scan) / siem-* : เพิ่มเฉพาะตอน --env prod ในรูปแบบเดียวกัน


if __name__ == "__main__":
    main()
```

---

## 9. โค้ด / ไฟล์ที่ต้องแก้

| # | ไฟล์ | แก้อะไร | ทำไม | Phase |
|---|---|---|---|---|
| 1 | `web-portal/backend/app/services/kubernetes_service.py:30-41` | ถ้าไม่มี kubeconfig และมี env `KUBERNETES_SERVICE_HOST` ให้เรียก `config.load_incluster_config()` (ตอนนี้ fallback ไป `load_kube_config()` ซึ่งจะพังใน pod) | ใช้ ServiceAccount แทน kubeconfig admin | 3 |
| 2 | `web-portal/backend/app/services/warm_pod_service.py:153`, `prewarm_service.py:82` | เพิ่ม `{"key": "vlab.io/role", "operator": "NotIn", "values": ["platform"]}` ใน affinity ของ DaemonSet | กันไม่ให้ warm pod ลง platform node (ทำงานคู่กับ taint) | 3 |
| 3 | `warm_pod_service.py:266-280` (`node_for_ip`), `prewarm_service.py:165` | ข้าม node ที่มี label `vlab.io/role=platform` และเพิ่ม test ใน `tests/prewarm` | Solution C3 — ไม่ให้นับ platform node เป็นเครื่องแลป | 3 |
| 4 | `web-portal/frontend/Dockerfile`, `nginx.conf` → `nginx.conf.template` | `listen ${BIND_IP}:${HTTP_PORT}`, proxy `/api/` → `${API_UPSTREAM}` + ค่า ENV เริ่มต้น | hostNetwork + พอร์ตต่อ env (ข้อ 7.2) | 3 (ทำพร้อม AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2D) |
| 5 | `web-portal/frontend/src/services/api.ts:14` | `VITE_API_URL=/api` (relative) — AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2C | ใช้ image เดียวได้ทุก env | ต้องเสร็จก่อน 3 |
| 6 | backend อ่าน IP จริงหลัง proxy — AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2A | เชื่อ `X-Real-IP` เฉพาะเมื่อ peer อยู่ใน `TRUSTED_PROXY_CIDRS` = `127.0.0.1/32` | backend ผูก loopback และ nginx ส่ง IP จริงมาให้ | ต้องเสร็จก่อน 3 |
| 7 | `images.yml` build-arg `KUBECTL_VERSION` | pin ให้ตรงกับ `k3s_version` | build ซ้ำแล้วได้ผลเหมือนเดิม | 1 |
| 8 | `k8s/siem/layer3-processing/01-vector-aggregator-configmap.yaml:261`, `k8s/siem/layer5-detection/02-sigma-rules-cronjob.yaml:103`, datasource ใน `00-grafana-deployment.yaml` | `http://100.86.87.27:8000/api/v1/logs` → `http://<PLATFORM_IP>/api/v1/logs` (ผ่าน nginx) และ DB → `postgres.vlab-prod.svc.cluster.local:5432` | IP เก่าฮาร์ดโค้ดไว้ และ backend ไม่เปิด :8000 ออกนอกเครื่องแล้ว | 2 / 4 |
| 9 | `k8s/siem/kustomization.yaml` + `layer*/kustomization.yaml` (ใหม่), `docs/SETUP_TEST.md` ขั้น 5.5 | ตั้ง wave ทีละ layer และเปลี่ยนคำสั่งเป็น `kubectl apply -k` | ลำดับ layer | 2 |
| 10 | Ansible | role ใหม่ `argocd` + play ใน `site.yml`, `k3s-agent` เพิ่ม `--node-label` / `--node-taint` เฉพาะ group `platform`, inventory เพิ่ม group `platform`, ลบ task ที่ย้ายไป Argo CD (ข้อ 7.1) | Solution D12 | 2 |
| 11 | `tailscale/vlab-acl.hujson.example`, `vlab-tags.tsv.example` | `tag:vlab-platform` + กฎ + test (Solution ข้อ 5.3) | worker เปิด portal ได้ แต่เข้า Argo CD / staging / SSH ไม่ได้ | 0 |
| 12 | `.github/workflows/backend-tests.yml` | ย้าย path filter เข้า job `changes` + เพิ่ม job `Admin tests` (ข้อ 3.1) | required check ไม่ค้าง และ `tests/admin` ได้รันจริง | 0 |
| 13 | `web-portal/docker-compose.prod.yml`, `ansible/roles/web-service` | เก็บไว้จนผ่าน Phase 4 ไป 2 สัปดาห์ แล้วค่อยลบ | ใช้เป็นทาง rollback ตอน cutover | 5 |

---

## 10. งานประจำวัน

### 10.1 แก้โค้ดปกติ

1. เปิด PR แล้วรอให้ check เขียว + review
2. merge แล้วภายใน ~15 นาที staging จะเปลี่ยนเอง ดูได้ที่ Argo CD UI `http://<PLATFORM_IP>:30808` → `web-portal-staging`
3. ทดสอบที่ `http://<PLATFORM_IP>:8180`

### 10.2 ขึ้น prod

```bash
argocd app get web-portal-staging -o json | jq -r '.status.summary.images[]'
```

```bash
git tag v1.4.0 <sha ที่ staging ใช้>
```

```bash
git push origin v1.4.0
```

จากนั้น review PR "release: v1.4.0 → prod" แล้ว approve + merge ระบบจะ sync เองเมื่อพ้นเวลาเรียน

### 10.3 Hotfix ระหว่างเวลาเรียน

PR fix → merge → รอ staging เขียว → tag `v1.4.1` → merge PR release แล้วกด sync เอง (deny window มี `manualSync: true`)

```bash
argocd app sync web-portal-prod
```

### 10.4 Rollback

```bash
# ทางหลัก (GitOps): revert commit ที่ bump prod แล้วเปิด PR → merge
git revert <commit "chore(deploy): prod → v1.4.0">
```

```bash
# ทางด่วน (ไม่รอ PR) — Argo CD จะปิด auto-sync ให้เอง ต้องตามด้วย revert ใน Git แล้วเปิด auto-sync คืน
argocd app history web-portal-prod
```

```bash
argocd app rollback web-portal-prod <HISTORY_ID>
```

ถ้า migration ทำข้อมูลเสีย: ปิด auto-sync → `kubectl -n vlab-prod scale deploy/backend --replicas=0` → `pg_restore --clean --if-exists` จากไฟล์ `/backups/presync-*.dump` ล่าสุด (รันใน Job / pod ที่ mount PVC `db-backups`) → revert release → เปิด auto-sync

### 10.5 เพิ่ม env var ใหม่

ใน PR เดียวกับโค้ด ให้เพิ่มทั้งใน `app/configs/settings.py` และใน `overlays/staging/backend.env` + `overlays/prod/backend.env`
ConfigMap มี hash ต่อท้ายชื่อ เมื่อค่าเปลี่ยน pod จะ restart เอง

### 10.6 เพิ่ม / เปลี่ยน secret

แก้ค่าในไฟล์ group_vars (gitignore) → `python script/seal-secrets.py --env <env> ...` → เพิ่มเลข `vlab.io/secrets-rev` → PR

### 10.7 migration ใหม่

เขียน migration แบบ expand-only (Solution ข้อ 7) แล้วระบบจะรันใน `db-migrate` ตอน sync ดู log ได้ด้วยคำสั่งนี้

```bash
kubectl -n vlab-staging logs job/db-migrate
```

### 10.8 ดูสถานะ / log

```bash
argocd app list
```

```bash
argocd app diff web-portal-prod
```

```bash
kubectl -n vlab-prod logs deploy/backend -f
```

```bash
kubectl -n vlab-prod logs job/smoke
```

---

## 11. Troubleshooting

| อาการ | สาเหตุที่น่าจะเป็น | แก้ |
|---|---|---|
| pod backend / frontend ของ staging ค้าง `Pending` ("didn't have free ports") | hostNetwork พอร์ตชนกับ prod หรือตัวเก่ายัง terminate ไม่เสร็จ | เช็ก patch `containerPort` ของ overlay และรอ `terminationGracePeriodSeconds` |
| frontend `CrashLoopBackOff` "bind() … failed (98: Address in use)" | พอร์ต 80 ถูก svclb ของ Traefik ใช้อยู่ | Solution ข้อ 9 แถวแรก |
| `ImagePullBackOff` | `images.yml` ล้ม (ไม่มี tag) หรือ package บน GHCR ยังเป็น private | ดู run ของ Actions / ตั้ง package เป็น public |
| SealedSecret "no key could decrypt secret" | seal ด้วย cert ผิดตัว หรือเปลี่ยนชื่อ / namespace (scope strict) | `kubeseal --fetch-cert` ใหม่ แล้ว seal ใหม่ |
| `db-migrate` ล้ม | migration / ข้อมูลไม่เข้ากัน | อ่าน log แล้วแก้ด้วย PR ใหม่ (fix forward) ถ้าข้อมูลเสียให้ restore (ข้อ 10.4) |
| `whoami-from-lab` ล้มด้วย "มี NAT / proxy คั่น" | frontend ไม่ได้ใช้ hostNetwork, nginx ไม่ได้ส่ง `X-Real-IP`, หรือ backend ไม่เชื่อ `127.0.0.1` | เช็กข้อ 7.2 และ AWS_LAB_GATEWAY.md ข้อ 16 เฟส 2A |
| `whoami-from-lab` ค้างจนหมดเวลา | เครื่องแลปที่ระบุใน `nodeSelector` ปิดอยู่ | เปลี่ยนเครื่องหรือตัด component ออก |
| Argo CD `OutOfSync` ตลอดที่ field เดิม | controller อื่นแก้ field นั้นหลัง apply | เพิ่ม `ignoreDifferences` เฉพาะ field นั้นใน Application |
| ComparisonError "namespace skypilot not found" | Ansible `skypilot_reset=true` ลบ ns ไป | รัน role `skypilot-node` จนเสร็จแล้วกด Refresh |
| staging สร้าง pod lab ไม่ได้ (403) | RBAC ของ `vlab-staging-labs` ขาด verb | `kubectl auth can-i --as=system:serviceaccount:vlab-staging:vlab-backend <verb> <resource> -n vlab-staging-labs` แล้วเติมใน `backend-rbac.yaml` |
| prod merge แล้วไม่ deploy | อยู่ใน deny window | ปกติ ถ้าด่วนให้ดูข้อ 10.3 |
