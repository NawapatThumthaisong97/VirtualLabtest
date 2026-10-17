# VirtualLab RBAC

## 1. Database and Authorization Model

The RBAC schema is additive to the existing application schema. `users` retains its current UUID primary key and legacy `role` column; authorization assignments are normalized into these tables:

| Table | Purpose | Keys and lifecycle |
|---|---|---|
| `users` | Existing user identities | Existing UUID primary key; referenced by `user_roles` |
| `roles` | `Student`, `Instructor`, and `Admin` role definitions | Integer primary key, unique `role_name`, `is_active`, `deleted_at` |
| `permissions` | Domain-scoped permissions | Integer primary key, unique `(resource_domain, permission_name)`, `is_active`, `deleted_at` |
| `user_roles` | User-to-role assignments | Composite primary key `(user_id, role_id)`; revoke by setting `deleted_at` |
| `role_permissions` | Role-to-permission grants | Composite primary key `(role_id, permission_id)`; seed-owned grants are marked and soft-disabled with `deleted_at` |

Mapping-table foreign keys cascade when a user is deleted and restrict hard deletion of referenced roles or permissions. Roles and permissions should normally be disabled/soft-deleted instead. The mapping-table primary keys and reverse lookup indexes support authorization checks; permission domain/name and role name are unique.

Permission codes use `domain:permission[:scope]`; hierarchical permission names are supported, for example `kubernetes:workloads:view:assigned`. JWTs include `user_id` and role names, never the permission list. The role claim is informational: every protected request checks current role assignments and active permissions in PostgreSQL so role revocation takes effect without waiting for token expiry.

## 2. Role Matrix

Only the allow permissions below are seeded. Anything not listed is denied by default.

| Domain | Student | Instructor | Admin |
|---|---|---|---|
| **Cluster** | `clusters:create:self`, `clusters:read:self`, `clusters:delete:self`; creation reserves compute/storage quota under a locked quota row | `clusters:create:course`, `clusters:read:course`, `clusters:update:course`, `clusters:delete:course`; target cluster and course are checked together | `clusters:manage:global` |
| **Kubernetes** | `kubernetes:cluster_admin:self`; only inside a cluster owned by that student | `kubernetes:workloads:view:assigned`, `kubernetes:workloads:exec:assigned`, `kubernetes:workloads:logs:assigned`; no cluster-admin grant | `kubernetes:cluster_admin:global` |
| **Network / ZTNA** | `network:tailscale:access:self`; no inter-cluster grant | `network:tailscale:access:assigned` | `network:policies:manage:global`, `network:tailscale:manage:global`, `network:egress_allowlist:manage:global` |
| **Storage / Registry** | `storage:images:pull:self`, `storage:images:push:self`, `storage:data:read_write:self`; no system-image push grant | `storage:images:push:course`, `storage:datasets:manage:course` | `storage:r2:manage:global`, `storage:registry:manage:global`, `storage:quotas:manage:global` |

The application RBAC check is not a replacement for infrastructure enforcement. OPA/Kyverno, Kubernetes RBAC/network policies, Tailscale ACLs, Squid egress rules, and registry/bucket policies must independently enforce global guardrails and deny inter-cluster or system-image access.

## 3. Personal Cluster Paradigm

**Local Admin, Global Guardrails, Zero Trust:** a student may be `cluster-admin` inside their own isolated personal cluster, but that authority ends at the cluster boundary. The backend checks ownership for personal-cluster and self-scoped Kubernetes/network requests using the cluster name stored on the user's `sessions` records. OPA/Kyverno and Kubernetes/network policies remain authoritative for global constraints. Tailscale provides authenticated private access, while the Squid proxy limits outbound traffic to an explicit allowlist.

The current backend has no first-class `clusters` or R2 repository ownership table. Consequently:

- Cluster ownership checks use `sessions.sky_cluster_name` and `sessions.user_id`; cluster routes should use the stored cluster name as their path context, or inject a custom scope checker if using another identifier.
- Instructor cluster access is tied to the instructor's `Enrollment` for the lab's course.
- Student session provisioning reserves the requested CPU-hours and disk MB across every user quota period while holding those quota rows `FOR UPDATE`. A failed SkyPilot launch releases the reservation only after cluster cleanup succeeds; uncertain cleanup intentionally retains the reservation.
- Personal bucket/repository checks must supply a `storage:self` scope checker backed by authoritative bucket/repository ownership. No such ownership model exists in the current schema, so the default policy fails closed.
- The existing Kubernetes router is global and therefore requires `kubernetes:cluster_admin:global`. Network and storage routers do not currently exist; add routes only with resource-specific policies.

These checks are deliberate integration gates, not permission grants. Connect them to the authoritative cluster, quota, registry, and R2 services before exposing those operations.

## 4. Developer Onboarding

After pulling `main`, create a feature branch. The leading slash in `/feature/XXXX` is notation; Git branch names should be created without a leading slash:

```bash
git switch main
git pull --ff-only
git switch -c feature/XXXX
```

### Windows / PowerShell Migration Walkthrough

Run these commands from the repository root. The migration script is under `web-portal/backend/script`, so running `python script/init_db.py` from the repository root will fail with a file-not-found error.

For the local development database, start PostgreSQL from the repository root:

```powershell
docker compose -f .\web-portal\docker-compose.yml up -d db
```

Then move into the backend directory and use its virtual environment. The dependency file is named `requirement.txt` (singular):

```powershell
Set-Location .\web-portal\backend
if (-not (Test-Path .\.venv\Scripts\python.exe)) { python -m venv .venv }
if (-not (Test-Path .\.env)) { Copy-Item .env.example .env }
notepad .env
```

In `web-portal/backend/.env`, set `DATABASE_URL` to the database you intend to migrate. For the local Compose database above, the example URL is `postgresql://postgres:password@localhost:5432/virtual_lab`; it is for development only. Each command invocation prints exactly one token. Run it once for `SECRET_KEY`, then run it again to generate a different value for `ADMIN_SESSION_SECRET_KEY`:

```powershell
# Run once; put this output on the SECRET_KEY= line in .env.
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"

# Run again; put this different output on the ADMIN_SESSION_SECRET_KEY= line.
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Both values must be at least 32 characters and must not be the same. Never commit `.env` or paste real secrets into chat. `TAILSCALE_TRUSTED_PROXY_CIDRS_STR` must contain the immediate proxy IP/CIDR that the backend actually sees; leave it empty if SQLAdmin should remain inaccessible until that proxy is configured. The proxy must strip client-supplied Tailscale identity headers before setting its own.

Install dependencies in the project environment if it is not already provisioned, then verify the database connection and run the schema migration:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirement.txt
.\.venv\Scripts\python.exe -c "from app.configs.db import check_db_connection; assert check_db_connection(), 'Database connection failed'"
.\.venv\Scripts\python.exe script\init_db.py
.\.venv\Scripts\python.exe -m alembic current
```

The expected current revision is `20261013_04`. Then seed roles, permissions, and assignments separately:

```powershell
.\.venv\Scripts\python.exe script\run_rbac_seed.py
```

For the local Compose database only, verify that all three roles and their grants exist (run from `web-portal/backend`):

```powershell
docker compose -f ..\docker-compose.yml exec db psql -U postgres -d virtual_lab -c "SELECT r.role_name, count(rp.permission_id) AS permission_count FROM roles r LEFT JOIN role_permissions rp ON rp.role_id = r.id AND rp.deleted_at IS NULL GROUP BY r.role_name ORDER BY r.role_name;"
```

`init_db.py` delegates to Alembic and never calls `Base.metadata.create_all`. A fresh database runs the baseline and subsequent revisions. For an unversioned database with the complete legacy schema, it stamps the detected baseline/RBAC revision and upgrades. Revision `20261013_03` repairs RBAC soft-delete/provenance columns; revision `20261013_04` repairs the known legacy `courses`, `lab_images`, and `sessions` column drift, preserves old columns, and backfills `sessions.lab_image_id` only when `image_ref` exactly matches one `repository:tag`. Partial or unrecognized schemas are rejected. The RBAC seeder is separate from sample data, creates missing user-role assignments from legacy `users.role` without reactivating revoked assignments, upserts seed-owned grants, and soft-disables stale seed-owned grants without deleting custom grants. Do not edit or delete an applied migration; add a new reversible migration instead. Downgrading the baseline drops the entire application schema and data, so do not use it as a routine rollback.

### Troubleshooting

| Symptom | What to check |
|---|---|
| `can't open file ... script/init_db.py` | Check `Get-Location`; run `Set-Location .\web-portal\backend` from the repository root first. |
| Pydantic says `SECRET_KEY` or `ADMIN_SESSION_SECRET_KEY` is missing | Confirm `web-portal/backend/.env` exists and contains two separate random values, each at least 32 characters. |
| PostgreSQL connection refused / `OperationalError` | From repo root run `docker compose -f .\web-portal\docker-compose.yml ps`; verify the `db` service is healthy and `DATABASE_URL` points to the correct host/port/database. |
| `Database has a partial ... schema` or `unrecognized tables` | Stop. Do not drop tables or run `create_all`; take a backup and have the existing schema reviewed before adding a migration/adoption path. |
| Current revision is not `20261013_04` | Run `python -m alembic current` from the backend directory and inspect `python -m alembic history`; do not stamp or downgrade by guesswork. |

If the full backend dependency install fails on native Windows because a dependency requires Unix modules, run the migration from the project's Linux/WSL/container environment with the same backend `.env`; do not install packages globally.

Protect a RESTful plural-resource route with the dependency. Cluster-scoped dependencies must receive a `ResourceContextPolicy`; the default implementation validates student ownership and instructor course assignment using existing session/enrollment records.

```python
from fastapi import APIRouter, Depends

from app.middlewares.rbac import verify_permission
from app.services.rbac_service import ResourceContextPolicy

router = APIRouter(prefix="/clusters", tags=["clusters"])
cluster_context_policy = ResourceContextPolicy()


@router.delete(
    "/{cluster_name}",
    dependencies=[
        Depends(
            verify_permission(
                "clusters:delete:self",
                context_policy=cluster_context_policy,
            )
        )
    ],
)
def delete_cluster(cluster_name: str):
    ...
```

Personal cluster creation through `/sessions` uses `QuotaReservationService` before contacting SkyPilot. The reservation estimate is requested CPU units times image lifespan and image disk size in MB; this is conservatively charged through the quota window. The code uses Monday-based weeks, calendar months, and Jan-Jun/Jul-Dec semesters. Confirm those window definitions match institutional policy before production use.

```python
reservation_ids = quota_reservation_service.reserve_personal_cluster(
    user_id, compute_hours, storage_mb
)
```

For storage operations, inject a checker backed by the authoritative bucket/repository ownership data:

```python
storage_policy = ResourceContextPolicy(
    scope_checkers={"storage:self": owns_personal_storage_resource},
)
```

Storage scope checker signature is `(db, user_id, resource_id, course_id)`; it must prove ownership/assignment from authoritative storage metadata. Never trust a client-supplied course ID without verifying that the requested cluster or repository belongs to it.

Raise domain exceptions for authorization failures. The global handler serializes them as `ApiResponse(success=False, message="...", error=ErrorDetail(code="...", message="..."))`. Request payloads must use Pydantic schemas, and JSON field aliases follow the project's camelCase convention.

Before opening a PR, run the backend checks relevant to the change and include migration/seeder instructions when applicable. **Every PR requires 2 reviewers.**

> Please strictly follow the rules defined in [📜 ข้อตกลงและระเบียบในการทํางาน (Notion)](NOTION_GUIDELINES_URL).
>
> Replace `NOTION_GUIDELINES_URL` with the team's actual Notion page URL when it is available.