# นักศึกษานอก tailnet เข้า portal และ lab บน AWS ได้ (lab gateway + public portal)

> สถานะ: **อนุมัติแล้ว ใช้ทางเลือก A (router เดิม)** (2026-11-09) ยังไม่มีโค้ด — ขั้นตอนลงมืออยู่ใน [AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md](AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md)
> ที่มา: คาบ online ([AWS_PRELAUNCH.md](AWS_PRELAUNCH.md)) เปิด EC2 รอไว้ได้แล้ว แต่นักศึกษาที่อยู่บ้าน (ไม่อยู่ใน tailnet)
> ยังเข้า portal ไม่ได้ และถึงกด Start ได้ ก็เปิด lab บน EC2 ไม่ได้

## 1. สรุป

| ส่วน | ทำอะไร | ผลลัพธ์ |
|---|---|---|
| **เฟส 1: lab gateway** | EC2 เล็ก ๆ ตัวใหม่ใน public subnet รัน `cloudflared` + Traefik ส่งต่อ `https://l-<token>-<port>.bell-lab.space` ไปที่ `10.10.2.x:<port>` | เปิด lab บน AWS ได้จากที่ไหนก็ได้ ผ่าน HTTPS |
| **เฟส 2: public portal** | เพิ่มทางเข้า `https://vlab.bell-lab.space` ผ่าน Cloudflare Tunnel โดย**เก็บทางเข้าเดิม** (Tailscale IP) ไว้ให้เครื่องในห้องแลป | นักศึกษา login + กด Start จากบ้านได้ ห้องแลปยังได้ warm pod เหมือนเดิม |
| เฟส 3 (ทีหลัง) | forward-auth ให้ลิงก์ lab ต้อง login ก่อน + แยก domain ของ lab | ลิงก์หลุดก็เข้าไม่ได้ |

เฟส 1 กับ 2 แยกเทสกันได้ เฟส 1 เทสได้ก่อนโดย login บนเครื่องที่อยู่ใน tailnet แล้วเอาลิงก์ lab ไปเปิดบนมือถือที่ใช้ 4G

## 2. สภาพตอนนี้ (อ่านจากโค้ด 2026-11-06)

| ชั้น | ตอนนี้ | ที่มา |
|---|---|---|
| portal | uvicorn :8000 กับ nginx :80 ผูกกับ Tailscale IP (`BIND_IP`) เท่านั้น `VITE_API_URL` และ CORS เป็น `http://<tailscale-ip>` | `ansible/roles/web-service/defaults/main.yml`, `templates/compose.env.j2`, `templates/backend.env.j2`, `web-portal/docker-compose.prod.yml` |
| endpoint ของ lab บน AWS | ค่าจาก `sky.endpoints()` ตรง ๆ = `http://10.10.2.x:<port>` (`use_internal_ips: true`) | `session_service.py` `_run_sky_launch`, `roles/skypilot-node/tasks/main.yml` |
| ทางเข้า private subnet | Tailscale subnet router (`vlab-ts-router`) ที่เดียว เข้าได้เฉพาะเครื่องใน tailnet | `terraform/router.tf`, `network.tf` |
| router → lab | ใน terraform มีแค่ 22 และ 8080 ส่วน 5173 / 8443 เพิ่มด้วย AWS CLI (ยังไม่ import) ไม่มี 3000 / 8000 | `terraform/security_groups.tf`, `docs/archive/NextToU.md` |
| lab SG ingress | SkyPilot เปิดพอร์ตตาม `ports:` ของ task จาก `0.0.0.0/0` บน SG `vlab-lab-instances` ให้เอง | `sky/provision/aws/instance.py` `open_ports` |
| แยกห้องแลป / ข้างนอก | เทียบ IP ของ connection (`request.client.host`) กับ InternalIP ของ worker (= Tailscale IP เพราะ `flannel_iface: tailscale0`) ไม่เชื่อ `X-Forwarded-For` | `session_route.py`, `warm_pod_service.py` `node_for_ip`, ansible เช็กด้วย `/v1/whoami` จาก worker |
| กด Start | `POST /sessions` รอจน launch เสร็จแล้วค่อยตอบ (AWS ~97–119 วิ) frontend ไม่ poll | `frontend/src/services/session.ts` |
| auth ของหน้าเว็บ | access token ใน localStorage ส่งเป็น `Authorization: Bearer` และมี refresh cookie แบบ httponly | `frontend/src/services/api.ts`, `auth_service.py` |
| SSO | ใน prod ยังไม่ได้ตั้ง (`GOOGLE_REDIRECT_URI` ไม่อยู่ใน `backend.env.j2`) frontend ส่ง `redirect_uri` มาเองได้ | `sso_adapter.py`, `auth_route.py` |

> `ARCHITECTURE.md` กับ `k8s/auth/` เป็นแบบที่ออกแบบไว้ตอนแรก (cloudflared ใน K3s, t4g.nano ASG, NAT GW, Spot)
> ไม่ตรงกับของที่ deploy จริง doc นี้ยึดตามตารางข้างบน

## 3. ทางเลือกที่พิจารณา

### 3.1 รูปแบบ URL ของ lab

| แบบ | ตัวอย่าง | ผล |
|---|---|---|
| path | `lab.bell-lab.space/<course>/<lab>/<token>/3000/` | ❌ app ที่อ้าง asset แบบ absolute (`/assets/x.js`, `/@vite/client`, `/openapi.json`) พังหมด ต้องตั้ง base path ทุก lab และทุก lab อยู่ origin เดียวกัน = localStorage / cookie ปนกันข้ามนักศึกษา |
| **subdomain ชั้นเดียว** | `l-<token>-3000.bell-lab.space` | ✅ app อยู่ที่ `/` เหมือนรันในเครื่อง แต่ละ session แต่ละพอร์ตเป็นคนละ origin, Universal SSL ฟรีครอบ `*.bell-lab.space` |
| subdomain 2 ชั้น | `<token>-3000.lab.bell-lab.space` | ⚠️ Universal SSL ไม่ครอบชั้นที่ 2 ต้องซื้อ Advanced Certificate Manager |
| DNS record ต่อเครื่อง (Route53 → private IP) | `s1.lab...` → `10.10.2.14` | ❌ คนนอก tailnet ยังไปไม่ถึง private IP อยู่ดี |

ไม่ใส่ course / lab id ใน URL: proxy ใช้แค่ token หาเครื่อง ใส่ไปก็เปิดเผยข้อมูลภายในเปล่า ๆ

### 3.2 วาง proxy ไว้ที่ไหน

| ที่ | ข้อดี | ข้อเสีย |
|---|---|---|
| A. บน `vlab-ts-router` ตัวเดิม | ไม่มีค่าเครื่องเพิ่ม | router เป็น member ของ tailnet (ACL ให้ member `*:*`) ถ้า proxy ที่เปิดรับคนทั้งโลกถูกเจาะ = เข้า tailnet ทั้งก้อน, router ลงด้วยมือไม่มี IaC, ถ้า proxy กินเครื่องจนเต็ม SkyPilot SSH เข้า EC2 ไม่ได้ (launch ทุกตัวค้าง) |
| **B. EC2 ใหม่ `vlab-lab-gateway`** | แยก blast radius: ติด `tag:vlab-gateway` ที่ ACL ให้ไปได้แค่ backend :8000, ขยายเครื่องแยกจาก router, จัดการด้วย terraform + ansible ได้ตั้งแต่แรก | ค่าเครื่อง + public IPv4 (ประมาณ $10–20/เดือน ดูข้อ 9) |
| C. บนเครื่อง web-service (on-prem) วิ่งผ่าน tailnet ไป AWS | ทุกอย่างอยู่ใน ansible เดิม | traffic lab ทั้งหมดผ่านเน็ตของ on-prem + Tailscale (อาจตกไป DERP relay) เน็ตที่ on-prem เคยมีปัญหา (QUIC ถูกบล็อก, Cloudflare ช้า) และต้อง `--accept-routes` บน web-service |

**เลือก B** เหตุผลหลักคือความปลอดภัย: เครื่องที่รับ traffic จากอินเทอร์เน็ตไม่ควรมีสิทธิ์เต็มใน tailnet

> 2026-11-06: ทีมจะเริ่มเฟส 1 ด้วย **A แบบมีเงื่อนไข** (ติด tag จำกัดสิทธิ์, ขยายเครื่อง, ไม่ลง Docker, จำกัดทรัพยากรด้วย systemd)
> วิธีทำอยู่ใน [AWS_LAB_GATEWAY_ROUTER.md](AWS_LAB_GATEWAY_ROUTER.md) ถ้าเทสโหลดไม่ผ่านหรือ Pete ไม่อนุมัติ ค่อยย้ายไป B

## 4. เฟส 1: lab gateway

### 4.1 ภาพรวม

```
browser นักศึกษา (ที่ไหนก็ได้)
  │ https://l-k7f2q9xa3m5p8rtc-8443.bell-lab.space
  ▼
Cloudflare edge  ── DNS: *.bell-lab.space  CNAME  <tunnel-id>.cfargotunnel.com (proxied)
  │ TLS จบที่นี่ (Universal SSL)
  ▼ tunnel (cloudflared ต่อออกจาก gateway เอง ไม่เปิดพอร์ตรับเข้า)
vlab-lab-gateway (public subnet, ไม่มี ingress rule)
  │ cloudflared → Traefik :80
  │ Traefik: Host = l-k7f2...-8443.bell-lab.space → http://10.10.2.14:8443
  ▼ VPC local route
EC2 lab ของนักศึกษาคนนั้น (private subnet)

Traefik ดึงตาราง route จาก backend ทุก 5 วิ:
  GET http://<web-service tailscale ip>:8000/api/internal/v1/gateway/routes   (ผ่าน tailnet, header X-Gateway-Token)
```

### 4.2 ชื่อ host

- รูปแบบ `l-<token>-<port>.bell-lab.space`
  - `l-` นำหน้าให้ไม่ชนกับ subdomain อื่นของ zone (`skypilot`, `vlab`) และให้ Traefik / log แยกออกง่าย
  - `<token>` = `secrets.token_bytes(10)` แปลงเป็น base32 ตัวเล็ก = 16 ตัว (80 bit) เดาไม่ได้ในทางปฏิบัติ
  - ความยาว label ประมาณ 25 ตัว (DNS จำกัด 63)
- token 1 ตัวต่อ session ทุกพอร์ตของ session ใช้ token เดียวกัน
- record ที่ตั้งชื่อชัดเจน (เช่น `skypilot.bell-lab.space`) ชนะ wildcard เสมอ ของเดิมจึงไม่กระทบ

### 4.3 Backend

**Database (migration ใหม่)**
- `sessions.gateway_token` (String 32, unique, nullable)
- `sessions.upstreams` (JSONB, nullable) = `{"8443": "http://10.10.2.14:8443"}` ปลายทางจริงที่ Traefik ต้องส่งไป
- `sessions.endpoints` (ของเดิม) = URL ที่นักศึกษาเปิด → เมื่อเปิด gateway เป็น `https://l-...-8443.bell-lab.space`
  หน้าเว็บ (`LabDetail.tsx`) จึงไม่ต้องแก้

**ค่าตั้ง (`settings.py`)**

| ชื่อ | default | ความหมาย |
|---|---|---|
| `LAB_GATEWAY_ENABLED` | `false` | ปิด = endpoint เป็น private IP เหมือนเดิมทุกอย่าง |
| `LAB_GATEWAY_DOMAIN` | `""` | เช่น `bell-lab.space` |
| `LAB_GATEWAY_TOKEN` | `""` | secret ที่ Traefik ส่งมาใน header (≥ 32 ตัว) |

**`session_service.py`**
- `_new_sky_session`: run_target AWS + เปิด gateway → สุ่ม `gateway_token` ตอนสร้าง record (ทั้งกด Start เองและ prelaunch)
- `_run_sky_launch`: หลังได้ `sky.endpoints()` → เก็บของจริงลง `upstreams` และเก็บ URL สาธารณะลง `endpoints`
- `_lab_envs` (AWS + gateway): ส่ง env เข้า container เพิ่ม
  - `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=.bell-lab.space` ให้ Vite dev server ยอมรับ Host ใหม่ (ดู 4.6)
  - `VLAB_PUBLIC_URL_<port>=https://l-<token>-<port>.bell-lab.space` ให้ lab ที่ต้องรู้ URL ของตัวเองใช้ (ไม่บังคับ)
- K8s / warm pod / direct pod **ไม่แตะ** (คาบ on-site เปิดจากเครื่องในห้องอยู่แล้ว)

**Route ใหม่ `GET /api/internal/v1/gateway/routes`**
- ต้องมี header `X-Gateway-Token` ตรงกับ `LAB_GATEWAY_TOKEN` (เทียบด้วย `hmac.compare_digest`) ไม่ตรง = 404
- คืน dynamic config ของ Traefik (JSON) ของ session ที่ `status = RUNNING`, `is_cloud`, มี `gateway_token` และ `upstreams`

```json
{
  "http": {
    "routers": {
      "s-k7f2q9xa3m5p8rtc-8443": {
        "rule": "Host(`l-k7f2q9xa3m5p8rtc-8443.bell-lab.space`)",
        "service": "s-k7f2q9xa3m5p8rtc-8443",
        "entryPoints": ["web"]
      }
    },
    "services": {
      "s-k7f2q9xa3m5p8rtc-8443": {
        "loadBalancer": { "servers": [{ "url": "http://10.10.2.14:8443" }] }
      }
    }
  }
}
```

- ตรวจ `upstreams` ทุกตัวต้องอยู่ใน `10.10.2.0/24` / `10.10.3.0/24` ก่อนใส่ตาราง กันข้อมูลผิดใน DB กลายเป็น proxy ไปที่อื่น
- session จบ (STOPPED / FAILED / PRELAUNCH_UNCLAIMED) → หลุดจากตารางในรอบ poll ถัดไป (≤ 5 วิ) → ลิงก์ได้ 404
- เครื่องที่ prelaunch ไว้แต่ยังไม่มีคนรับ: **ไม่ใส่ในตาราง** จนกว่าจะ claim (ไม่มีใครควรเปิดลิงก์ของเครื่องที่ยังไม่ได้แจก)

### 4.4 Gateway (ansible role ใหม่ `lab-gateway`)

docker compose 2 ตัว (image ทั้งคู่มี arm64)
- `cloudflare/cloudflared` (ปัก version, ไม่ใช้ `latest`) `tunnel --no-autoupdate --protocol http2 run --token ...`
  ใช้ `--protocol http2` ตาม role skypilot-node (QUIC/UDP 7844 เคยถูกบล็อก) ถึง gateway อยู่ AWS จะไม่โดน แต่ใช้ค่าเดียวกันไว้ก่อน
- `traefik:v3.x` (ปัก version)
  - entryPoint `web` :80 ฟังเฉพาะ docker network ภายใน ไม่ publish ออก host
  - `providers.http.endpoint` = route ข้อ 4.3, `pollInterval: 5s`, `headers.X-Gateway-Token`
  - `passHostHeader: true` (ค่าเริ่มต้น) — code-server ตรวจ Origin ของ websocket กับ Host ต้องส่ง Host จริง
  - access log เปิด (สำหรับ SIEM ทีหลัง) แต่ไม่ log query string
- Tailscale: `tailscale up --advertise-tags=tag:vlab-gateway` ไม่ advertise / ไม่ accept routes

**Cloudflare (ทำครั้งเดียว)**
- สร้าง tunnel ใหม่ `vlab-lab-gateway` (remotely managed) ไม่ใช้ tunnel ของ skypilot ร่วม
- Public hostname `*.bell-lab.space` → `http://traefik:80`
- DNS ได้ record `*` CNAME → `<tunnel-id>.cfargotunnel.com` (proxied) — wildcard แบบ proxied ใช้ได้ทุก plan ตั้งแต่ 2022
- ต้องเช็กว่า zone `bell-lab.space` เป็น full setup (ไม่ใช่ CNAME setup) ไม่งั้น Universal SSL ไม่ออก cert ให้ wildcard

**Tailscale ACL (`tailscale/vlab-acl.hujson`)**
```hujson
// gateway รับ traffic จากอินเทอร์เน็ต → ให้ไปได้แค่ backend :8000 ที่เดียว
{"action": "accept", "src": ["tag:vlab-gateway"], "proto": "tcp", "dst": ["<web-service tailscale ip>:8000"]},
```
พร้อม test: `tag:vlab-gateway` deny `tag:vlab-server:22`, `tag:vlab-server:6443`, `tag:vlab-worker:22`, `tag:vlab-registry:5002`

### 4.5 Terraform (`terraform/gateway.tf` ใหม่ + แก้ `security_groups.tf`)

- `aws_instance.lab_gateway`: `t4g.small` (ARM), Ubuntu 24.04 arm64, `public_a`, public IPv4 (ไม่มี NAT จึงต้องมีเพื่อออก Cloudflare / Tailscale), IMDSv2, SSM instance profile แบบ router, tag `vlab:protected`
- `sg-lab-gateway`: **ไม่มี ingress เลย**
  - egress `tcp 443` + `tcp/udp 7844` → `0.0.0.0/0` (cloudflared)
  - egress `udp` ทั้งหมด → `0.0.0.0/0` (WireGuard / STUN ของ Tailscale แบบเดียวกับ router)
  - egress `tcp 80` → `0.0.0.0/0` (apt)
  - egress → `sg-lab-instances` ช่วงพอร์ตของ lab (เสนอ `3000-9999`)
- `sg-lab-instances`: ingress จาก `sg-lab-gateway` ช่วงพอร์ตเดียวกัน (ไม่พึ่ง rule `0.0.0.0/0` ที่ SkyPilot สร้างอย่างเดียว)
- import กฎ 5173 / 8443 ของ router ที่เพิ่มด้วยมือเข้า terraform ไปพร้อมกัน

### 4.6 สิ่งที่ app ใน lab ต้องรู้

| app | ผล | ต้องทำ |
|---|---|---|
| code-server (8443) | ✅ Host ตรงกับ Origin เพราะ Traefik ส่ง Host จริง ได้ HTTPS = secure context (webview / clipboard ใช้ได้ ตอนนี้บน http ใช้ไม่ได้) | ไม่ต้อง |
| Vite dev (5173) | Vite ≥ 5.4.12 / 6.0.9 บล็อก Host ที่ไม่ใช่ localhost / IP ("Blocked request") | backend ส่ง `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` ให้แล้ว (4.3) HMR ต่อ `wss://` ที่ host เดียวกับหน้าเว็บเอง ถ้า lab ตั้ง `server.hmr.clientPort` เองจะพัง |
| Flask / FastAPI / Express | ✅ ไม่ตรวจ Host | — |
| Django | `ALLOWED_HOSTS` ต้องมี `.bell-lab.space` | บอกอาจารย์ใน guide ของ lab image |
| frontend เรียก backend ใน lab คนละพอร์ต | `fetch("http://localhost:8080")` พังตั้งแต่ตอนนี้แล้ว (browser เรียก localhost ของนักศึกษา) | ใช้ proxy ของ dev server แบบที่ `music-lab/client/vite.config.js` ทำกับ `/api` หรืออ่าน `VLAB_PUBLIC_URL_<port>` |

## 5. เฟส 2: public portal (ทางเข้า 2 ทาง)

### 5.1 ปัญหาที่ต้องกัน

ถ้าเอา portal ไปไว้หลัง Cloudflare เฉย ๆ backend จะเห็น IP ของ cloudflared ทุก request
→ `node_for_ip` ไม่เจอ worker → **นักศึกษาในห้องแลปทุกคนไป AWS** (warm pod ไม่ถูกใช้ + เสียเงินทุกคาบ)
อ่าน `CF-Connecting-IP` ก็ไม่ช่วย เพราะเป็น public IP ของมหาลัยหลัง NAT ไม่ใช่ Tailscale IP ของเครื่อง

### 5.2 การออกแบบ

```
เครื่องในห้องแลป ── http://<tailscale ip>/ ──────────────► nginx (frontend container) ─┐
                    (ทางเดิม, ไม่ผ่าน Cloudflare)          X-Real-IP = $remote_addr     │
                                                           = Tailscale IP ของ worker   ├─► backend :8000
นักศึกษาที่บ้าน ── https://vlab.bell-lab.space/ ── CF ──► cloudflared ──► nginx ───────┘
                                                           X-Real-IP = IP ของ cloudflared
                                                           → ไม่ใช่ worker → นับเป็นข้างนอก (ถูกต้อง)
```

- **frontend เรียก API แบบ relative** `VITE_API_URL=/api` (build ครั้งเดียวใช้ได้ทั้งสองทาง ไม่ติด CORS)
- **nginx ของ frontend proxy `/api/`** ไป backend และเขียนทับ header เอง
  ```nginx
  location /api/ {
      proxy_pass http://BACKEND_HOST:8000;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;        # ทับของที่ client ส่งมาเสมอ
      proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
      proxy_read_timeout 600s;                          # ทางเดิมยังรอ launch แบบ sync ได้
  }
  ```
- **backend อ่าน IP จริงแบบปลอดภัย** helper `client_ip(request)` ใช้ใน `create_session` และ `whoami`
  - peer อยู่ใน `TRUSTED_PROXY_CIDRS` (subnet docker bridge ของ frontend) → ใช้ `X-Real-IP`
  - peer อื่น (คนในทีมยิง :8000 ตรง) → ใช้ IP ของ connection แบบเดิม → ปลอม header ไม่ได้
- **cloudflared** เป็น service ใหม่ใน `docker-compose.prod.yml` (เปิดด้วย profile / ตัวแปร) ต่อเข้า nginx เท่านั้น ไม่ต่อ backend ตรง
- `whoami` ที่ ansible ใช้เช็กเปลี่ยนไปยิงผ่าน `http://<bind ip>/api/v1/whoami` (ผ่าน nginx) เพื่อพิสูจน์ว่า docker ไม่ NAT ทับ IP ของ worker
  (docker publish port ด้วย iptables DNAT เก็บ source IP เดิมไว้ แต่ต้องยืนยันบนเครื่องจริง)

### 5.3 กด Start ต้องไม่รอเกิน 100 วิ

Cloudflare (Free/Pro/Business) ตัด request ที่ origin ไม่ตอบใน 100 วิ เป็น error 524
`POST /sessions` ตอนนี้รอ launch AWS ~97–119 วิ → **ผ่านทาง public จะได้ 524 บ่อย** (EC2 ยังขึ้นต่อ แต่หน้าเว็บขึ้น error)
- เปลี่ยนเป็น async: `POST /sessions` สร้าง record PENDING แล้วตอบทันที (202 + `session_id`) launch ใน background
  ใช้ `_new_sky_session` + `_run_sky_launch` ที่ PR #134 แยกไว้แล้ว + thread pool แบบ `prelaunch_service`
- frontend poll `GET /sessions/{id}` ทุก 3 วิ จน RUNNING / FAILED (endpoint นี้มีอยู่แล้ว)
- warm pod / claim ของ prelaunch ตอบเร็วอยู่แล้ว ตอบ RUNNING ทันทีได้เหมือนเดิม

### 5.4 Auth / cookie / SSO

- Bearer token ใน localStorage ใช้ได้ทั้งสอง origin (แยก login กันต่อ origin — รับได้)
- `AUTH_COOKIE_SECURE`: ทาง public เป็น HTTPS ทางเดิมเป็น HTTP → ตั้ง Secure ตาม `X-Forwarded-Proto` ต่อ request แทนค่าคงที่
- `CORS_ORIGINS_STR` เพิ่ม `https://vlab.bell-lab.space` (เผื่อ request ที่ไม่ผ่าน relative path)
- SSO: Google รับ redirect URI ที่เป็น HTTPS + domain เท่านั้น (ไม่รับ IP) → **SSO จะใช้ได้จริงครั้งแรกบน public domain**
  ลงทะเบียน `https://vlab.bell-lab.space/...callback` ใน Google Console, frontend ส่ง `redirect_uri` ตาม origin (backend รองรับอยู่แล้ว)

### 5.5 ข้อควรรู้

- นักศึกษาที่นั่งในห้องแลปแต่เปิดผ่าน `vlab.bell-lab.space` = นับเป็นข้างนอก → ได้ EC2 (เสียเงิน)
  กันด้วยให้ browser ของเครื่องแลปเปิด Tailscale URL เป็นหน้าแรก และหน้าเว็บบน public origin แสดงป้าย "เปิดจากข้างนอก"
- คาบ on-site ที่มีคนกดจากบ้าน → ได้ EC2 ตามกฎเดิม (คำถามเปิดข้อ 7.4 ของ AWS_PRELAUNCH.md)

## 6. เฟส 3 (ยังไม่ทำ เขียนไว้ให้เห็นทาง)

- **forward-auth**: Traefik `forwardAuth` ถาม backend ทุก request ว่าผู้เปิดเป็นเจ้าของ session ไหม
  browser ไม่ส่ง Bearer ไปที่ `l-*.bell-lab.space` ต้องมี handshake: portal เปิด `https://l-.../__vlab/auth?ticket=<ใช้ครั้งเดียว 60 วิ>`
  → gateway แลก ticket เป็น cookie ของ host นั้น แล้ว redirect ไป `/`
- **แยก domain ของ lab** (เช่นซื้อ domain ใหม่สำหรับ lab โดยเฉพาะ) โค้ดใน lab คือโค้ดที่นักศึกษาเขียนเอง ถ้าอยู่ใต้ `bell-lab.space` เดียวกับ portal
  มันตั้ง cookie `Domain=bell-lab.space` ได้ ซึ่งจะถูกส่งไปที่ `vlab.bell-lab.space` ด้วย (cookie tossing / login CSRF)
  ระหว่างยังไม่แยก ให้ cookie ของ portal ใช้ชื่อขึ้นต้น `__Host-` (ถูก cookie จาก subdomain อื่นทับไม่ได้) ตอนทำเฟส 2

## 7. ความเสี่ยง

| ความเสี่ยง | ระดับ | รับมือ |
|---|---|---|
| ลิงก์ lab หลุด → คนอื่นเข้า IDE / app ได้จนกว่า session จะจบ | กลาง | token 80 bit + ลิงก์ตายพร้อม session, เฟส 3 forward-auth |
| gateway ถูกเจาะ | กลาง | ไม่มี ingress, ACL ไปได้แค่ backend :8000, SG ไปได้แค่ lab ports, ไม่มี IAM นอกจาก SSM |
| EC2 ของนักศึกษาคุยข้ามกันได้ทุกพอร์ต (`lab_self_in` = all) | กลาง (**มีอยู่แล้ว ไม่ใช่ของใหม่**) | แยก issue: ตัด `lab_self_in` หรือจำกัดเป็น SSH ของ SkyPilot |
| ใช้ domain ของเราทำ phishing / ฝากไฟล์ (lab เปิด public ได้) | ต่ำ–กลาง | ลิงก์อายุเท่า lifespan, access log ของ Traefik, เฟส 3 |
| gateway หรือ backend ล่ม | กลาง | gateway ล่ม = เปิด lab AWS ไม่ได้ (EC2 ยังอยู่) backend ล่ม = Traefik ใช้ตารางล่าสุดต่อ (ต้องเทส) |
| Cloudflare ToS / ขีดจำกัด Free | ต่ำ | upload ≤ 100MB ต่อ request, request ≤ 100 วิ (แก้ใน 5.3), ไม่ใช้ส่งวิดีโอยาว ๆ |

## 8. แผนเทส

### เฟส 1 (login จากเครื่องใน tailnet, เปิด lab จากมือถือ 4G ที่ไม่มี Tailscale)

| # | เคส | สิ่งที่ต้องเห็น |
|---|---|---|
| 1 | `LAB_GATEWAY_ENABLED=false` กด Start AWS | endpoint เป็น private IP เหมือนเดิม (ไม่มีอะไรเปลี่ยน) |
| 2 | เปิด gateway กด Start lab music-lab (AWS) | endpoints เป็น `https://l-<token>-<port>.bell-lab.space` ครบ 3 พอร์ต |
| 3 | มือถือ 4G เปิด 8443 (code-server) | เปิดได้, terminal + แก้ไฟล์ได้ (websocket), ไม่มี error origin |
| 4 | มือถือ 4G เปิด 5173 (Vite) | ไม่มี "Blocked request", แก้ไฟล์แล้ว HMR อัปเดต, `/api` ผ่าน proxy ไป 8080 ได้ |
| 5 | ปิด session | ภายใน ~5–10 วิ ลิงก์เดิมได้ 404 |
| 6 | สุ่ม token ปลอม / พอร์ตที่ lab ไม่ได้เปิด | 404 |
| 7 | prelaunch: เครื่องที่ยังไม่ claim | ไม่อยู่ในตาราง route, claim แล้วเปิดได้ทันที |
| 8 | เรียก `/api/internal/v1/gateway/routes` ไม่มี / ผิด token | 404 |
| 9 | จาก gateway: `curl` master :22 / :6443, router :22, 10.10.2.x :22 | ต่อไม่ได้ทั้งหมด (ACL + SG) |
| 10 | 30 session พร้อมกัน (เปิด code-server ค้างไว้) | CPU / CPU credit ของ gateway ไม่หมด (ดู CloudWatch) |

### เฟส 2

| # | เคส | สิ่งที่ต้องเห็น |
|---|---|---|
| 1 | ansible deploy | task whoami (ผ่าน nginx) ผ่าน = เห็น IP จริงของ worker |
| 2 | เครื่องแลปเปิด Tailscale URL กด Start | warm pod เหมือนเดิม |
| 3 | มือถือ 4G เปิด `vlab.bell-lab.space` login + กด Start (ไม่มี prelaunch) | ได้ PENDING ทันที, poll จน RUNNING (~2 นาที) ไม่มี 524 |
| 4 | ส่ง `X-Real-IP: <IP worker>` เองจากข้างนอก / ยิง :8000 ตรงจาก tailnet | ยังนับเป็นข้างนอก |
| 5 | คาบ online + มือถือ 4G | claim เครื่องที่เปิดรอไว้ได้ใน < 5 วิ เปิด lab ผ่าน gateway ได้ |
| 6 | SSO บน public domain | login ได้ |

## 9. ค่าใช้จ่าย (ประมาณ ต้องเช็กราคาจริงใน ap-southeast-1)

- `t4g.small` ประมาณ $15/เดือน + public IPv4 $0.005/ชม. ≈ $3.6/เดือน (เริ่ม `t4g.micro` ได้ถ้าเทสข้อ 10 ผ่าน)
- data transfer ออกเน็ตจาก gateway (คิดตาม GB) — code-server / Vite ใช้ไม่มาก ดูจาก Bill Explorer หลังเทส
- Cloudflare Tunnel + wildcard proxied + Universal SSL: ฟรี

## 10. คำถามที่ต้องตัดสินใจ

1. ใช้ `bell-lab.space` ไหม และใครเป็นเจ้าของ account Cloudflare (ต้องสร้าง tunnel + เข้า DNS)
2. แยก domain ของ lab ตั้งแต่เฟส 1 เลยไหม (ซื้อ domain ใหม่ ปีละไม่กี่ร้อยบาท) หรือรอเฟส 3
3. ยอมรับ gateway เครื่องใหม่ (ข้อ 3.2 B) หรือจะวางบน router เดิมเพื่อประหยัด
4. ช่วงพอร์ตของ lab ที่เปิดให้ gateway (`3000-9999` หรือระบุเป็นรายพอร์ต)
5. web-service รันที่เครื่องไหนจริง (`inventory.yml` ไม่มี group `webservice`) — ต้องรู้ IP สำหรับ ACL และ endpoint ที่ Traefik ดึง
6. เฟส 2 เปลี่ยน Start เป็น async กระทบหน้า Lab ของ frontend ใครรับ

## อ้างอิงภายนอก

- Cloudflare Tunnel ingress รองรับ wildcard hostname: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/local-management/configuration-file/
- wildcard DNS แบบ proxied ใช้ได้ทุก plan: https://developers.cloudflare.com/dns/manage-dns-records/reference/wildcard-dns-records/
- Universal SSL ครอบ root + subdomain ชั้นแรก: https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/
- Traefik HTTP provider (`endpoint`, `pollInterval`, `headers`): https://doc.traefik.io/traefik/providers/http/
- Vite `server.allowedHosts` / `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS`: https://vite.dev/config/server-options.html และ advisory GHSA-vg6x-rcgg-rjx6 (CVE-2025-24010)
- code-server `--trusted-origin` / origin check: https://github.com/coder/code-server/releases/tag/v4.15.0
- Cloudflare 524 (100 วิ): https://community.cloudflare.com/t/100-second-proxy-read-timeout-524-gateway-error-increase/684447
- SkyPilot `open_ports` บน AWS (เปิด `0.0.0.0/0` บน SG ที่ตั้งไว้): `sky/provision/aws/instance.py` ใน .venv (SkyPilot 0.12)
