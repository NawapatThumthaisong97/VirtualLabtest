# frontend-tracer

Next.js 14 (App Router) — Tracer Bullet UI

## Purpose
A deliberately minimal "distripped" dashboard for observing ML job execution in real time across the hybrid K3s + AWS stack.

## Structure

```
src/
  app/
    page.tsx              ← Root 3-column layout
    layout.tsx            ← Fonts, global providers
  components/
    JobCommandPanel.tsx   ← JSON input + "Trigger Normal / Burst" buttons
    JobStateTable.tsx     ← Polls GET /api/jobs — shows PENDING→SUCCESS transitions
    LiveLogTerminal.tsx   ← SSE stream from GET /api/logs/{job_id}
  lib/
    api.ts                ← Typed fetch wrappers to FastAPI backend
public/                   ← Static assets
Dockerfile                ← Production image
```

## 3-Column Layout (Bullet 4 scope)

| Column | Component | Data Source |
|:-------|:----------|:------------|
| Left | `JobCommandPanel` | User input → `POST /api/launch` |
| Center | `JobStateTable` | Polls `GET /api/jobs` (PostgreSQL) |
| Right | `LiveLogTerminal` | SSE `GET /api/logs/{job_id}` |

## Constraint Reminders
- ✅ Connects to FastAPI only — no direct DB access
- ✅ All API calls go through Cloudflare Tunnel in production
- ✅ No secrets, credentials, or AWS SDK in this layer
