# lab gateway บน vlab-ts-router (เฟส 1 แบบไม่เพิ่มเครื่อง)

> สถานะ: **Pete อนุมัติแล้ว** (2026-11-09) ยังไม่มีโค้ด — ขั้นตอนลงมือทีละไฟล์อยู่ใน [AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md](AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md)
> ต่อจาก [AWS_LAB_PUBLIC_ACCESS.md](AWS_LAB_PUBLIC_ACCESS.md) — doc นั้นคือภาพรวม (เฟส 1–3) doc นี้คือวิธีทำเฟส 1
> โดยใช้ router ตัวเดิม (ทางเลือก A ในข้อ 3.2) แทน EC2 ใหม่ ส่วนที่ต่างจาก doc หลักเขียนไว้ที่ข้อ 2

## 1. เป้าหมาย

นักศึกษากด Start lab บน AWS แล้วได้ลิงก์ `https://l-<token>-<port>.bell-lab.space` ที่เปิดได้จากที่ไหนก็ได้ (ไม่ต้องอยู่ใน tailnet)
โดยไม่เพิ่มเครื่องใหม่ และไม่ทำให้ SkyPilot launch ผ่าน router พัง

ไม่อยู่ในขอบเขต: portal สาธารณะ (เฟส 2), forward-auth (เฟส 3)
ระหว่างที่ยังไม่มีเฟส 2 คนที่ login ได้ยังต้องอยู่ใน tailnet แต่ลิงก์ lab ที่ได้ไปเปิดที่ไหนก็ได้

```
browser (ที่ไหนก็ได้)
  │ https://l-k7f2q9xa3m5p8rtc-8443.bell-lab.space
  ▼
Cloudflare edge   (*.bell-lab.space, TLS)
  ▼ tunnel (cloudflared ต่อออกจาก router เอง)
vlab-ts-router  ┌ tailscaled   (เดิม: subnet router ให้ SkyPilot / ทีม)
                ├ cloudflared  (ใหม่, systemd)
                └ traefik      (ใหม่, systemd, ฟังแค่ 127.0.0.1:8081)
  ▼ Host → 10.10.2.14:8443
EC2 lab (private subnet)

traefik ดึงตาราง route ทุก 5 วิ ผ่าน tailnet:
  GET http://<web-service tailscale ip>:8000/api/internal/v1/gateway/routes   (header X-Gateway-Token)
```

## 2. ต่างจาก doc หลักตรงไหน

| เรื่อง | doc หลัก (EC2 ใหม่) | doc นี้ (router เดิม) | เหตุผล |
|---|---|---|---|
| ที่รัน | `vlab-lab-gateway` t4g.small | `vlab-ts-router` ขยายเป็น t3.small | ไม่เพิ่มเครื่อง |
| วิธีรัน | docker compose | **binary + systemd ไม่ลง Docker** | Docker แก้ iptables (`FORWARD` policy เป็น DROP + chain ของตัวเอง) เสี่ยงทำ subnet router ที่ forward `tailscale0 → ens5` พัง และ RAM ของ router มีน้อย |
| จำกัดทรัพยากร | `mem_limit` ของ compose | `MemoryMax` / `CPUQuota` ของ systemd | ถ้า proxy กินเครื่องเต็ม tailscaled ต้องยังอยู่ ไม่งั้น launch AWS ทั้งระบบค้าง |
| Tailscale tag | `tag:vlab-gateway` เครื่องใหม่ | ติด `tag:vlab-router` ให้เครื่องเดิม | router ตอนนี้น่าจะเป็น member ที่ได้ `*:*` |
| SG | `sg-lab-gateway` ใหม่ | แก้ `sg-ts-router` เดิม | — |

ส่วน backend (token, `upstreams`, route ตาราง) **เหมือน doc หลักข้อ 4.3 ทุกอย่าง** ถ้าวันหนึ่งย้ายไป EC2 ใหม่ แก้แค่ฝั่งเครื่อง

## 3. ก่อนเริ่ม (ต้องทำก่อนแตะ router)

1. **Pete อนุมัติ** — Pete สร้าง router (`b348626`, 2026-09-30) และลง Tailscale เองด้วยมือ ต้องรู้ว่าเครื่องมีอะไรอยู่บ้าง
2. **เก็บสถานะเดิมของ router** (ผ่าน SSM Session Manager)
   ```bash
   tailscale status
   tailscale debug prefs          # flag ที่ใช้ตอน up: advertise-routes, snat ฯลฯ
   sudo iptables -S FORWARD; sudo iptables -t nat -S
   sysctl net.ipv4.ip_forward
   free -m; df -h; systemctl list-units --type=service --state=running
   ```
   เก็บผลไว้ใน issue / doc เป็นหลักฐานก่อนแก้
3. **snapshot** สร้าง AMI ของ router (`aws ec2 create-image --no-reboot --instance-id <router> --name vlab-ts-router-before-gateway --profile <ของ Pete>`)
4. **เช็กว่าไม่มีคาบ / lab AWS รันอยู่** ตอนขยายเครื่อง (ข้อ 4.1 ต้อง stop/start)

## 4. Infra

### 4.1 Terraform (`terraform/router.tf`, `terraform/security_groups.tf`)

**router.tf**
- `instance_type = "t3.small"` (จาก `t3.micro`: RAM 1GB → 2GB)
  - terraform จะ stop → เปลี่ยน type → start เอง ใช้เวลาไม่กี่นาที ช่วงนั้น SkyPilot launch / SSH เข้า EC2 ไม่ได้
  - **public IPv4 จะเปลี่ยน** (router ไม่ได้ใช้ Elastic IP) Tailscale / Cloudflare ไม่สนใจ แต่ถ้ามีที่ไหน allowlist IP นี้ไว้ต้องแก้
- เปิด `credit_specification { cpu_credits = "unlimited" }` กัน CPU credit หมดตอนคาบใหญ่ (จ่ายเพิ่มเฉพาะตอนใช้เกิน baseline)

**security_groups.tf** (`sg-ts-router` / `sg-lab-instances`)

| rule | ทิศ | พอร์ต | ไป / จาก | หมายเหตุ |
|---|---|---|---|---|
| `ts_router_cloudflared` (ใหม่) | egress | tcp 7844 | `0.0.0.0/0` | cloudflared แบบ `--protocol http2` (udp 7844 มีแล้วใน `ts_router_udp_all`, tcp 443 มีแล้ว) |
| `ts_router_lab_web` (แก้) | egress | tcp **3000–9999** (เดิม 8080) | `sg-lab-instances` | ครอบ 5173 / 8443 ที่เพิ่มด้วย AWS CLI ไว้ |
| `lab_web_from_router` (ใหม่) | ingress | tcp 3000–9999 | `sg-ts-router` | ไม่พึ่ง rule `0.0.0.0/0` ที่ SkyPilot สร้างตาม `ports:` อย่างเดียว |

หลัง `terraform apply` ลบ rule 5173 / 8443 ที่เพิ่มด้วยมือ (`aws ec2 revoke-security-group-egress ...`) เพราะซ้ำกับช่วงใหม่
พอร์ตของ lab image ที่อยู่นอก 3000–9999 จะไม่ถูกใส่ในตาราง route (backend log warning) — ถ้าต้องการพอร์ตอื่นค่อยขยายช่วง

### 4.2 Tailscale

**ติด tag ให้ router** ผ่าน admin console (Machines → `vlab-ts-router` → Edit ACL tags → `tag:vlab-router`)
ใช้ console แทน `tailscale up --advertise-tags` เพราะ `tailscale up` ล้าง flag อื่นที่ไม่ได้ใส่ซ้ำ (เช่น `--advertise-routes`)

ผลของการติด tag ที่ต้องรู้
- เครื่องไม่ใช่ของ user อีกต่อไป key expiry ถูกปิดเอง
- ACL ของ traffic ที่วิ่ง**ผ่าน** subnet route (master → `10.10.2.x`) ตรวจจาก src (master = `tag:vlab-server` ได้ `*:*` อยู่แล้ว) จึงไม่ควรกระทบ SkyPilot — **ต้องเทสข้อ 7.1**
- ต้องเช็กว่า route `10.10.2.0/24`, `10.10.3.0/24` ยัง approved อยู่หลังติด tag ถ้าหายให้ approve ใหม่ หรือเพิ่ม `autoApprovers`

**ACL (`tailscale/vlab-acl.hujson`)**
```hujson
"tagOwners": {
    // ...ของเดิม
    "tag:vlab-router": ["autogroup:admin"],
},

"acls": [
    // ...ของเดิม
    // router รับ traffic จากอินเทอร์เน็ต (cloudflared) → เริ่มคุยใน tailnet ได้แค่ backend :8000 (traefik ดึงตาราง route)
    // traffic ของ subnet route (ทีม / master → 10.10.x) ไม่ใช่ router เริ่ม ไม่ต้องมีกฎ src router
    {"action": "accept", "src": ["tag:vlab-router"], "proto": "tcp", "dst": ["<web-service tailscale ip>:8000"]},
],

"tests": [
    // ...ของเดิม
    {
        "src": "tag:vlab-router",
        "proto": "tcp",
        "accept": ["<web-service tailscale ip>:8000"],
        "deny": ["tag:vlab-server:22", "tag:vlab-server:6443", "tag:vlab-server:30880",
                 "tag:vlab-worker:22", "tag:vlab-worker:8080", "tag:vlab-registry:5002"],
    },
],
```
apply ด้วย `script/tailscale-acl.sh` เหมือนเดิม

### 4.3 Cloudflare (ทำครั้งเดียวใน dashboard ของเจ้าของ zone `bell-lab.space`)

1. Zero Trust → Networks → Tunnels → **Create tunnel** ชื่อ `vlab-lab-gateway` (แยกจาก tunnel ของ skypilot) เก็บ token ใส่ vault
2. Public hostname: subdomain `*` domain `bell-lab.space` → Service `HTTP` URL `127.0.0.1:8081`
3. DNS ต้องมี `*` CNAME → `<tunnel-id>.cfargotunnel.com` แบบ **Proxied** (dashboard มักสร้างให้ ถ้าไม่สร้างให้เพิ่มเอง)
4. เช็กว่า zone เป็น full setup และ Universal SSL active (cert ครอบ `*.bell-lab.space`)
5. record ที่มีชื่อชัดเจนอยู่แล้ว (`skypilot.bell-lab.space` ฯลฯ) ชนะ wildcard — เช็กหลังตั้งว่าของเดิมยังเปิดได้

## 5. Ansible role ใหม่ `lab-gateway`

### 5.1 Inventory / การเข้าเครื่อง

```yaml
# ansible/inventory.yml
    aws_router:
      hosts:
        vlab-ts-router:
          ansible_host: <tailscale ip ของ router>
          ansible_user: ubuntu
```
- router สร้างโดยไม่มี key pair และ SG ไม่เปิด 22 จากข้างนอก → เข้าผ่าน **tailnet** (WireGuard ไม่ผ่าน SG)
- ครั้งแรกใส่ public key ของคนที่รัน ansible ลง `~ubuntu/.ssh/authorized_keys` ผ่าน SSM
- ไม่รัน role `common` / `tailscale` กับ router (Tailscale ของ router ตั้งด้วยมือ ห้าม role ไปแตะ flag)

```yaml
# ansible/site.yml
- name: Provision lab gateway on the AWS Tailscale router
  hosts: aws_router
  become: yes
  roles:
    - { role: lab-gateway, tags: ['lab-gateway'] }
```

### 5.2 สิ่งที่ role ทำ

| task | รายละเอียด |
|---|---|
| ติดตั้ง cloudflared | apt repo ทางการของ Cloudflare **ปัก version** (`lab_gateway_cloudflared_version`) |
| ติดตั้ง traefik | binary จาก GitHub release `traefik_v3.x_linux_amd64.tar.gz` ปัก version + เช็ก sha256 วางที่ `/usr/local/bin/traefik` |
| user | `traefik` และ `cloudflared` แบบ system user ไม่มี shell |
| config | `/etc/traefik/traefik.yml` (template ข้อ 5.3) owner root:traefik mode 0640 (มี gateway token) |
| secret | `/etc/cloudflared/env` = `TUNNEL_TOKEN=...` mode 0600 |
| systemd | `traefik.service`, `cloudflared-lab.service` (template ข้อ 5.4) enable + start |
| verify | `curl -s -o /dev/null -w '%{http_code}' -H 'Host: l-nope-8080.bell-lab.space' http://127.0.0.1:8081/` ต้องได้ 404 และ `cloudflared tunnel info` / log ต้องเห็น connection registered |
| verify ห้ามพัง | `tailscale status` ยัง online, `ip_forward = 1`, `iptables -S FORWARD` เหมือนก่อนลง |

ตัวแปร (`roles/lab-gateway/defaults/main.yml`)
```yaml
lab_gateway_domain: bell-lab.space
lab_gateway_listen: 127.0.0.1:8081
lab_gateway_backend_url: "http://{{ <web-service tailscale ip> }}:8000/api/internal/v1/gateway/routes"
lab_gateway_token: "{{ vault_lab_gateway_token }}"          # ค่าเดียวกับ LAB_GATEWAY_TOKEN ของ backend
lab_gateway_tunnel_token: "{{ vault_lab_gateway_tunnel_token }}"
lab_gateway_traefik_version: "3.x.y"                         # ปักเลขจริงตอนทำ
lab_gateway_cloudflared_version: "2026.x.y"
lab_gateway_traefik_memory_max: 384M
lab_gateway_cloudflared_memory_max: 256M
```

### 5.3 `traefik.yml`

```yaml
entryPoints:
  web:
    address: "{{ lab_gateway_listen }}"
    forwardedHeaders:
      trustedIPs: ["127.0.0.1/32"]       # เชื่อ X-Forwarded-* จาก cloudflared บนเครื่องเดียวกันเท่านั้น
    transport:
      respondingTimeouts:
        readTimeout: 600s                # v3 ตั้ง 60s เป็นค่าเริ่มต้น upload นาน ๆ จะถูกตัด
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
      defaultMode: drop                  # ไม่เก็บ cookie / header ของนักศึกษาลง log
```
`passHostHeader` เป็น true อยู่แล้ว (code-server ตรวจ Origin ของ websocket กับ Host) ไม่ต้องตั้ง

### 5.4 systemd

```ini
# /etc/systemd/system/traefik.service
[Service]
User=traefik
ExecStart=/usr/local/bin/traefik --configFile=/etc/traefik/traefik.yml
Restart=on-failure
MemoryMax={{ lab_gateway_traefik_memory_max }}
CPUQuota=70%
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

# /etc/systemd/system/cloudflared-lab.service
[Service]
User=cloudflared
EnvironmentFile=/etc/cloudflared/env
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --protocol http2 run
Restart=on-failure
MemoryMax={{ lab_gateway_cloudflared_memory_max }}
CPUQuota=50%
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
```
ฟังแค่ `127.0.0.1` ไม่ต้องใช้ root / capability ใด ๆ
`--protocol http2` ตาม role `skypilot-node` (cloudflared รุ่นใหม่ไม่ถอยจาก QUIC ไป http2 เอง)

## 6. Backend (เหมือน doc หลักข้อ 4.3 — สรุปสิ่งที่ต้องเขียน)

| ไฟล์ | งาน |
|---|---|
| `migrations/versions/<ใหม่>.py` | `sessions.gateway_token` (String 32, unique, nullable), `sessions.upstreams` (JSONB, nullable) |
| `app/models/session.py` | 2 column ข้างบน |
| `app/configs/settings.py` | `LAB_GATEWAY_ENABLED=false`, `LAB_GATEWAY_DOMAIN=""`, `LAB_GATEWAY_TOKEN=""` (เปิดแล้วต้อง ≥ 32 ตัว ไม่งั้นไม่ start), `LAB_GATEWAY_PORT_RANGE=3000-9999` |
| `app/services/session_service.py` | `_new_sky_session`: สุ่ม token (AWS + เปิด gateway), `_run_sky_launch`: `upstreams` = ของจริง / `endpoints` = URL สาธารณะ, `_lab_envs` (AWS): `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=.<domain>` + `VLAB_PUBLIC_URL_<port>` |
| `app/services/lab_gateway_service.py` (ใหม่) | สร้าง dynamic config ของ Traefik จาก session ที่ `RUNNING` + `is_cloud` + มี token ตัด upstream ที่ไม่อยู่ใน `10.10.2.0/24` / `10.10.3.0/24` หรือพอร์ตนอกช่วง, เครื่อง prelaunch ที่ยังไม่ claim ไม่ใส่ |
| `app/routes/lab_gateway_route.py` (ใหม่) | `GET /api/internal/v1/gateway/routes` เช็ก `X-Gateway-Token` ด้วย `hmac.compare_digest` ไม่ตรง / ปิด gateway = 404 |
| `tests/session/test_lab_gateway.py` (ใหม่) | token ผิด = 404, เฉพาะ RUNNING, prelaunch ยังไม่ claim ไม่อยู่, upstream นอก subnet ถูกตัด, ปิด flag = endpoint แบบเดิม |
| `ansible/roles/web-service` | `webservice_lab_gateway_enabled: false` + `*_domain` + `*_token` → `backend.env.j2` |

frontend ไม่ต้องแก้ (`LabDetail.tsx` แสดง `session.endpoints` อยู่แล้ว)

## 7. แผนเทส

### 7.1 router ยังทำงานเดิมได้ (ทำทุกครั้งหลังแตะ router: ขยายเครื่อง / ติด tag / ลง role)

| # | เคส | ต้องเห็น |
|---|---|---|
| R1 | `tailscale status` บน router และบน master | router online, master เห็น route `10.10.2.0/24`, `10.10.3.0/24` |
| R2 | กด Start lab AWS (ยังไม่เปิด gateway) | launch ผ่านใน ~1.5–2 นาที (SkyPilot SSH ผ่าน router ได้) |
| R3 | เครื่องใน tailnet เปิด `http://10.10.2.x:8443` | เปิดได้เหมือนเดิม |
| R4 | `systemctl stop traefik cloudflared-lab` แล้วทำ R2 | ยัง launch ได้ (proxy ล่มไม่กระทบ SkyPilot) |

### 7.2 gateway (login บนเครื่องใน tailnet, เปิดลิงก์บนมือถือ 4G ที่ไม่มี Tailscale)

| # | เคส | ต้องเห็น |
|---|---|---|
| G1 | `LAB_GATEWAY_ENABLED=true` กด Start music-lab (AWS) | endpoints เป็น `https://l-<token>-{8080,5173,8443}.bell-lab.space` |
| G2 | มือถือเปิด 8443 (code-server) | เปิดได้, terminal ใช้ได้, ไม่มี "Reconnecting" |
| G3 | ทิ้ง code-server ไว้เฉย ๆ 5 นาที แล้วกลับมาพิมพ์ | websocket ยังไม่หลุด (เช็ก `readTimeout` / `idleTimeout`) |
| G4 | มือถือเปิด 5173 (Vite) | ไม่มี "Blocked request", แก้ไฟล์ใน code-server แล้ว HMR อัปเดต, `/api` ผ่าน proxy ได้ |
| G5 | ปิด session | ≤ 10 วิ ลิงก์ได้ 404 |
| G6 | token มั่ว / พอร์ตที่ lab ไม่ได้เปิด | 404 |
| G7 | คาบ online: เครื่อง prelaunch ยังไม่ claim | ไม่อยู่ในตาราง, claim แล้วเปิดได้ทันที |
| G8 | `curl` routes endpoint ไม่มี / ผิด token | 404 |
| G9 | บน router: `nc -zv` master :22 / :6443, worker :22 (ผ่าน tailnet) | ต่อไม่ได้ (ACL) |
| G10 | 30 session เปิด code-server ค้างพร้อมกัน | CPU / RAM ของ router ไม่ชน `MemoryMax`, R2 ยังผ่านระหว่างนั้น, `CPUCreditBalance` ใน CloudWatch ไม่ดิ่ง |
| G11 | `systemctl restart traefik` ระหว่างเปิด code-server | หลุดแล้วต่อใหม่เองภายในไม่กี่วิ |
| G12 | ปิด backend 1 นาที | ลิงก์ที่เปิดอยู่ยังใช้ได้ (traefik ใช้ตารางล่าสุด) — ถ้าไม่ใช่ จดไว้เป็นข้อจำกัด |

## 8. ถอยกลับ

ไล่จากเบาไปหนัก
1. `LAB_GATEWAY_ENABLED=false` (ansible `-e webservice_lab_gateway_enabled=false`) → endpoint กลับเป็น private IP ทันทีสำหรับ session ใหม่
2. `systemctl disable --now traefik cloudflared-lab` บน router
3. ลบ tag `tag:vlab-router` ใน admin console + revert ACL
4. revert terraform (instance type / SG)
5. สุดท้าย: สร้าง router ใหม่จาก AMI ข้อ 3.3 (route ต้อง approve ใหม่)

## 9. ลำดับงาน

| # | งาน | ใคร / ที่ไหน | ขึ้นกับ |
|---|---|---|---|
| 1 | Pete อนุมัติ doc นี้ + ตอบข้อ 10 | Pete | — |
| 2 | เก็บสถานะ router + snapshot (ข้อ 3) | คนที่มีสิทธิ์ AWS | 1 |
| 3 | backend + tests (ข้อ 6) เปิด flag ไว้ `false` | dev | 1 (ทำคู่กับ 2–5 ได้) |
| 4 | terraform: ขยายเครื่อง + SG (ข้อ 4.1) → ทำ 7.1 | Pete | 2 |
| 5 | ติด tag + ACL (ข้อ 4.2) → ทำ 7.1 อีกรอบ | admin tailnet | 4 |
| 6 | Cloudflare tunnel + DNS (ข้อ 4.3) | เจ้าของ zone | 1 |
| 7 | ansible role `lab-gateway` (ข้อ 5) → ทำ 7.1 อีกรอบ | dev | 5, 6 |
| 8 | เปิด flag บน VM แล้วเทส 7.2 | dev + tester | 3, 7 |
| 9 | อัปเดตสถานะ doc นี้ + doc หลัก | dev | 8 |

## 10. คำถามที่ต้องตอบก่อนเริ่ม

1. Pete โอเคให้ router รับ traffic จากอินเทอร์เน็ต (ผ่าน tunnel) ไหม ถ้าไม่ → กลับไปใช้ EC2 ใหม่ตาม doc หลัก
2. ตอนนี้บน router มีอะไรนอกจาก Tailscale อีกไหม (ข้อ 3.2 จะตอบได้)
3. ใครเป็นเจ้าของ account Cloudflare ของ `bell-lab.space` และตั้ง tunnel ใหม่ได้
4. web-service รันที่เครื่องไหน (Tailscale IP) — ต้องใช้ใน ACL และ `lab_gateway_backend_url`
5. ช่วงพอร์ต `3000–9999` พอสำหรับ lab image ที่มีอยู่ไหม
6. ยอมให้ public IP ของ router เปลี่ยนตอนขยายเครื่องได้ไหม (หรือจะผูก Elastic IP ไปด้วยเลย)

## อ้างอิง

- Docker แก้ iptables `FORWARD` policy: https://docs.docker.com/engine/network/packet-filtering-firewalls/
- Traefik HTTP provider: https://doc.traefik.io/traefik/providers/http/
- Traefik entryPoint `respondingTimeouts`: https://doc.traefik.io/traefik/routing/entrypoints/
- Cloudflare Tunnel ingress / wildcard: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/local-management/configuration-file/
- Tailscale tags: https://tailscale.com/kb/1068/tags
- ข้อมูลอื่นดู "อ้างอิงภายนอก" ใน [AWS_LAB_PUBLIC_ACCESS.md](AWS_LAB_PUBLIC_ACCESS.md)
