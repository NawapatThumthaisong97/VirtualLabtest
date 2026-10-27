# Lab Image Security Scan & Delete Pipeline

## Overview
Automated K3s-based security scanning for lab images with R2 webhook triggers, ECR sync, scan orchestration, and UI for image management including delete.

## Changes

### Core Components
**Backend (`web-portal/backend/`)**
- `scan_reconciler.py`: Background task orchestrating scan lifecycle (15s interval, 2 concurrent, retry logic, 7-day cleanup)
- `scan_job_service.py`: K8s Job manifest builder (4-container pipeline, Secret management, presigned URL injection)
- `lab_image_service.py`: Webhook handler (R2 upload → QUEUED), delete with R2+ECR cleanup
- `scan_job_service.py`: Creates K8s Job + Secret with presigned GET URL
- Migration: `20261024_01_lab_image_scan_columns.py` (scan_status, scan_attempts, scan_job_name, scan_started_at, scan_finished_at, scan_summary)
- DELETE `/api/lab-image/{id}`: Removes DB row, R2 archive, ECR image; detaches from labs; instructor/admin only

**Scanner Image (`scan-runner/`)**
- `Dockerfile`: Hardened Alpine + Trivy + skopeo + Python (non-root 10001, read-only rootfs, no setuid/apk)
- `runner.py`: 4-stage pipeline (fetch→validate→scan→publish) with verdict logic, retryable errors, termination log output
- `policy.json`: skopeo trust policy (local archives only, reject all registries)

**Ansible Deployment**
- `roles/scan-runner-image/`: Builds scanner image with digest-pinned base & Trivy, verifies cosign signature, pushes to camp registry
- `roles/ecr-sync/`: systemd timer (OnUnitActiveSec=120s) syncing `vlab/*` to ECR via skopeo + boto3
- `roles/k3s-server/`: Applies `scan-namespace.yaml` (namespace + NetworkPolicy isolation)

**Frontend (`web-portal/frontend/src/`)**
- `LabImageTab.tsx`: Upload form, scan status badges, auto-refresh (10s) for in-progress scans, delete button with confirmation
- `LabImageForm.tsx`: Repository name validation (`vlab/` prefix, reserved names blocked)
- `ScanStatusBadge.tsx`: Visual status (queued/running/passed/failed/error)
- `LabsTab.tsx`: Lab dropdown bound to approved lab images

### Key Features
**Scan Flow**
1. Instructor uploads .tar → presigned PUT → R2
2. Cloudflare Worker → webhook → backend sets `QUEUED`
3. Reconciler (15s loop) → creates Job with 4 init containers + 1 main:
   - `fetch`: Downloads from presigned URL, validates size/ETag
   - `validate`: Checks tar structure, arch, ports
   - `scan`: Trivy (vuln+secret), policy evaluation
   - `publish`: skopeo copy to camp registry if PASS
4. Reconciler reads termination message → updates DB (`PASSED`/`FAILED`/`ERROR`)
5. `PASSED` → `APPROVED` + R2 archive deleted (registry is source of truth)
6. Timer on registry node → ECR sync every ~2min

**Delete Flow**
1. Instructor/admin clicks Delete → confirmation modal
2. Backend checks permissions, verifies no class_slots reference (RESTRICT FK)
3. Detaches from labs (`image_id=NULL`), sessions, schedules
4. Deletes ECR image + repository (if empty) via boto3
5. Deletes R2 archive via S3 API
6. Commits DB changes; rollback on cloud failure (retriable)

**Security**
- Scanner runs non-root, read-only rootfs, NetworkPolicy blocks egress except camp registry
- Secret with presigned URL auto-deleted via ownerReference
- Policy blocks Trivy from pulling from internet (local cache only)
- Repository names forced to `vlab/*` prefix (ECR IAM scope)

### Modified Files
**Backend Models & Schema**
- `models/lab_image.py`: Added scan columns, `ScanStatus` enum, `get_skypilot_resources()`
- `schemas/lab_image_schema.py`: Validation for repository prefix, reserved names, scan status response
- `repositories/lab_image_repository.py`: `has_class_slots()`, `detach_references()`, `delete()`
- `controllers/lab_image_controller.py`: `delete_image()`
- `routes/lab_image_route.py`: `DELETE /lab-image/{id}`
- `adapters/r2_adapter.py`: `delete_object()`
- `adapters/ecr_adapter.py`: Added `EcrAdapter.delete_image()` (batch delete, list, delete repo)
- `configs/settings.py`: Added `LAB_IMAGE_SCAN_*` env vars, `AWS_ECR_ACCESS_KEY_ID/SECRET_ACCESS_KEY`

**Backend Services**
- `kubernetes_service.py`: K8s client wrapper for Job/Secret/Pod operations
- `lab_service.py`: Validates `lab.image_id` belongs to course

**Ansible**
- `site.yml`: Added `scan-runner-image`, `ecr-sync` roles
- `group_vars/all.yml.example`: Added `scan_runner_version`, `ecr_sync_registry`, Vault vars
- `roles/k3s-server/tasks/main.yml`: Apply `scan-namespace.yaml`
- `roles/web-service/defaults/main.yml`, `templates/backend.env.j2`: Scan-related env vars

**K8s**
- `k8s/scan-namespace.yaml`: Namespace `vlab-scan`, NetworkPolicy (deny all ingress, allow egress to registry only), PriorityClass `vlab-scan`

**Frontend**
- `pages/Instructor.tsx`: Added Lab Images tab
- `services/labImage.ts`: API client for list, upload, delete
- `services/lab.ts`: Updated Lab interface with `imageId`

### Tests
- `tests/lab_image/test_scan_launch.py`: Job creation, Secret injection, verdict parsing
- `tests/lab_image/test_lab_image_upload.py`: Upload flow, webhook, scan trigger
- `tests/fakes.py`: Mock K8s client, R2 adapter

### Config Changes
**Backend `.env` additions**
```bash
LAB_IMAGE_SCAN_ENABLED=true
SCAN_RECONCILE_INTERVAL_SECONDS=15
SCAN_MAX_CONCURRENT=2
SCAN_MAX_ATTEMPTS=2
AWS_ECR_ACCESS_KEY_ID=<IAM key with ecr:BatchDeleteImage, ecr:ListImages, ecr:DeleteRepository>
AWS_ECR_SECRET_ACCESS_KEY=<secret>
```

**Ansible Vault vars**
```yaml
vault_ecr_sync_aws_access_key_id: AKIA...
vault_ecr_sync_aws_secret_access_key: ...
```

## Documentation
- `docs/LAB_IMAGE_SCAN_GUIDE.md`: Complete technical reference (replaced LAB_IMAGE_SCAN_PIPELINE.md)
- `docs/LAB_IMAGE_SCAN_ARCHITECTURE.md`: Design decisions, threat model
- `docs/SCAN_RUNNER_IMAGE.md`: Scanner image threat analysis

## Breaking Changes
- `labs.image_id` FK set to `RESTRICT`: cannot delete lab_image if referenced by class_slots (must be NULL-able in slots first or delete slots)
- Repository names must start with `vlab/` (enforced at upload presign)

## Deployment Steps
1. Apply migration: `alembic upgrade head`
2. Build scanner: `ansible-playbook ansible/site.yml --tags scan-runner-image`
3. Deploy ECR sync: `ansible-playbook ansible/site.yml --tags ecr-sync`
4. Set `.env` vars + restart backend
5. Apply K8s namespace: already applied by role `k3s-server` on next Ansible run

## Risks & Mitigations
**Known Gaps**
- Camp registry has no auth: anyone on Tailscale can push to `:5001/vlab/*` → bypasses scan (fix: add htpasswd + ACL split push/pull)
- No unit tests for `runner.py` evaluate_report, detect_archive_format → manual verification only
- ECR sync AccessDenied: needs `ecr:BatchDeleteImage`, `ecr:ListImages`, `ecr:DeleteRepository` on IAM user
- 404 errors in fetch are retried: should be `retryable=False` (1-line fix)

**Tested**
- `vlab/print-test2077:latest` PASSED (3.8MB, 0 CRITICAL vulns)
- `vlab/python-lab:lab-02` ERROR expected (large base image, HIGH vulns → warnings only)
- Reconciler loop stability (survives K3s restart)
- Delete flow with lab detachment

## Files Changed
```
modified: ansible/{site.yml,group_vars/all.yml.example,roles/k3s-server/tasks/main.yml,roles/web-service/{defaults/main.yml,templates/backend.env.j2}}
new:      ansible/roles/{ecr-sync,scan-runner-image}/
new:      k8s/scan-namespace.yaml
new:      scan-runner/{Dockerfile,runner.py,policy.json}
modified: web-portal/backend/{.env.example,app/{adapters/{r2_adapter,ecr_adapter}.py,configs/settings.py,{controllers,routes}/lab_image_*.py,main.py,models/lab_image.py,repositories/lab_image_repository.py,schemas/{lab_image,lab}_schema.py,services/{lab_image,lab,kubernetes}_service.py}}
new:      web-portal/backend/{app/services/{scan_job_service,scan_reconciler}.py,migrations/versions/20261024_01_lab_image_scan_columns.py,tests/lab_image/test_scan_launch.py}
modified: web-portal/backend/tests/{fakes.py,lab_image/{conftest,test_lab_image_upload}.py}
modified: web-portal/frontend/src/{components/instructor/{LabsTab,LabForm,types}.tsx,pages/Instructor.tsx,services/{labImage,lab}.ts}
new:      web-portal/frontend/src/{components/instructor/{LabImageTab,LabImageForm,ScanStatusBadge,formStyles}.tsx,services/labImage.ts}
deleted:  docs/LAB_IMAGE_SCAN_PIPELINE.md
new:      docs/LAB_IMAGE_SCAN_GUIDE.md
```
