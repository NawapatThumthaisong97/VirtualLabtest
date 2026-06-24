# k8s-helm

Helm Chart — Control Plane Deployment on K3s Master Node

## Purpose
Packages and deploys all Control Plane components to the on-prem K3s cluster in a reproducible, version-controlled way.

## Chart Structure

```
Chart.yaml
values.yaml               ← Top-level value overrides (image tags, domains, replicas)
templates/
  fastapi/
    deployment.yaml       ← FastAPI pod (envFrom: aws-credentials Secret, serviceAccountName)
    service.yaml
    serviceaccount.yaml   ← virtuallab-fastapi-sa ServiceAccount
    rbac.yaml             ← ClusterRole + ClusterRoleBinding for SkyPilot K3s access
  frontend/
    deployment.yaml
    service.yaml
  postgresql/
    statefulset.yaml      ← PostgreSQL with PVC
    service.yaml
    pvc.yaml
  nginx-ingress/
    ingress.yaml          ← Routes: /api/* → FastAPI, /* → Frontend
  oauth2-proxy/
    deployment.yaml       ← Google SSO guard
    service.yaml
    configmap.yaml
  cloudflared/
    deployment.yaml       ← Cloudflare Tunnel pod (outbound-init, no inbound port)
    configmap.yaml        ← Tunnel routing rules
  tailscale-router/
    deployment.yaml       ← Advertises On-Prem CIDR to Tailnet (NOT the AWS VPC CIDR)
    configmap.yaml
```

## Critical Template Notes

### fastapi/deployment.yaml — Credential Injection (Constraint #8)
```yaml
spec:
  serviceAccountName: virtuallab-fastapi-sa   # K3s RBAC access for SkyPilot
  containers:
    - name: fastapi
      envFrom:
        - secretRef:
            name: aws-credentials        # AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
        - configMapRef:
            name: fastapi-config         # DATABASE_URL, etc.
```

### tailscale-router/deployment.yaml — CIDR Scope (Constraint #6)
```yaml
# This pod advertises ONLY the on-prem K3s CIDR to the Tailnet.
# The AWS VPC CIDR is advertised by the t4g.nano gateway in AWS (infrastructure/terraform).
args: ["--advertise-routes=<ON_PREM_CIDR>"]
```

## Constraint Reminders
- ✅ `cloudflared` pod: outbound-only — zero inbound ports (Constraint #1)
- ✅ No Redis, no Celery pods anywhere in this chart (Constraint #2)
- ✅ `aws-credentials` Secret must be pre-created by `create-k8s-secrets.sh` before Helm install (Constraint #8)
- ✅ `tailscale-router` advertises On-Prem CIDR only — not AWS VPC CIDR (Constraint #6)
