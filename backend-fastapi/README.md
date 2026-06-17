# backend-fastapi

FastAPI (async) — Control Plane API + SkyPilot Orchestration

## Purpose
The single non-blocking entry point for all ML job operations. Interfaces directly with SkyPilot SDK for hybrid K3s/AWS execution. No middleware (no Redis, no Celery).

## Structure

```
app/
  main.py               ← App entrypoint, lifespan hooks, CORS config
  routers/
    jobs.py             ← POST /api/launch, GET /api/jobs, GET /api/jobs/{id}
    logs.py             ← GET /api/logs/{job_id} (SSE stream)
    health.py           ← GET /healthz
  models/
    job.py              ← SQLAlchemy ORM: Job (id, state, type, created_at, ...)
    user.py             ← SQLAlchemy ORM: User (for SSO + RBAC)
  schemas/
    job.py              ← Pydantic: JobCreate, JobStatus, JobListResponse
  services/
    skypilot_service.py ← SkyPilot SDK wrapper (async coroutine, no blocking)
  db/
    session.py          ← Async SQLAlchemy engine + session factory
    migrations/         ← Alembic migration scripts

sky_tasks/
  ml_job.yaml           ← 2-tier SkyPilot resource spec (K3s → AWS Spot)
  burst_test.yaml       ← Force-AWS task for Bullet 3B validation

Dockerfile
requirements.txt
.env.example            ← Template (DATABASE_URL only — NO AWS keys here)
```

## Key Design Decisions

### Job Dispatch Flow (Constraint #2)
```python
@router.post("/api/launch", status_code=202)
async def launch_job(payload: JobCreate, db: AsyncSession = Depends(get_db)):
    job = await create_job(db, payload)           # INSERT state=PENDING
    asyncio.create_task(dispatch_job(job.id))     # Non-blocking background task
    return {"job_id": job.id, "state": "PENDING"} # Immediate 202 response
```

### SkyPilot 2-Tier Resource Spec (Constraint #3)
```yaml
# sky_tasks/ml_job.yaml
resources:
  - cloud: kubernetes    # Tier 1: On-Prem K3s (first priority)
  - cloud: aws           # Tier 2: Burst to AWS Spot (fallback)
    use_spot: true
```

### Credentials (Constraint #8)
- **AWS creds:** Injected via `envFrom.secretRef` in Helm deployment — NEVER in `.env` or code
- **K3s access:** Via `ailab-fastapi-sa` ServiceAccount — auto-mounted by Kubernetes

## Constraint Reminders
- ✅ All endpoints are `async def` — zero blocking I/O
- ✅ Job dispatch uses `asyncio.create_task()` — no Celery/Redis
- ✅ SkyPilot SDK called directly from `skypilot_service.py`
- ✅ State persisted in PostgreSQL via async SQLAlchemy session
- ✅ `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` come from K8s Secret only
- ✅ K3s access via ServiceAccount — no kubeconfig file
