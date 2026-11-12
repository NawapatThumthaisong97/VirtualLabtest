# Runbook: เปิด lab บน AWS และ portal ให้คนนอก tailnet ใช้ได้

> สถานะ: **ขั้นตอนลงมือ ยังไม่ได้เริ่ม** (2026-11-09) — Pete อนุมัติให้ `vlab-ts-router` รับ traffic จากอินเทอร์เน็ตแล้ว (2026-11-09) ใช้ทางเลือก A
> ใช้คู่กับ [AWS_LAB_PUBLIC_ACCESS.md](AWS_LAB_PUBLIC_ACCESS.md) (design เหตุผล ภาพรวม) และ
> [AWS_LAB_GATEWAY_ROUTER.md](AWS_LAB_GATEWAY_ROUTER.md) (วางเฟส 1 บน `vlab-ts-router`)
> doc นี้ตอบแค่ว่า **ทำอะไร ที่ไฟล์ไหน ตามลำดับไหน และเช็กยังไงว่าผ่าน** เหตุผลของแต่ละข้ออยู่ใน 2 doc นั้น

ทุกขั้นมี 3 ส่วนเสมอ: **แก้อะไร** → **รันอะไร** → **ผ่านเมื่อเห็นอะไร** ถ้าข้อ "ผ่านเมื่อ" ไม่ผ่าน ห้ามไปขั้นถัดไป

---

## 0. ภาพรวม phase

| Phase | ทำอะไร | แตะ prod ไหม | ใครทำ | ขึ้นกับ |
|---|---|---|---|---|
| **0** | เก็บข้อมูล + snapshot router + ตอบคำถามที่ค้าง | ไม่ (อ่านอย่างเดียว + สร้าง AMI) | Pete + dev | — |
| **1A** | backend: token / route ของ gateway (flag ปิดไว้) | deploy ได้ ไม่มีผลจนเปิด flag | dev | 0 |
| **1B** | Terraform: ขยาย router + SG | ใช่ (router stop/start ไม่กี่นาที) | Pete | 0 |
| **1C** | Tailscale: ติด tag router + ACL | ใช่ (ทั้ง tailnet) | admin tailnet | 1B |
| **1D** | Cloudflare: tunnel + DNS wildcard | ใช่ (zone `bell-lab.space`) | Panupong (เจ้าของ zone) | 0 |
| **1E** | Ansible role `lab-gateway` ลง router | ใช่ (router) | dev | 1C, 1D |
| **1F** | เปิด flag + เทสเฟส 1 | ใช่ | dev + tester | 1A, 1E |
| **2A** | backend: อ่าน IP จริงหลัง proxy + cookie ตาม proto | deploy ได้ ไม่มีผลจน nginx เปลี่ยน | dev | 1F |
| **2B** | backend: กด Start แบบ async (ไม่รอเกิน 100 วิ) | deploy ได้ ปิด flag ไว้ | dev | 1F |
| **2C** | frontend: เรียก `/api` แบบ relative + poll สถานะ | ใช่ (rebuild frontend) | dev | 2B |
| **2D** | compose + nginx: proxy `/api` + cloudflared ของ portal | ใช่ (web-service) | dev | 2A, 2C |
| **2E** | Ansible `web-service`: ตัวแปร / env / whoami ใหม่ | ใช่ | dev | 2D |
| **2F** | Cloudflare tunnel ของ portal + SSO | ใช่ | Panupong + dev | 2E |
| **2G** | เทสเฟส 2 | — | dev + tester | 2F |

```
0 ──┬── 1A ───────────────────────────┐
    ├── 1B ── 1C ──┐                   ├── 1F ──┬── 2A ──┐
    └── 1D ────────┴── 1E ─────────────┘        └── 2B ── 2C ──┴── 2D ── 2E ── 2F ── 2G
```
1A ทำคู่กับ 1B–1E ได้ (flag ปิดไว้ ไม่มีผลกับ prod)

---

## 1. สิ่งที่ต่างจาก 2 doc เดิม (เจอตอนไล่โค้ด 2026-11-09)

| # | doc เดิมบอก | ของจริงในโค้ด | runbook นี้ทำ |
|---|---|---|---|
| D1 | ติด tag router ผ่าน admin console | `script/tailscale-acl.sh` ติด tag ผ่าน API (`POST /device/{id}/tags`) ไม่ได้เรียก `tailscale up` จึงไม่ล้าง flag | เพิ่มบรรทัดใน `tailscale/vlab-tags.tsv` แล้ว `apply` (ทำซ้ำได้ มี backup) |
| D2 | แก้ `tailscale/vlab-acl.hujson` | ไฟล์นี้ **gitignore** อยู่ใน git มีแค่ `.example` | แก้ไฟล์ของตัวเอง + อัปเดต `.example` ใน git ให้คนอื่นเห็น |
| D3 | `_lab_envs` (AWS) ส่ง env ของ gateway | `_lab_envs` ใช้ร่วมกันทั้ง K8s และ AWS และ token ต้องรู้ **ก่อน** สร้าง task แต่ `_new_sky_session` สร้าง task ก่อนสร้าง record | สุ่ม token ก่อน `create_fastapi_task` แล้วส่งเข้า `_build_aws_task` เท่านั้น |
| D4 | nginx (bridge) ส่ง `X-Real-IP $remote_addr` | comment ใน `docker-compose.prod.yml` บอกว่าเคยเจอ (2026-10-23) traffic จาก `tailscale0` เข้า container แบบ bridge ถูก MASQUERADE ทุกคนกลายเป็น `172.18.0.1` | ให้ nginx ใช้ `network_mode: host` แบบเดียวกับ backend (ข้อ 2D) **ต้องยืนยันบนเครื่องจริง** |
| D5 | Cloudflare ตัดที่ 100 วิ → ทำ Start เป็น async | เครื่องที่ prelaunch ไว้แต่ยัง PENDING ก็รอใน request ได้นานถึง `JOB_START_TIMEOUT` เหมือนกัน | ทำ async ทั้งทาง launch ใหม่และทาง claim (ข้อ 2B) |
| D6 | inventory มี group `webservice` | `site.yml` ใช้ `hosts: webservice` แต่ `inventory.yml.example` ตั้งชื่อ group ว่า `webportal` ส่วน inventory ของ Pete คือ `ansible/inventory.home.yml` (group `webservice` host `vlab-web`) — `ansible/inventory.yml` บางเครื่องเป็น cluster อื่น (ไม่มี webservice) | ทุกคำสั่ง ansible ใน runbook นี้ใช้ `-i inventory.home.yml` เช็กก่อนรันว่าชี้ cluster ของ Pete |
| D7 | `credit_specification unlimited` | T3 เปิด unlimited เป็นค่าเริ่มต้นอยู่แล้ว | ใส่ไว้ให้เห็นชัดใน terraform ไม่เปลี่ยนพฤติกรรม |
| D8 | ลงทะเบียน SSO callback เป็น `https://vlab.bell-lab.space/api/auth/sso/callback` | frontend ส่ง `redirect_uri = ${window.location.origin}/auth/callback` เอง (`AuthContext.tsx:56`) = **หน้า frontend** ไม่ใช่ path ของ backend `GOOGLE_REDIRECT_URI` เป็นแค่ค่าสำรอง | ลงทะเบียน `https://vlab.bell-lab.space/auth/callback` (ข้อ 2E.4 / 2F) |
| D9 | — | หน้า admin (`SessionAdmin` ใน `app/main.py:135`) แสดงทุก column ยกเว้น `endpoints` → `gateway_token` จะโผล่ในหน้า admin | exclude `gateway_token` + `upstreams` (ข้อ 1A.6) |
| D10 | ส่ง `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` ให้ Vite | ตรวจ source ของ Vite 8 (`web-portal/frontend/node_modules/vite`) แล้วรองรับจริง แต่ music-lab ใช้ `vite ^5.4.0` ซึ่ง `npm install` ใน Dockerfile จะได้ 5.4.x ตัวล่าสุด (มี host check) ยังไม่ได้ยืนยันว่า 5.4.x อ่าน env นี้ | เช็กใน container ก่อนเปิด flag (ข้อ 1F.0) ไม่รองรับ → แก้ `music-lab/client/vite.config.js` |
| D11 | — | wildcard `*.bell-lab.space` แบบ Proxied ได้ทุก setting ของ zone (cache, Rocket Loader, Bot Fight Mode) ซึ่งอาจแก้ HTML / cache JS / challenge request ของ code-server และ Vite | เพิ่ม Cache Rule + Configuration Rule ของ `l-*` (ข้อ 1D) |
| D12 | — | Traefik เปิด `checkNewVersion` เป็นค่าเริ่มต้น (ต่อออกเน็ตเอง) | ปิดใน `traefik.yml` (ข้อ 1E) |
| D13 | พอร์ตนอก `3000–9999` ไม่ใส่ตาราง | นักศึกษาจะไม่เห็นปุ่มของพอร์ตนั้นเลยบน AWS (บนเครื่องแลปยังเห็น) | บอกอาจารย์ในคู่มืออัปโหลด lab image ว่าพอร์ตต้องอยู่ในช่วงนี้ |
| D14 | — | `LabDetail.tsx` เก็บ session แค่ใน state รีเฟรชหน้าแล้วหาย (Start ซ้ำได้ 409) — มีอยู่แล้ว ไม่ใช่ของใหม่ แต่ทาง async ของเฟส 2 ทำให้เจอบ่อยขึ้น | ข้อ 2C.2 โหลด session ที่เปิดอยู่ตอนเข้าหน้า |
| D15 | backend รันที่ `<web-service tailscale ip>` | **VM `webservice`** (hostname Tailscale `vlab-web`, `100.102.72.39`, `tag:vlab-server`) รัน docker compose ของ role `web-service` (backend + frontend + Postgres) **ไม่ใช่ pod ใน K8s** — `k8s/auth/06-backend-deployment.yaml` เป็น design เก่าของ Issue #81 ไม่ได้ deploy (ที่มา: `docs/archive/NextToU.md` ข้อ webservice, commit `0beebbb`, `bf5de8d`) VM นี้เป็น VirtualBox บน ThinkPad ของ Pete | ACL / `lab_gateway_backend_url` ใช้ `100.102.72.39:8000` ยืนยันกับ Pete ก่อน 1C ว่ายังเป็นเครื่องนี้ (ข้อ 0.1) |
| D16 | สร้าง DNS `*` CNAME ใหม่ | **มี `*.bell-lab.space` อยู่แล้ว** (2026-11-09: `l-test-8080.bell-lab.space` ตอบ Cloudflare **521** = proxied ไปที่ origin IP ที่ไม่ตอบ ไม่ใช่ tunnel) ส่วน `skypilot.bell-lab.space` มี record ของตัวเอง (ตอบ 1033 = tunnel ไม่มี connector) | 1D: **แก้** record `*` เดิมให้ชี้ tunnel ใหม่ จดค่าเดิมไว้ถอย |

---

## Phase 0: เตรียมก่อนแตะอะไร

### 0.1 ตอบคำถามที่ค้าง (เขียนคำตอบลงท้าย doc นี้ ข้อ 9)

- [x] Pete อนุมัติให้ router รับ traffic จากอินเทอร์เน็ตผ่าน tunnel (2026-11-09)
- [x] เจ้าของ Cloudflare account + domain `bell-lab.space` = Panupong (domain จดที่ Namecheap แต่ nameserver ชี้ Cloudflare แล้ว `patryk` / `emely.ns.cloudflare.com` = full setup ไม่ต้องแก้อะไรที่ Namecheap)
- [ ] ยืนยันกับ Pete ว่า backend ยังรันที่ VM `webservice` / `vlab-web` `100.102.72.39` (D15) และ VM อยู่บน ThinkPad
      → ThinkPad ปิด = ทั้ง portal ล่มอยู่แล้ว gateway ไม่ได้เพิ่มจุดล่มใหม่ แต่ถ้าจะใช้สอนจริงควรย้าย VM ไปเครื่องที่เปิดตลอด
- [ ] record `*.bell-lab.space` เดิม (D16) ใช้กับอะไรอยู่ไหม (เปิด Cloudflare → DNS → Records ดูว่า `*` ชี้ไปไหน)
- [ ] ช่วงพอร์ต `3000–9999` พอไหม (music-lab ใช้ 8080 / 5173 / 8443)
- [ ] ยอมให้ public IPv4 ของ router เปลี่ยนตอนขยายเครื่องไหม

### 0.2 ค่าที่ต้องจดไว้ใช้ทั้ง runbook

| ชื่อในเอกสารนี้ | หาจาก |
|---|---|
| `<ROUTER_TS_IP>` | `tailscale status` บนเครื่องไหนก็ได้ในทีม หา `vlab-ts-router` |
| `<BACKEND_TS_IP>` | Tailscale IP ของ VM `webservice` (= `webservice_bind_ip`) ตาม `docs/archive/NextToU.md` คือ `100.102.72.39` เช็กซ้ำด้วย `tailscale status \| grep vlab-web` |
| `<ROUTER_INSTANCE_ID>` | `terraform -chdir=terraform state show aws_instance.ts_router \| grep '^ *id '` |
| `<SG_TS_ROUTER_ID>` | `terraform -chdir=terraform state show aws_security_group.ts_router \| grep '^ *id '` |
| `<SG_LAB_ID>` | `terraform -chdir=terraform state show aws_security_group.lab_instances \| grep '^ *id '` |

### 0.3 เก็บสถานะ router (SSM Session Manager)

```bash
aws ssm start-session --target <ROUTER_INSTANCE_ID> --profile <ของ Pete>
```
บน router:
```bash
tailscale status
tailscale debug prefs
sudo iptables -S FORWARD; sudo iptables -t nat -S
sysctl net.ipv4.ip_forward
free -m; df -h
systemctl list-units --type=service --state=running
```
**ผ่านเมื่อ:** แปะผลทั้งหมดลง issue แล้ว (ใช้เทียบหลังแก้ทุกขั้น)

### 0.4 snapshot router

```bash
aws ec2 create-image --no-reboot --instance-id <ROUTER_INSTANCE_ID> \
  --name vlab-ts-router-before-gateway --profile <ของ Pete>
```
**ผ่านเมื่อ:** AMI ขึ้นสถานะ `available` ใน console

### 0.5 เทส baseline (ก่อนแก้)

กด Start lab music-lab แบบ AWS จากเครื่องนอกห้องแลป 1 ครั้ง จดเวลา launch และเปิด `http://10.10.2.x:8443` จากเครื่องใน tailnet ได้
**ผ่านเมื่อ:** เปิดได้ (ใช้เป็นเกณฑ์เทส R1–R3 ข้อ 1F)

---

## Phase 1A: backend ของ gateway (flag ปิด)

ทำบน branch `feature/lab-gateway` ทั้งหมด merge ได้ก่อน infra เสร็จ เพราะ `LAB_GATEWAY_ENABLED=false` ไม่เปลี่ยนพฤติกรรมเดิม

### 1A.1 `web-portal/backend/app/configs/settings.py`

เพิ่มใน class Settings (ใกล้กลุ่ม `PRELAUNCH_*`)
```python
    # lab gateway (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md) ปิด = endpoint ของ lab AWS เป็น private IP แบบเดิม
    LAB_GATEWAY_ENABLED: bool = False
    LAB_GATEWAY_DOMAIN: str = ""                      # เช่น bell-lab.space
    LAB_GATEWAY_TOKEN: str = ""                       # Traefik ส่งมาใน X-Gateway-Token ต้อง >= 32 ตัวเมื่อเปิด
    LAB_GATEWAY_PORT_MIN: int = 3000
    LAB_GATEWAY_PORT_MAX: int = 9999
    LAB_GATEWAY_UPSTREAM_CIDRS_STR: str = "10.10.2.0/24,10.10.3.0/24"
```
เพิ่ม validator (แบบเดียวกับที่บังคับ `SECRET_KEY` ≥ 32): ถ้า `LAB_GATEWAY_ENABLED` แล้ว `LAB_GATEWAY_DOMAIN` ว่าง หรือ `len(LAB_GATEWAY_TOKEN) < 32` → raise ให้ backend ไม่ start

### 1A.2 `web-portal/backend/app/models/session.py`

ต่อท้าย column ของ `Session`
```python
    # lab gateway: token ใน hostname (l-<token>-<port>.<domain>) และปลายทางจริงที่ Traefik ส่งต่อ
    # endpoints (เดิม) = URL ที่นักศึกษาเปิด / upstreams = {"8443": "http://10.10.2.14:8443"}
    gateway_token = Column(String(32), nullable=True, unique=True)
    upstreams = Column(JSONB, nullable=True)
```
**ห้าม** เพิ่ม 2 field นี้ใน `SessionResponse` (`app/schemas/session_schema.py`) — `GET /sessions/{id}` ต้องไม่คืน upstream ภายใน

### 1A.3 migration ใหม่ `web-portal/backend/migrations/versions/2026MMDD_01_session_lab_gateway.py`

เช็ก head ก่อน: `docker compose exec backend alembic heads` (ตอนเขียน doc นี้คือ `20261031_01`)
```python
"""lab gateway: sessions.gateway_token + sessions.upstreams (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md)"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "2026MMDD_01"
down_revision = "20261031_01"   # ใส่ head จริงตอนสร้าง
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("gateway_token", sa.String(32), nullable=True))
    op.add_column("sessions", sa.Column("upstreams", JSONB, nullable=True))
    op.create_unique_constraint("uq_sessions_gateway_token", "sessions", ["gateway_token"])


def downgrade() -> None:
    op.drop_constraint("uq_sessions_gateway_token", "sessions", type_="unique")
    op.drop_column("sessions", "upstreams")
    op.drop_column("sessions", "gateway_token")
```
deploy ไม่ต้องสั่งเพิ่ม: `script/init_db.py` (ansible task "Create database schema") รัน alembic upgrade ให้

### 1A.4 `web-portal/backend/app/services/lab_gateway_service.py` (ใหม่)

ฟังก์ชันล้วน ทดสอบได้โดยไม่ต้องมี SkyPilot
```python
"""ตาราง route ของ Traefik (HTTP provider) — docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md"""
import base64, ipaddress, logging, secrets
from urllib.parse import urlparse

from sqlalchemy import or_
from app.configs.settings import settings
from app.models.session import Session as SessionModel, SessionStatus

logger = logging.getLogger(__name__)


def new_token() -> str:
    """80 bit → base32 ตัวเล็ก 16 ตัว (ใช้ใน DNS label ได้)"""
    return base64.b32encode(secrets.token_bytes(10)).decode().lower()


def public_host(token: str, port) -> str:
    return f"l-{token}-{port}.{settings.LAB_GATEWAY_DOMAIN}"


def port_allowed(port) -> bool:
    return str(port).isdigit() and settings.LAB_GATEWAY_PORT_MIN <= int(port) <= settings.LAB_GATEWAY_PORT_MAX


def public_endpoints(token: str, ports) -> dict[str, str]:
    return {str(p): f"https://{public_host(token, p)}" for p in ports if port_allowed(p)}


def gateway_envs(token: str, ports) -> dict[str, str]:
    """env ที่ส่งเข้า container ของ lab บน AWS (ดู AWS_LAB_PUBLIC_ACCESS.md ข้อ 4.6)"""
    envs = {"__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS": f".{settings.LAB_GATEWAY_DOMAIN}"}
    envs.update({f"VLAB_PUBLIC_URL_{p}": url for p, url in public_endpoints(token, ports).items()})
    return envs


def _upstream_ok(url: str) -> bool:
    try:
        parsed = urlparse(url)
        ip = ipaddress.ip_address(parsed.hostname)
    except (ValueError, TypeError):
        return False
    nets = [ipaddress.ip_network(c.strip()) for c in settings.LAB_GATEWAY_UPSTREAM_CIDRS_STR.split(",") if c.strip()]
    return any(ip in n for n in nets) and port_allowed(parsed.port)


def build_routes(db) -> dict:
    rows = (
        db.query(SessionModel)
        .filter(
            SessionModel.status == SessionStatus.RUNNING,
            SessionModel.is_cloud.is_(True),
            SessionModel.gateway_token.isnot(None),
            SessionModel.upstreams.isnot(None),
            SessionModel.deleted_at.is_(None),
            # prelaunch ที่ยังไม่มีคนรับ ไม่ใส่ตาราง
            or_(SessionModel.prelaunched_at.is_(None), SessionModel.claimed_at.isnot(None)),
        )
        .all()
    )
    routers, services = {}, {}
    for s in rows:
        for port, url in (s.upstreams or {}).items():
            if not _upstream_ok(url):
                logger.warning(f"[gateway] skip session {s.id} port {port}: upstream {url} not allowed")
                continue
            name = f"s-{s.gateway_token}-{port}"
            routers[name] = {"rule": f"Host(`{public_host(s.gateway_token, port)}`)",
                             "service": name, "entryPoints": ["web"]}
            services[name] = {"loadBalancer": {"servers": [{"url": url}]}}
    return {"http": {"routers": routers, "services": services}}
```

### 1A.5 `web-portal/backend/app/routes/lab_gateway_route.py` (ใหม่)

```python
import hmac
from fastapi import APIRouter, Depends, Header, HTTPException
from app.configs.db import get_db
from app.configs.settings import settings
from app.services.lab_gateway_service import build_routes

# ไม่ใส่ใน OpenAPI ไม่ต้อง login (Traefik ไม่มี JWT) ใช้ token อย่างเดียว
router = APIRouter(prefix="/internal/v1/gateway", include_in_schema=False)


@router.get("/routes")
def gateway_routes(x_gateway_token: str | None = Header(None, alias="X-Gateway-Token"), db=Depends(get_db)):
    expected = settings.LAB_GATEWAY_TOKEN
    if (not settings.LAB_GATEWAY_ENABLED or not expected or not x_gateway_token
            or not hmac.compare_digest(x_gateway_token.encode(), expected.encode())):
        raise HTTPException(status_code=404)
    # คืน dynamic config ของ Traefik ตรง ๆ ไม่ห่อ ApiResponse
    return build_routes(db)
```
ลงทะเบียนใน `web-portal/backend/app/routes/__init__.py`
```python
from app.routes.lab_gateway_route import router as lab_gateway_router
api_router.include_router(lab_gateway_router, tags=["Lab Gateway"])
```
ได้ path จริง `/api/internal/v1/gateway/routes` (`API_PREFIX=/api`)

### 1A.6 `web-portal/backend/app/services/session_service.py`

| ฟังก์ชัน | แก้อะไร |
|---|---|
| `_new_sky_session` (~บรรทัด 450) | ก่อนเรียก `create_fastapi_task`: `token = new_token() if settings.LAB_GATEWAY_ENABLED and run_target == RunTarget.AWS else None` ส่ง `gateway_token=token` เข้า `create_fastapi_task` และใส่ `gateway_token=token` ใน `SessionModel(...)` |
| `create_fastapi_task` (~บรรทัด 160) | รับ `gateway_token: Optional[str] = None` ส่งต่อให้ `_build_aws_task` เท่านั้น (K8s ไม่ใช้) |
| `_build_aws_task` (~บรรทัด 231) | หลัง `ports = ...`: `envs = self._lab_envs(lab_image, env)` แล้ว `if gateway_token: envs.update(gateway_envs(gateway_token, ports))` ใช้ `envs` นี้ในลูป `-e` แทนการเรียก `_lab_envs` ตรง ๆ |
| `_run_sky_launch` (~บรรทัด 519) | หลังได้ `formatted_endpoints`: ถ้า `new_session.gateway_token` → `new_session.upstreams = formatted_endpoints` และ `new_session.endpoints = public_endpoints(token, formatted_endpoints.keys())` ไม่มี token → แบบเดิม |

`_claim_prelaunched` ไม่ต้องแก้: คืน `session.endpoints` ที่ `_run_sky_launch` ตั้งไว้แล้ว และ `prelaunch_service._launch_job` เรียก `_run_sky_launch` ตัวเดียวกัน
`_lab_envs` **ไม่แตะ** (K8s / warm pod / direct pod ใช้ร่วม)
`session_reconciler.py` ไม่ต้องแก้: ไม่ได้อ่าน / เขียน `endpoints` แค่เปลี่ยน status ซึ่งพอให้ route หลุดจากตาราง

**หน้า admin** `web-portal/backend/app/main.py` บรรทัด ~135 (D9)
```python
class SessionAdmin(ModelView, model=Session):
    # gateway_token = กุญแจเข้า lab ของนักศึกษา / upstreams = IP ภายใน ไม่แสดงในหน้า admin
    column_list = get_model_columns(Session, exclude=["endpoints", "gateway_token", "upstreams"])
```
ถ้า `SessionAdmin` มี `column_details_list` / form ที่ไม่ได้ตั้ง ให้ exclude 2 field นี้ด้วย (`column_details_exclude_list`, `form_excluded_columns`)

### 1A.7 tests `web-portal/backend/tests/session/test_lab_gateway.py` (ใหม่)

| เคส | คาดหวัง |
|---|---|
| ไม่มี header / token ผิด / flag ปิด | 404 |
| session RUNNING + is_cloud + มี token | อยู่ในตาราง ครบทุกพอร์ต |
| session PENDING / STOPPED / FAILED / deleted | ไม่อยู่ |
| prelaunched_at มีค่า + claimed_at ว่าง | ไม่อยู่ / claim แล้วอยู่ |
| upstream `http://8.8.8.8:8080` หรือพอร์ต 22 | ถูกตัด + log warning |
| `_build_aws_task` มี token | `docker run` มี `-e __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=.bell-lab.space` และ `-e VLAB_PUBLIC_URL_8443=...` |
| `_build_k8s_task` | ไม่มี env ของ gateway |
| `_run_sky_launch` มี token | `endpoints` เป็น `https://l-...` / `upstreams` เป็น `http://10.10.2.x:...` |
| flag ปิด | `gateway_token` ว่าง endpoints แบบเดิม |
| `GET /sessions/{id}` และ `GET /sessions` | response ไม่มี `upstreams` / `gateway_token` |
| prelaunch (`prelaunch_service`) เปิดเครื่องตอน flag เปิด | record มี token ตั้งแต่ PENDING, ไม่อยู่ในตารางจนกว่า claim |
| port `80` ใน image | ไม่อยู่ใน `endpoints` + log warning (D13) |

```bash
cd web-portal/backend && pytest tests/session -q
```
**ผ่านเมื่อ:** test ใหม่ผ่าน และ test เดิมใน `tests/session` ไม่พัง

### 1A.8 Ansible `web-service` (ตัวแปรใหม่ ยังปิด)

`ansible/roles/web-service/defaults/main.yml`
```yaml
# lab gateway (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md) — เปิดหลัง role lab-gateway ลง router แล้ว
webservice_lab_gateway_enabled: false
webservice_lab_gateway_domain: bell-lab.space
webservice_lab_gateway_token: "{{ vault_lab_gateway_token | default('') }}"
```
`ansible/roles/web-service/templates/backend.env.j2` (ต่อท้าย)
```jinja
# lab gateway: endpoint ของ lab AWS เป็น https://l-<token>-<port>.<domain> (Traefik บน router ดึงตารางจาก backend)
LAB_GATEWAY_ENABLED={{ webservice_lab_gateway_enabled | string | lower }}
LAB_GATEWAY_DOMAIN={{ webservice_lab_gateway_domain }}
LAB_GATEWAY_TOKEN={{ webservice_lab_gateway_token }}
```
`ansible/group_vars/all.yml` (ไฟล์จริง gitignore) + อัปเดต `all.yml.example`
```yaml
# python3 -c 'import secrets;print(secrets.token_urlsafe(48))' — ค่าเดียวกันใช้ทั้ง backend และ traefik บน router
vault_lab_gateway_token: <สุ่ม>
```
**ผ่านเมื่อ:** deploy web-service ด้วย flag ปิดแล้ว `curl http://<BACKEND_TS_IP>:8000/api/internal/v1/gateway/routes` ได้ 404 และกด Start AWS ได้ endpoint `http://10.10.2.x` แบบเดิม

---

## Phase 1B: Terraform (router + SG)

> ทำตอน **ไม่มีคาบ / lab AWS รันอยู่** router จะ stop/start ไม่กี่นาที ช่วงนั้น SkyPilot launch และเข้า `10.10.2.x` ไม่ได้

### 1B.1 `terraform/router.tf`

```hcl
resource "aws_instance" "ts_router" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.small"   # เดิม t3.micro: RAM 1GB → 2GB ให้พอ traefik + cloudflared (AWS_LAB_GATEWAY_ROUTER.md)
  # ...ของเดิม...

  # T3 เป็น unlimited อยู่แล้ว เขียนไว้ให้เห็นว่าตั้งใจ (CPU credit หมดตอนคาบใหญ่ = proxy ช้าทั้งห้อง)
  credit_specification {
    cpu_credits = "unlimited"
  }
  # ...lifecycle / tags ของเดิม...
}
```

### 1B.2 `terraform/security_groups.tf`

แก้ rule เดิม `ts_router_lab_web` (8080 → ช่วง)
```hcl
resource "aws_vpc_security_group_egress_rule" "ts_router_lab_web" {
  security_group_id            = aws_security_group.ts_router.id
  description                  = "Lab web ports through router (Tailscale users + lab gateway)"
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 9999
  referenced_security_group_id = aws_security_group.lab_instances.id
}
```
เพิ่ม 2 rule ใหม่
```hcl
# cloudflared แบบ --protocol http2 (udp 7844 ครอบด้วย ts_router_udp_all, tcp 443 ครอบด้วย ts_router_https แล้ว)
resource "aws_vpc_security_group_egress_rule" "ts_router_cloudflared" {
  security_group_id = aws_security_group.ts_router.id
  description       = "cloudflared tunnel (http2)"
  ip_protocol       = "tcp"
  from_port         = 7844
  to_port           = 7844
  cidr_ipv4         = "0.0.0.0/0"
}

# ไม่พึ่ง rule 0.0.0.0/0 ที่ SkyPilot เปิดตาม ports: ของ task อย่างเดียว
resource "aws_vpc_security_group_ingress_rule" "lab_web_from_router" {
  security_group_id            = aws_security_group.lab_instances.id
  description                  = "Lab web ports from router (lab gateway)"
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 9999
  referenced_security_group_id = aws_security_group.ts_router.id
}
```

### 1B.3 plan / apply

```bash
cd terraform
terraform plan -out gateway.tfplan
```
**อ่าน plan ก่อน apply** ต้องเห็นแค่นี้:
- `aws_instance.ts_router` **update in-place** (`instance_type`, `credit_specification`) — ถ้าขึ้น `must be replaced` **หยุด** (router ใหม่ = Tailscale หาย)
- `aws_vpc_security_group_egress_rule.ts_router_lab_web` replace (เปลี่ยนพอร์ต = สร้างใหม่ ปกติ)
- `ts_router_cloudflared`, `lab_web_from_router` create

```bash
terraform apply gateway.tfplan
```

### 1B.4 ลบ rule ที่เพิ่มด้วยมือ (5173 / 8443)

```bash
aws ec2 describe-security-group-rules --profile <ของ Pete> \
  --filters Name=group-id,Values=<SG_TS_ROUTER_ID> \
  --query 'SecurityGroupRules[?IsEgress && (FromPort==`5173` || FromPort==`8443`)].[SecurityGroupRuleId,FromPort]'
aws ec2 revoke-security-group-egress --profile <ของ Pete> \
  --group-id <SG_TS_ROUTER_ID> --security-group-rule-ids <id1> <id2>
```

**ผ่านเมื่อ:** เทส R1–R3 (ข้อ 1F.3) ผ่าน และ `terraform plan` รอบสองขึ้น `No changes`

**ถอย:** revert commit → `terraform apply` (กลับเป็น t3.micro / พอร์ต 8080) แล้วเพิ่ม rule 5173 / 8443 คืนด้วย CLI

---

## Phase 1C: Tailscale tag + ACL

### 1C.1 `tailscale/vlab-tags.tsv` (ไฟล์ของตัวเอง gitignore)

```
<ROUTER_TS_IP>      tag:vlab-router     # vlab-ts-router (AWS subnet router + lab gateway)
```

### 1C.2 `tailscale/vlab-acl.hujson` (ไฟล์ของตัวเอง) และ `tailscale/vlab-acl.hujson.example` (ใน git)

```hujson
"tagOwners": {
    // ...ของเดิม
    "tag:vlab-router": ["autogroup:admin"],
},

"acls": [
    // ...ของเดิม
    // router รับ traffic จากอินเทอร์เน็ต (cloudflared) → เริ่มคุยใน tailnet ได้แค่ backend :8000 (traefik ดึงตาราง route)
    // traffic ของ subnet route (ทีม / master → 10.10.x) router ไม่ได้เป็นคนเริ่ม ไม่ต้องมีกฎ src router
    {"action": "accept", "src": ["tag:vlab-router"], "proto": "tcp", "dst": ["<BACKEND_TS_IP>:8000"]},
],

// route ไม่หลุดหลังติด tag (เครื่องไม่ใช่ของ user แล้ว)
"autoApprovers": {
    "routes": {
        "10.10.2.0/24": ["tag:vlab-router"],
        "10.10.3.0/24": ["tag:vlab-router"],
    },
},

"tests": [
    // ...ของเดิม
    {
        "src": "tag:vlab-router",
        "proto": "tcp",
        "accept": ["<BACKEND_TS_IP>:8000"],
        "deny": ["tag:vlab-server:22", "tag:vlab-server:6443", "tag:vlab-server:30880",
                 "tag:vlab-worker:22", "tag:vlab-worker:8080", "tag:vlab-registry:5002"],
    },
],
```
> ถ้า backend รันบนเครื่องที่ไม่ติด tag (WSL ของคนในทีม) IP เปลี่ยนได้ ให้ติด tag ให้เครื่องนั้นก่อน แล้วเขียน dst เป็น tag แทน IP

### 1C.3 apply

```bash
./script/tailscale-acl.sh plan     # ดู diff + tag ที่จะติด
./script/tailscale-acl.sh apply    # ยืนยัน → ตั้ง policy → ติด tag
./script/tailscale-acl.sh check
```

**ผ่านเมื่อ:**
- admin console: `vlab-ts-router` มี tag `tag:vlab-router`, route `10.10.2.0/24` `10.10.3.0/24` ยัง approved
- บน router: `tailscale debug prefs` เหมือนข้อ 0.3 (advertise-routes ไม่หาย)
- เทส R1–R3 ผ่านอีกรอบ
- บน router: `nc -zv -w3 <BACKEND_TS_IP> 8000` ต่อได้ / `nc -zv -w3 <master ts ip> 22` ต่อไม่ได้

**ถอย:** `./script/tailscale-acl.sh rollback tailscale/backup/<ไฟล์ล่าสุด>` แล้วลบ tag ใน console

---

## Phase 1D: Cloudflare (dashboard ของ Panupong เจ้าของ zone)

1. Zero Trust → Networks → Tunnels → **Create tunnel** (Cloudflared) ชื่อ `vlab-lab-gateway`
2. หน้าติดตั้ง: copy **token** (ข้อความหลัง `--token`) → `ansible/group_vars/all.yml`
   ```yaml
   vault_lab_gateway_tunnel_token: <token>
   ```
   ไม่ต้องรันคำสั่งติดตั้งที่ dashboard ให้มา (role 1E ลงเอง)
3. Public hostname: Subdomain `*` / Domain `bell-lab.space` / Service `HTTP` → `127.0.0.1:8081`
   ถ้า dashboard ไม่ยอมเพราะมี DNS `*` อยู่แล้ว (D16) ให้ทำข้อ 4 ก่อนแล้วกลับมาทำข้อนี้
4. DNS → Records (D16): **มี `*` อยู่แล้ว** — จด Type / Content / Proxy status เดิมลงข้อ 9 ก่อน แล้ว **Edit** record นั้นเป็น
   Type `CNAME` / Name `*` / Target `<tunnel-id>.cfargotunnel.com` / **Proxied**
   (ถ้า Type เดิมเป็น A / AAAA เปลี่ยน type ไม่ได้ ให้ลบ record `*` ทั้ง A และ AAAA แล้วสร้าง CNAME ใหม่)
   ก่อนแก้ เช็กว่า hostname ที่ใช้จริงทุกตัว (`skypilot` ฯลฯ) มี record ของตัวเอง ไม่ได้พึ่ง `*` — 2026-11-09 `skypilot` มีของตัวเองแล้ว
5. SSL/TLS → Edge Certificates: Universal SSL **Active** และครอบ `*.bell-lab.space`
   — เช็กแล้ว 2026-11-09: cert ที่ edge ส่งให้ `l-test-8080.bell-lab.space` มี SAN `bell-lab.space, *.bell-lab.space` (Google Trust Services WE1 หมดอายุ 2027-02-06 Cloudflare ต่อเอง) ไม่ต้องทำอะไรเพิ่ม
6. เช็ก record ที่มีชื่อชัดเจน (`skypilot.bell-lab.space` ฯลฯ) ยังเปิดได้
7. **Rules → Cache Rules** (D11): ชื่อ `lab gateway no cache` เงื่อนไข `starts_with(http.host, "l-") and ends_with(http.host, ".bell-lab.space")` → **Bypass cache**
   (Vite dev / code-server เสิร์ฟไฟล์ที่เปลี่ยนตลอด ถ้า Cloudflare cache ไว้ HMR / extension จะได้ไฟล์เก่า)
8. **Rules → Configuration Rules** เงื่อนไขเดียวกัน → ปิด Rocket Loader, Email Obfuscation, Automatic HTTPS Rewrites (กันแก้ HTML ของ lab)
9. **Security → Bots**: ถ้าเปิด Bot Fight Mode ไว้ทั้ง zone ต้องเทส G2 / G4 ว่าไม่โดน challenge (Bot Fight Mode ยกเว้นราย hostname ไม่ได้บน Free plan ถ้าโดน ต้องปิดทั้ง zone)
10. **Network**: WebSockets = On (ค่าเริ่มต้น)

**ผ่านเมื่อ:** tunnel ขึ้นสถานะ `Inactive` (ยังไม่มี connector — ปกติ) และ `curl -s https://l-test-8080.bell-lab.space/` เปลี่ยนจาก `error code: 521` เป็น `error code: 1033` (= ถึง tunnel ใหม่แล้ว แค่ยังไม่มี cloudflared ต่อ)

**ถอย:** ลบ public hostname `*` แล้วคืน record `*` ตามค่าที่จดไว้ในข้อ 9

---

## Phase 1E: Ansible role `lab-gateway` บน router

### 1E.1 ให้ Ansible เข้า router ได้ (ครั้งเดียว ผ่าน SSM)

```bash
aws ssm start-session --target <ROUTER_INSTANCE_ID> --profile <ของ Pete>
# บน router:
sudo -u ubuntu bash -c 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo "<public key ของคนรัน ansible>" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```
เข้าผ่าน tailnet (`ssh ubuntu@<ROUTER_TS_IP>`) — SG ไม่ได้เปิด 22 จากข้างนอก และไม่ต้องเปิด

### 1E.2 `ansible/inventory.home.yml` ของ Pete (+ `inventory.yml.example`)

```yaml
    aws_router:
      hosts:
        vlab-ts-router:
          ansible_host: "<ROUTER_TS_IP>"
          ansible_user: ubuntu
```

### 1E.3 `ansible/site.yml` (ต่อท้าย)

```yaml
# ไม่รัน common / tailscale กับ router: Tailscale ของ router ตั้งด้วยมือ ห้าม role ไปแตะ flag
- name: Provision lab gateway on the AWS Tailscale router
  hosts: aws_router
  become: yes
  roles:
    - { role: lab-gateway, tags: ['lab-gateway'] }
```

### 1E.4 โครง role ใหม่

```
ansible/roles/lab-gateway/
├── defaults/main.yml
├── handlers/main.yml
├── tasks/main.yml
└── templates/
    ├── traefik.yml.j2
    ├── traefik.service.j2
    └── cloudflared-lab.service.j2
```

**`defaults/main.yml`**
```yaml
lab_gateway_domain: bell-lab.space
lab_gateway_listen: 127.0.0.1:8081
# IP ของเครื่อง backend ใน tailnet (= webservice_bind_ip)
lab_gateway_backend_ip: "{{ hostvars[groups['webservice'][0]]['ansible_host'] }}"
lab_gateway_backend_url: "http://{{ lab_gateway_backend_ip }}:8000/api/internal/v1/gateway/routes"
lab_gateway_token: "{{ vault_lab_gateway_token }}"
lab_gateway_tunnel_token: "{{ vault_lab_gateway_tunnel_token }}"

# ปักเลขจริงตอนทำ (ดู release ล่าสุดที่มีอายุ ≥ 2 สัปดาห์)
lab_gateway_traefik_version: "3.x.y"
lab_gateway_cloudflared_version: "2026.x.y"
# sha256 ของ cloudflared-linux-amd64.deb จากหน้า release (traefik ใช้ไฟล์ checksums ของ release เอง)
lab_gateway_cloudflared_sha256: ""

lab_gateway_traefik_memory_max: 384M
lab_gateway_cloudflared_memory_max: 256M
```
> router เป็น `t3` = **x86_64** ใช้ไฟล์ `amd64` (doc หลักที่ใช้ t4g เป็น arm64)

**`tasks/main.yml`**
```yaml
# ---------- เก็บสถานะก่อนลง (เทียบตอนท้าย) ----------
- name: Snapshot FORWARD chain before install
  ansible.builtin.command: iptables -S FORWARD
  register: forward_before
  changed_when: false

# ---------- users ----------
- name: System users for traefik and cloudflared
  ansible.builtin.user:
    name: "{{ item }}"
    system: yes
    shell: /usr/sbin/nologin
    create_home: no
  loop: [traefik, cloudflared]

# ---------- traefik (binary, ไม่ลง Docker) ----------
- name: Download traefik release
  ansible.builtin.get_url:
    url: "https://github.com/traefik/traefik/releases/download/v{{ lab_gateway_traefik_version }}/traefik_v{{ lab_gateway_traefik_version }}_linux_amd64.tar.gz"
    dest: "/tmp/traefik_v{{ lab_gateway_traefik_version }}.tar.gz"
    checksum: "sha256:https://github.com/traefik/traefik/releases/download/v{{ lab_gateway_traefik_version }}/traefik_v{{ lab_gateway_traefik_version }}_checksums.txt"
    mode: "0644"

- name: Install traefik binary
  ansible.builtin.unarchive:
    src: "/tmp/traefik_v{{ lab_gateway_traefik_version }}.tar.gz"
    dest: /usr/local/bin
    remote_src: yes
    include: [traefik]
    owner: root
    group: root
    mode: "0755"
  notify: restart traefik

- name: traefik config dir
  ansible.builtin.file:
    path: /etc/traefik
    state: directory
    owner: root
    group: traefik
    mode: "0750"

- name: traefik config (มี gateway token)
  ansible.builtin.template:
    src: traefik.yml.j2
    dest: /etc/traefik/traefik.yml
    owner: root
    group: traefik
    mode: "0640"
  notify: restart traefik

# ---------- cloudflared ----------
- name: Download cloudflared .deb
  ansible.builtin.get_url:
    url: "https://github.com/cloudflare/cloudflared/releases/download/{{ lab_gateway_cloudflared_version }}/cloudflared-linux-amd64.deb"
    dest: "/tmp/cloudflared-{{ lab_gateway_cloudflared_version }}.deb"
    checksum: "sha256:{{ lab_gateway_cloudflared_sha256 }}"
    mode: "0644"

- name: Install cloudflared
  ansible.builtin.apt:
    deb: "/tmp/cloudflared-{{ lab_gateway_cloudflared_version }}.deb"
  notify: restart cloudflared-lab

- name: cloudflared env dir
  ansible.builtin.file:
    path: /etc/cloudflared
    state: directory
    owner: root
    group: root
    mode: "0755"

- name: cloudflared tunnel token
  ansible.builtin.copy:
    dest: /etc/cloudflared/lab-gateway.env
    content: "TUNNEL_TOKEN={{ lab_gateway_tunnel_token }}\n"
    owner: root
    group: root
    mode: "0600"
  no_log: true
  notify: restart cloudflared-lab

# ---------- systemd ----------
- name: systemd units
  ansible.builtin.template:
    src: "{{ item }}.service.j2"
    dest: "/etc/systemd/system/{{ item }}.service"
    mode: "0644"
  loop: [traefik, cloudflared-lab]
  # ไม่ใช้ "restart {{ item }}": ชื่อ handler ที่มาจากตัวแปร loop ไม่ถูก resolve ทุกรุ่นของ Ansible
  notify: [reload systemd, restart traefik, restart cloudflared-lab]

- name: Flush handlers before verify
  ansible.builtin.meta: flush_handlers

- name: Enable and start
  ansible.builtin.systemd:
    name: "{{ item }}"
    enabled: yes
    state: started
  loop: [traefik, cloudflared-lab]

# ---------- verify ----------
- name: traefik answers 404 for unknown host
  ansible.builtin.uri:
    url: "http://{{ lab_gateway_listen }}/"
    headers:
      Host: "l-nope-8080.{{ lab_gateway_domain }}"
    status_code: 404
  register: probe
  until: probe.status == 404
  retries: 10
  delay: 3

- name: traefik can read routes from backend (no provider error in log)
  ansible.builtin.shell: journalctl -u traefik --since "-2min" --no-pager | grep -iE 'provider.*(error|unable)' || true
  register: provider_errors
  changed_when: false
  failed_when: provider_errors.stdout | length > 0

- name: Router must still route (tailscale up + ip_forward)
  ansible.builtin.command: "{{ item }}"
  loop:
    - tailscale status --peers=false
    - sysctl -n net.ipv4.ip_forward
  register: router_checks
  changed_when: false
  failed_when: router_checks.rc != 0 or (item == 'sysctl -n net.ipv4.ip_forward' and router_checks.stdout != '1')

- name: FORWARD chain unchanged
  ansible.builtin.command: iptables -S FORWARD
  register: forward_after
  changed_when: false
  failed_when: forward_after.stdout != forward_before.stdout
```

**`handlers/main.yml`**
```yaml
- name: reload systemd
  ansible.builtin.systemd:
    daemon_reload: yes

- name: restart traefik
  ansible.builtin.systemd:
    name: traefik
    state: restarted

- name: restart cloudflared-lab
  ansible.builtin.systemd:
    name: cloudflared-lab
    state: restarted
```

**`templates/traefik.yml.j2`**
```yaml
# {{ ansible_managed }}
global:
  checkNewVersion: false              # ไม่ต่อออกเน็ตเอง (D12) อัปเดตผ่านตัวแปร version ของ role
  sendAnonymousUsage: false

entryPoints:
  web:
    address: "{{ lab_gateway_listen }}"
    forwardedHeaders:
      trustedIPs: ["127.0.0.1/32"]      # เชื่อ X-Forwarded-* จาก cloudflared บนเครื่องเดียวกันเท่านั้น
    transport:
      respondingTimeouts:
        readTimeout: 600s               # v3 ค่าเริ่ม 60s — upload / websocket นาน ๆ ถูกตัด
        idleTimeout: 600s

providers:
  http:
    endpoint: "{{ lab_gateway_backend_url }}"
    pollInterval: 5s
    pollTimeout: 5s
    headers:
      X-Gateway-Token: "{{ lab_gateway_token }}"

api:
  dashboard: false
ping: {}
log:
  level: INFO
accessLog:
  fields:
    headers:
      defaultMode: drop                 # ไม่เก็บ cookie / header ของนักศึกษา
```

**`templates/traefik.service.j2`**
```ini
# {{ ansible_managed }}
[Unit]
Description=Traefik (vlab lab gateway)
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
User=traefik
Group=traefik
ExecStart=/usr/local/bin/traefik --configFile=/etc/traefik/traefik.yml
Restart=on-failure
RestartSec=3
MemoryMax={{ lab_gateway_traefik_memory_max }}
CPUQuota=70%
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**`templates/cloudflared-lab.service.j2`**
```ini
# {{ ansible_managed }}
[Unit]
Description=cloudflared tunnel vlab-lab-gateway
After=network-online.target traefik.service
Wants=network-online.target

[Service]
User=cloudflared
Group=cloudflared
EnvironmentFile=/etc/cloudflared/lab-gateway.env
# --protocol http2 ตาม role skypilot-node (cloudflared รุ่นใหม่ไม่ถอยจาก QUIC เอง)
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --protocol http2 run
Restart=on-failure
RestartSec=3
StateDirectory=cloudflared
Environment=HOME=/var/lib/cloudflared
MemoryMax={{ lab_gateway_cloudflared_memory_max }}
CPUQuota=50%
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```
> `EnvironmentFile` อ่านโดย systemd (root) ก่อนสลับ user จึงตั้ง mode 0600 root ได้

### 1E.5 รัน

```bash
cd ansible
ansible-playbook -i inventory.home.yml site.yml --limit aws_router --tags lab-gateway --check --diff   # ดูก่อน
ansible-playbook -i inventory.home.yml site.yml --limit aws_router --tags lab-gateway
```

**ผ่านเมื่อ:**
- playbook จบโดยไม่มี task verify fail
- Cloudflare dashboard: tunnel `vlab-lab-gateway` เป็น **Healthy**
- `free -m` บน router ยังเหลือ RAM ≥ 800MB
- เทส R1–R4 (ข้อ 1F.3) ผ่าน

**ถอย:** `sudo systemctl disable --now traefik cloudflared-lab` บน router (ไม่กระทบ subnet router)

---

## Phase 1F: เปิด gateway + เทสเฟส 1

### 1F.0 เช็ก Vite ใน image music-lab ก่อน (D10)

```bash
# บนเครื่องที่มี image music-lab (registry / master)
docker run --rm --entrypoint sh <registry>/skypilot/music-lab:lab-01 -c \
  'grep -m1 "\"version\"" /app/client/node_modules/vite/package.json;
   grep -l __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS /app/client/node_modules/vite/dist/node/chunks/*.js'
```
- เจอไฟล์ = env ที่ backend ส่งใช้ได้ ไปต่อ
- ไม่เจอ = แก้ `music-lab/client/vite.config.js` ใน `server:` เพิ่ม
  ```js
  // lab บน AWS เปิดผ่าน https://l-<token>-5173.bell-lab.space (lab gateway)
  allowedHosts: [".bell-lab.space"],
  ```
  แล้ว build + push image ใหม่ (`ansible/build-images.yml`) ก่อนเทส G4

### 1F.1 เปิด flag

```bash
cd ansible
ansible-playbook -i inventory.home.yml site.yml --limit webservice --tags web-service \
  -e webservice_lab_gateway_enabled=true
```
พอเทสผ่านค่อยเปลี่ยนค่าใน `ansible/group_vars/all.yml` เป็น `webservice_lab_gateway_enabled: true` ถาวร

### 1F.2 เช็กตาราง route

```bash
# จากเครื่องใน tailnet
curl -s -H "X-Gateway-Token: <vault_lab_gateway_token>" http://<BACKEND_TS_IP>:8000/api/internal/v1/gateway/routes
```
ยังไม่มี lab AWS เปิด = `{}` (ไม่ใช่ `{"http":{"routers":{},...}}` — Traefik 3.7 decode ไม่ได้ ดู progress E6)

### 1F.3 เทส router ยังทำงานเดิม (ทำหลัง 1B / 1C / 1E / 1F ทุกครั้ง)

| # | เคส | ต้องเห็น |
|---|---|---|
| R1 | `tailscale status` บน router และ master | router online, master เห็น route `10.10.2.0/24` `10.10.3.0/24` |
| R2 | กด Start lab AWS | launch ผ่านในเวลาใกล้ baseline ข้อ 0.5 |
| R3 | เครื่องใน tailnet เปิด `http://10.10.2.x:8443` (ตอน flag ปิด) | เปิดได้ |
| R4 | `systemctl stop traefik cloudflared-lab` แล้วทำ R2 | ยัง launch ได้ (proxy ล่มไม่กระทบ SkyPilot) แล้ว start คืน |

### 1F.4 เทส gateway (login บนเครื่องใน tailnet / เปิดลิงก์บนมือถือ 4G ที่ไม่มี Tailscale)

ใช้ตาราง G1–G12 ใน [AWS_LAB_GATEWAY_ROUTER.md](AWS_LAB_GATEWAY_ROUTER.md) ข้อ 7.2 ครบทุกข้อ จดผลลงข้อ 9 ของ doc นี้

**ผ่านเมื่อ:** G1–G11 ผ่าน (G12 ไม่ผ่านจดเป็นข้อจำกัดได้)

**ถอย:** `-e webservice_lab_gateway_enabled=false` → session ใหม่กลับเป็น private IP ทันที (session ที่เปิดอยู่ใช้ลิงก์เดิมจนปิด)

---

## Phase 2A: backend อ่าน IP จริงหลัง nginx + cookie ตาม proto

### 2A.1 `web-portal/backend/app/configs/settings.py`

```python
    # peer ที่เชื่อ header X-Real-IP / X-Forwarded-Proto / X-Vlab-Entry ได้ (nginx ของ frontend)
    # ว่าง = ไม่เชื่อ header ใดเลย (พฤติกรรมเดิม) — คนละตัวกับ TAILSCALE_TRUSTED_PROXY_CIDRS_STR ของหน้า admin
    TRUSTED_PROXY_CIDRS_STR: str = ""
```
พร้อม property แปลงเป็น `ip_network` แบบเดียวกับ `tailscale_trusted_proxy_cidrs`

### 2A.2 `web-portal/backend/app/utils/client_ip.py` (ใหม่)

```python
import ipaddress
from typing import Optional
from fastapi import Request
from app.configs.settings import settings


def _trusted_peer(request: Request) -> bool:
    if not request.client:
        return False
    try:
        peer = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return any(peer in net for net in settings.trusted_proxy_cidrs)


def client_ip(request: Request) -> Optional[str]:
    """IP ของเครื่องที่กด — เชื่อ X-Real-IP เฉพาะจาก nginx ของเราเอง (peer ใน TRUSTED_PROXY_CIDRS_STR)"""
    peer = request.client.host if request.client else None
    if not _trusted_peer(request):
        return peer
    if request.headers.get("X-Vlab-Entry") == "public":
        return None          # เข้าทาง Cloudflare = ข้างนอกเสมอ ไม่ต้องเทียบ worker
    return (request.headers.get("X-Real-IP") or "").strip() or peer


def is_https(request: Request) -> bool:
    if _trusted_peer(request):
        return request.headers.get("X-Forwarded-Proto") == "https"
    return request.url.scheme == "https"
```

### 2A.3 ใช้ helper

| ไฟล์ | จุด |
|---|---|
| `app/routes/session_route.py` บรรทัด ~114 (`create_session`) | `client_ip = client_ip(http_request)` |
| `app/routes/session_route.py` บรรทัด ~160 (`whoami`) | เหมือนกัน |
| `app/services/auth_service.py` บรรทัด ~294–335 (set/delete cookie) | `secure=is_https(request)` แทน `settings.AUTH_COOKIE_SECURE` (ส่ง `request` เข้าฟังก์ชันจาก route) |

> uvicorn เชื่อ `X-Forwarded-For` จาก `127.0.0.1` เป็นค่าเริ่มต้น nginx ต้อง proxy ไปที่ `BIND_IP:8000` (ไม่ใช่ 127.0.0.1) และไม่ส่ง `X-Forwarded-For` เพื่อไม่ให้ uvicorn เขียน `request.client` ทับเอง

### 2A.4 tests

| เคส | คาดหวัง |
|---|---|
| peer ไม่ trusted + ส่ง `X-Real-IP: <worker ip>` | ได้ peer (ปลอมไม่ได้) |
| peer trusted + `X-Real-IP: <worker ip>` | ได้ worker ip → นับเป็นเครื่องแลป |
| peer trusted + `X-Vlab-Entry: public` | ข้างนอก |
| `TRUSTED_PROXY_CIDRS_STR` ว่าง | พฤติกรรมเดิมทุกเคส |
| login ผ่าน `X-Forwarded-Proto: https` จาก trusted | cookie มี `Secure` / http = ไม่มี |

**ผ่านเมื่อ:** test ผ่าน และ deploy โดยไม่ตั้ง `TRUSTED_PROXY_CIDRS_STR` แล้ว whoami จาก worker ยังผ่าน (ansible task เดิม)

---

## Phase 2B: กด Start แบบ async

### 2B.1 ย้าย executor ออกมาใช้ร่วม

`web-portal/backend/app/services/prelaunch_service.py` มี `ThreadPoolExecutor` + `_launch_job` อยู่แล้ว ย้ายไป `app/services/launch_runner.py` (ใหม่) ให้ทั้ง prelaunch และ Start ใช้ตัวเดียวกัน
- `submit(fn)` และ `launch_job(session_id, task, lab_image_id, lifetime_minutes=None)` เปิด `SessionLocal()` ของ thread เอง
- หลัง `_run_sky_launch` สำเร็จ: ถ้า `session.claimed_at` มีค่า (มีคนรับระหว่าง PENDING ดู 2B.3) → ตั้ง autostop ตาม `lifespan_minutes` + `expires_at` แบบที่ `_claim_prelaunched` ทำ

### 2B.2 `settings.py`

```python
    # Start lab AWS ตอบทันที (PENDING) แล้ว launch ใน background — จำเป็นเมื่อเข้าผ่าน Cloudflare (ตัดที่ 100 วิ)
    SESSION_ASYNC_LAUNCH: bool = False
```

### 2B.3 `session_service.py`

| จุด | แก้ |
|---|---|
| `create_session` ท้ายสุด (~บรรทัด 445) | ถ้า `SESSION_ASYNC_LAUNCH`: หลัง `_new_sky_session` → `launch_runner.submit(launch_job(new_session.id, task, lab_image.id))` แล้ว `return self._sky_result(...)` ทันที ไม่งั้นแบบเดิม |
| `_sky_result` (~บรรทัด 534) | `"status": session.status.value` แทน `"running"` ตายตัว |
| `_claim_prelaunched` (~บรรทัด 566) | ถ้า `SESSION_ASYNC_LAUNCH` และยัง PENDING: ตั้ง `claimed_at` แล้ว return pending ทันที (ไม่ loop รอ) ตัว launch_job ตั้ง autostop ให้ตอน RUNNING (2B.1) |
| warm pod / direct pod | ไม่แก้ (เกิดจากเครื่องแลปเท่านั้น ไม่ผ่าน Cloudflare) |

`CreateSessionResponse` ไม่ต้องแก้ schema (`status: str`, `endpoints` ส่ง `{}` ตอน pending ได้)

### 2B.4 tests

- async เปิด: `POST /sessions` ตอบ `status: "pending"` ภายใน < 2 วิ (mock sky), launch_job เปลี่ยนเป็น RUNNING
- launch พัง: session เป็น FAILED, `GET /sessions/{id}` ตอบ failed
- prelaunch PENDING + async: ตอบ pending, `claimed_at` ถูกตั้ง, หลัง RUNNING autostop = lifespan
- async ปิด: test เดิมทั้งหมดผ่าน

**ผ่านเมื่อ:** test ผ่าน deploy ด้วย flag ปิด ไม่มีอะไรเปลี่ยน

---

## Phase 2C: frontend

### 2C.1 `web-portal/frontend/src/services/session.ts`

```ts
  /** สถานะล่าสุด — ใช้ poll ตอน Start ตอบ pending */
  get: async (sessionId: string): Promise<SessionDetail> => {
    const response = await apiClient.get<ApiResponse<SessionDetail>>(`/sessions/${sessionId}`);
    return (response as unknown as ApiResponse<SessionDetail>).data;
  },
```
`SessionDetail` = field ของ `SessionResponse` ฝั่ง backend (snake_case: `id`, `status`, `endpoints`, `expires_at`, ...)

### 2C.2 `web-portal/frontend/src/pages/LabDetail.tsx` (~บรรทัด 78–90)

- `create` ตอบ `status === 'pending'` → แสดง `LabLoader` ต่อ แล้ว poll `sessionService.get(id)` ทุก 3 วิ
- หยุดเมื่อ `running` (set session) / `failed` / `stopped` (แสดง error) / เกิน 6 นาที (แสดง "ยังเปิดไม่เสร็จ ลองรีเฟรช")
- clear interval ตอน unmount
- เข้าหน้า / รีเฟรช (D14): โหลด session ของ lab นี้จาก `GET /sessions?status=pending` และ `?status=running` (กรอง `lab_id` ฝั่ง frontend) มี RUNNING → แสดงลิงก์ทันที มี PENDING → poll ต่อ แทนการให้กด Start ซ้ำแล้วได้ 409
- `SessionDetail` ไม่มี `cluster_name` / `image_repository` (บรรทัด ~219 ใช้อยู่) ให้แสดงจาก response ของ `create` ถ้ามี ไม่มีก็ซ่อน

### 2C.3 `VITE_API_URL` เป็น relative

ไม่ต้องแก้โค้ด (`api.ts` อ่าน `import.meta.env.VITE_API_URL`) เปลี่ยนค่าที่ ansible (2E) เป็น `/api`
dev (`npm run dev`) ใช้ `.env` ของตัวเองเหมือนเดิม

**ผ่านเมื่อ:** `npm run build` ผ่าน, `npm test` ผ่าน, เทสเองด้วย backend ที่เปิด `SESSION_ASYNC_LAUNCH=true` แล้วกด Start เห็น loader จนได้ลิงก์

---

## Phase 2D: compose + nginx + cloudflared ของ portal

### 2D.1 `web-portal/frontend/nginx.conf` → `web-portal/frontend/nginx.conf.template`

nginx image แทน `${BIND_IP}` ด้วย env ตอน start (`/etc/nginx/templates/*.template`) ตัวแปรของ nginx เอง (`$host`) ไม่ถูกแทน
```nginx
# ทางเดิม: เครื่องใน tailnet (เครื่องแลป / ทีม) — $remote_addr = Tailscale IP จริงเพราะ host network
server {
    listen ${BIND_IP}:80;
    include /etc/nginx/conf.d/vlab-common.inc;

    location /api/ {
        proxy_pass http://${BIND_IP}:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;      # ทับของที่ client ส่งมาเสมอ
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header X-Vlab-Entry tailnet;
        proxy_set_header X-Forwarded-For "";
        proxy_read_timeout 600s;                      # ทางเดิมยังรอ launch แบบ sync ได้
        client_max_body_size 100m;
    }
}

# ทาง public: cloudflared บนเครื่องเดียวกันต่อเข้ามา — ข้างนอกเสมอ
server {
    listen 127.0.0.1:8088;
    include /etc/nginx/conf.d/vlab-common.inc;

    location /api/ {
        proxy_pass http://${BIND_IP}:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $http_cf_connecting_ip;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Vlab-Entry public;
        proxy_set_header X-Forwarded-For "";
        proxy_read_timeout 90s;                       # ต่ำกว่า 100 วิ ของ Cloudflare
        client_max_body_size 100m;                    # Cloudflare Free จำกัด 100MB ต่อ request
    }
}
```
ย้าย `root` / `location /` / `location /assets/` / `gzip` เดิมไปไว้ใน `web-portal/frontend/nginx.common.inc` (ไม่ใช่ template)

`web-portal/frontend/Dockerfile` stage 2
```dockerfile
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY nginx.common.inc /etc/nginx/conf.d/vlab-common.inc
```

### 2D.2 `web-portal/docker-compose.prod.yml`

```yaml
  frontend:
    # ...build เดิม...
    # host network เหมือน backend: ผ่าน bridge แล้ว Tailscale MASQUERADE → $remote_addr กลายเป็น 172.18.0.1 ทุกคน
    network_mode: host
    environment:
      BIND_IP: ${BIND_IP}
    # ลบ ports: เดิม (host network ใช้ ports ไม่ได้)

  # ทางเข้า public ของ portal (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md 2D) เปิดด้วย COMPOSE_PROFILES=public
  cloudflared-portal:
    image: cloudflare/cloudflared:<ปัก version เดียวกับ lab gateway>
    profiles: ["public"]
    restart: unless-stopped
    network_mode: host
    command: ["tunnel", "--no-autoupdate", "--protocol", "http2", "run"]
    environment:
      TUNNEL_TOKEN: ${PORTAL_TUNNEL_TOKEN:-}
    depends_on:
      - frontend
```
> `net.ipv4.ip_nonlocal_bind=1` ที่ role ตั้งไว้แล้ว ทำให้ nginx bind `BIND_IP` ได้แม้ Tailscale ยังไม่ขึ้นตอนบูต

**ผ่านเมื่อ (เทสบนเครื่อง web-service ก่อน 2E):**
```bash
# จาก worker (เครื่องแลป)
curl -s http://<BACKEND_TS_IP>/api/v1/whoami
```
ต้องได้ `clientIp` = IP ของ worker และ `labMachine` ไม่ว่าง **ถ้าได้ IP อื่น (172.x / BIND_IP) หยุด** — ทางเข้าห้องแลปจะไป AWS หมด

---

## Phase 2E: Ansible `web-service`

### 2E.1 เช็ก inventory ก่อน (D6)

`ansible/inventory.home.yml` (ของ Pete) มี group `webservice` host `vlab-web` แล้ว (D6) — ถ้าใช้ไฟล์อื่น ต้องมี group ชื่อ `webservice` ตรงกับ `site.yml` (example ใช้ `webportal`)

### 2E.2 `ansible/roles/web-service/defaults/main.yml`

```yaml
# --- ทางเข้า public ของ portal (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md เฟส 2) ---
webservice_public_enabled: false
webservice_public_domain: vlab.bell-lab.space
webservice_portal_tunnel_token: "{{ vault_portal_tunnel_token | default('') }}"
webservice_session_async_launch: "{{ webservice_public_enabled }}"
```

### 2E.3 `templates/compose.env.j2`

```jinja
# relative: build ครั้งเดียวใช้ได้ทั้งทาง Tailscale และทาง public (nginx proxy /api ไป backend)
VITE_API_URL={{ webservice_api_prefix }}
COMPOSE_PROFILES={{ 'public' if webservice_public_enabled else '' }}
PORTAL_TUNNEL_TOKEN={{ webservice_portal_tunnel_token }}
```
(แทนบรรทัด `VITE_API_URL=http://...` เดิม — เปลี่ยนแล้วต้อง `--build` ใหม่ ซึ่ง task deploy ทำอยู่แล้ว)

### 2E.4 `templates/backend.env.j2`

```jinja
# nginx (host network) ต่อ backend จาก BIND_IP — เชื่อ X-Real-IP เฉพาะจากตรงนี้
TRUSTED_PROXY_CIDRS_STR={{ webservice_bind_ip }}/32
SESSION_ASYNC_LAUNCH={{ webservice_session_async_launch | string | lower }}
```
แก้บรรทัด CORS เดิม
```jinja
CORS_ORIGINS_STR=http://{{ webservice_bind_ip }},http://{{ webservice_bind_ip }}:{{ webservice_http_port }}{% if webservice_public_enabled %},https://{{ webservice_public_domain }}{% endif %}
```
SSO (ถ้ามี client id)
```jinja
{% if vault_google_client_id is defined %}
GOOGLE_CLIENT_ID={{ vault_google_client_id }}
GOOGLE_CLIENT_SECRET={{ vault_google_client_secret }}
# ค่าสำรองเท่านั้น: frontend ส่ง redirect_uri = <origin>/auth/callback มาเองทุกครั้ง (AuthContext.tsx) — D8
GOOGLE_REDIRECT_URI=https://{{ webservice_public_domain }}/auth/callback
{% endif %}
```
Google ไม่รับ redirect URI ที่เป็น IP (`http://100.x...`) → SSO ใช้ได้เฉพาะทาง public ทางเดิมยัง login ด้วยรหัสผ่าน

### 2E.5 `tasks/main.yml` — whoami ผ่าน nginx

**เก็บ** task เดิม (~บรรทัด 277–287 ยิง `:8000` ตรง) ไว้ แล้วเพิ่มอีกตัวต่อท้าย ให้พิสูจน์ทั้ง 2 ทาง
```yaml
# ทางที่ browser ใช้จริงหลังเฟส 2: worker → nginx (host network) → backend ต้องยังเห็น IP ของ worker
- name: Verify backend sees the real IP of a lab machine through nginx
  ansible.builtin.uri:
    url: "http://{{ webservice_bind_ip }}:{{ webservice_http_port }}{{ webservice_api_prefix }}/v1/whoami"
    return_content: true
  delegate_to: "{{ groups['workers'][0] }}"
  become: false
  register: whoami_nginx
  failed_when: >-
    whoami_nginx.json.data.clientIp != hostvars[groups['workers'][0]]['ansible_host']
    or whoami_nginx.json.data.labMachine is none
  when: groups['workers'] | default([]) | length > 0
```
ไม่ผ่าน = deploy fail (ถูกต้อง: ไม่งั้นนักศึกษาในห้องแลปไป AWS หมด)

### 2E.6 รัน (public ยังปิด)

```bash
ansible-playbook -i inventory.home.yml site.yml --limit webservice --tags web-service
```
**ผ่านเมื่อ:** deploy จบ (whoami ผ่าน nginx ผ่าน), เครื่องแลปกด Start ได้ warm pod, เครื่องนอกห้องกด Start AWS ได้

---

## Phase 2F: Cloudflare portal + SSO

1. Zero Trust → Tunnels → Create tunnel `vlab-portal` → token ใส่ `ansible/group_vars/all.yml` เป็น `vault_portal_tunnel_token`
2. Public hostname: `vlab.bell-lab.space` → Service `HTTP` `127.0.0.1:8088`
3. DNS: `vlab` CNAME `<portal-tunnel-id>.cfargotunnel.com` Proxied (record ชื่อตรงชนะ wildcard `*` ของ lab gateway)
4. (SSO) Google Cloud Console → OAuth client → Authorized redirect URI `https://vlab.bell-lab.space/auth/callback` (หน้า frontend ไม่ใช่ `/api/...` — D8)
5. deploy
   ```bash
   ansible-playbook -i inventory.home.yml site.yml --limit webservice --tags web-service -e webservice_public_enabled=true
   ```

**ผ่านเมื่อ:** tunnel `vlab-portal` Healthy, มือถือ 4G เปิด `https://vlab.bell-lab.space` เห็นหน้า login

**ถอย:** `-e webservice_public_enabled=false` (cloudflared-portal หยุด, ทางเดิมไม่กระทบ)

---

## Phase 2G: เทสเฟส 2

ใช้ตาราง "เฟส 2" ใน [AWS_LAB_PUBLIC_ACCESS.md](AWS_LAB_PUBLIC_ACCESS.md) ข้อ 8 ครบทุกข้อ และเพิ่ม

| # | เคส | ต้องเห็น |
|---|---|---|
| P7 | เครื่องแลปเปิดทาง Tailscale แล้ว login | cookie ไม่มี `Secure` แต่ login ค้างได้ (refresh ผ่าน) |
| P8 | มือถือเปิดทาง public แล้ว login | cookie มี `Secure` |
| P9 | ส่ง `X-Vlab-Entry: tailnet` + `X-Real-IP: <worker>` จากมือถือทาง public | ยังได้ AWS (nginx ทับ header) |
| P10 | หน้า admin (sqladmin) | ยังเข้าได้แบบเดิม (ยังเข้าทาง :8000 ตรง ไม่ผ่าน nginx — ถ้าย้ายมาผ่าน nginx ต้องแก้ `admin_auth.py` ด้วย) |
| P11 | อัปโหลด lab image ผ่านทาง public | ไฟล์ขึ้น R2 ตรง (presigned) ไม่ผ่าน Cloudflare ของเรา ไม่ติด 100MB |

---

## Phase 3 (ยังไม่ทำ)

forward-auth + แยก domain ของ lab ดู [AWS_LAB_PUBLIC_ACCESS.md](AWS_LAB_PUBLIC_ACCESS.md) ข้อ 6
cookie ชื่อ `__Host-` ทำได้เฉพาะทาง HTTPS (ต้อง `Secure` + ไม่มี `Domain`) ทางเดิมที่เป็น HTTP ใช้ไม่ได้ จึงเลื่อนมาทำพร้อมเฟส 3

---

## 7. แบ่ง PR (ลำดับ merge)

แต่ละ PR merge ได้เองโดยไม่ทำให้ prod เปลี่ยน จนกว่าจะเปิด flag / apply infra

| PR | branch | ไฟล์ | merge แล้วมีผลไหม | ต้องผ่านก่อน merge |
|---|---|---|---|---|
| 1 | `feature/lab-gateway-backend` | 1A.1–1A.7 + `main.py` (D9) | ไม่ (flag ปิด) | `pytest tests/session` ผ่าน |
| 2 | `feature/lab-gateway-ansible-vars` | 1A.8 (`web-service` defaults / `backend.env.j2` / `all.yml.example`) | ไม่ (ค่าเริ่ม false) | `ansible-playbook --check` ของ webservice ไม่มี diff นอกจาก `.env` |
| 3 | `infra/router-gateway` | 1B (`router.tf`, `security_groups.tf`) + 1C (`vlab-acl.hujson.example`, `vlab-tags.tsv.example`) | **ใช่** ตอน `terraform apply` / `tailscale-acl.sh apply` | plan ตรงตามข้อ 1B.3, R1–R3 |
| 4 | `infra/lab-gateway-role` | 1E (`ansible/roles/lab-gateway/**`, `site.yml`, `inventory.yml.example`) | **ใช่** ตอนรัน role | 1E.5 ผ่าน, R1–R4 |
| 5 | `fix/music-lab-vite-hosts` (ถ้า 1F.0 ไม่ผ่าน) | `music-lab/client/vite.config.js` | ต้อง build image ใหม่ | G4 |
| 6 | `feature/portal-client-ip` | 2A | ไม่ (`TRUSTED_PROXY_CIDRS_STR` ว่าง) | test 2A.4 |
| 7 | `feature/async-start` | 2B + 2C | ไม่ (`SESSION_ASYNC_LAUNCH=false`, frontend รองรับทั้งสองแบบ) | test 2B.4, `npm run build` |
| 8 | `feature/portal-public-entry` | 2D + 2E | **ใช่** (nginx เปลี่ยนเป็น host network) | whoami ผ่าน nginx (2D / 2E.5) |

PR 1, 2, 6, 7 ทำพร้อมกันได้ (คนละไฟล์ ยกเว้น `settings.py` ที่ PR 1 / 6 / 7 แก้คนละบล็อก — merge ทีละตัวแล้ว rebase)
PR 3 → 4 ต้องตามลำดับ และต้องมีคนที่มีสิทธิ์ AWS / tailnet admin อยู่ด้วย

---

## 8. ถอยกลับ (สรุป เรียงจากเบาไปหนัก)

| ระดับ | ทำอะไร | ผล |
|---|---|---|
| 1 | `-e webservice_public_enabled=false` | ปิดทาง public ของ portal |
| 2 | `-e webservice_lab_gateway_enabled=false` | lab ใหม่กลับเป็น private IP |
| 3 | `systemctl disable --now traefik cloudflared-lab` บน router | ปิด proxy |
| 4 | `./script/tailscale-acl.sh rollback <backup>` + ลบ tag | ACL เดิม |
| 5 | revert terraform + `apply` | router กลับ t3.micro / SG เดิม |
| 6 | สร้าง router ใหม่จาก AMI ข้อ 0.4 | approve route ใหม่ |

---

## 9. บันทึกผล (เติมระหว่างทำ)

| วันที่ | phase | ใคร | ผล / หมายเหตุ |
|---|---|---|---|
| | 0.1 คำตอบคำถาม | | |
| | 0.3 สถานะ router | | |
| | 1F G1–G12 | | |
| | 2D whoami ผ่าน nginx (D4) | | |
| | 2G | | |
