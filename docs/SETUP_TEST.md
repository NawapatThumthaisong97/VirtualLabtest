# ตั้งระบบสำหรับเทส จากเครื่องเปล่าจนเปิดหน้าเว็บได้
ไว้สําหรับรันเว็ป ล่าสุด หลังจากโดนขยํ่ามา 500 ครั้ง!
เพราะมันไม่เคยนิ่งมาตลอด เพราะงั้นเราไม่รู้ว่าต้องทําไงนอกจากอาจจะลองลงใหม่ก็ได้นะ
---

## 1. ภาพรวม: ต้องมีเครื่องอะไรบ้าง

```
                         Tailscale (ทุกเครื่องอยู่ใน tailnet เดียวกัน)
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ master       │   │ worker       │   │ registry     │   │ webservice   │
 │ K3s server   │◄──│ K3s agent    │   │ Docker reg.  │   │ backend      │
 │ SkyPilot API │   │ = คอมในห้องแลป │   │ :5001        │   │ frontend, DB │
 └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
        ▲ ansible ทุกเครื่องจาก "เครื่องสั่งงาน" (โน้ตบุ๊กเรา ไม่ต้องเป็น server)
```
เกริ่นก็คือถ้าจะรันเทสก็ต้องแบ่งคอมเป็นส่วนๆแล้วลงโปรแกรมด้วย Ansible

| เครื่อง | ทำอะไร | ของเราตอนนี้ (ใช้ได้จริง) | OS |
|---|---|---|---|
| **master** | K3s control plane + SkyPilot API (สั่ง EC2) | 5 vCPU / 6 GB / ดิสก์ 25 GB | Ubuntu 24.04 |
| **worker** | 1 เครื่อง = คอม 1 เครื่องในห้องแลป รัน pod ของ lab | 4 vCPU / 2 GB / 11 GB (เล็กสุดที่ใช้ได้ แนะนำ 8 GB) | Ubuntu 24.04 |
| **registry** | เก็บ lab image | เครื่องเดิมที่มีอยู่ | Ubuntu |
| **webservice** | หน้าเว็บ + API + Postgres (docker compose) | 3 vCPU / 3 GB / 40 GB (build frontend ต้อง RAM ≥ 2 GB) | Ubuntu 26.04 |
| เครื่องสั่งงาน | รัน ansible / kubectl | โน้ตบุ๊กเรา | อะไรก็ได้ที่มี ansible |

> เครื่องในห้องแลปจริง = worker หลายเครื่อง ติด label ห้อง (`vlab_room: LC-123`) — หน้า `/admin` จัดกลุ่มตามนี้

---

## 2. Setup ใหม่ทีละขั้น

### ขั้น 0 — เครื่องสั่งงาน
```bash
sudo apt install ansible
ansible-galaxy collection install ansible.posix community.docker
ssh-keygen -t ed25519            # ถ้ายังไม่มี แล้ว ssh-copy-id ไปทุกเครื่องในขั้น 1
```

### ขั้น 1 — ทุกเครื่อง: ลง Ubuntu + openssh + Tailscale
```bash
sudo apt install -y openssh-server
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                # login เข้า tailnet เดียวกัน แล้วจด IP: tailscale ip -4
```
- webservice ใส่ `--advertise-tags=tag:vlab-server` (ไม่งั้นต่อ SkyPilot ที่ master ไม่ได้)
- เครื่องใหม่ต้องเพิ่มใน `tailscale/vlab-tags.tsv` แล้วรัน `script/tailscale-acl.sh apply`
- จากเครื่องสั่งงาน: `ssh-copy-id <user>@<tailscale-ip>` ทุกเครื่อง

### ขั้น 2 — inventory (บอก ansible ว่าเครื่องไหนอยู่ไหน)
```bash
cd ansible
cp inventory.yml.example inventory.home.yml     # ไฟล์นี้ไม่เข้า git
```
แก้ IP / user ให้ตรง ตัวอย่างของเรา:
```yaml
all:
  children:
    master:     { hosts: { home-master:  { ansible_host: "100.125.244.48", ansible_user: vboxuser } } }
    workers:    { hosts: { worker-pete:  { ansible_host: "100.83.96.97",   ansible_user: vboxuser, vlab_room: "LC-123" } } }
    registry:   { hosts: { home-registry: { ansible_host: "100.127.74.48" } } }
    webservice: { hosts: { vlab-web:     { ansible_host: "100.102.72.39",  ansible_user: web } } }
```
- รหัส sudo: ใส่ `ansible_become_password: "{{ lookup('file', '~/.ansible/become-<user>') }}"` หรือรันด้วย `-K`
- Ubuntu 26.04 (sudo-rs) ต้องเพิ่ม `ansible_become_exe: sudo.ws`

### ขั้น 3 — ค่าลับ `group_vars/all.yml`
```bash
cp group_vars/all.yml.example group_vars/all.yml    # ไม่เข้า git ห้าม commit
```
| ค่า | เอามาจากไหน |
|---|---|
| `skypilot_aws_access_key_id` / `..._secret_...` | IAM user `Skypilot-IAM` (ขอ เราได้) |
| `skypilot_admin_password` | ตั้งเอง `openssl rand -base64 18` |
| `skypilot_backend_token` | **ขั้น 4 หลังลง master** — dashboard SkyPilot → Users → Service Accounts → สร้าง `vlab-backend` |
| `vault_backend_secret_key` / `vault_admin_session_secret_key` | `python3 -c 'import secrets;print(secrets.token_urlsafe(48))'` |

### ขั้น 4 — รัน ansible ตามลำดับ
```bash
cd ansible
I="-i inventory.home.yml site.yml"
ansible-playbook $I --limit master                  # K3s + SkyPilot API (~10 นาที)
#   → เข้า SkyPilot dashboard สร้าง token vlab-backend ใส่ all.yml (ขั้น 3)
ansible-playbook $I --limit registry
ansible-playbook $I --limit workers                 # join K3s + ติด label ห้อง
ansible-playbook $I --limit webservice -e webservice_seed=true   # ครั้งแรกเท่านั้นที่ seed
```
role `web-service` ตรวจให้เองตอนจบ: API ใช้ DB ได้, ต่อ SkyPilot ได้, **worker เรียก `whoami` แล้วเห็น IP ตัวเอง** (ไม่ผ่าน = deploy fail)

### ขั้น 5 — lab image เข้า registry
```bash
ansible-playbook -i inventory.home.yml build-images.yml -K -e lab_image_filter=music-lab
curl http://<registry-ip>:5001/v2/_catalog          # ต้องเห็น skypilot/music-lab
```

### ขั้น 6 — เช็กว่าใช้ได้
| เปิด | ต้องได้ |
|---|---|
| `http://<webservice-ip>/` | หน้า login |
| `http://<webservice-ip>:8000/health` | `"status":"healthy"` |
| `http://<webservice-ip>:8000/api/v1/whoami` จาก worker | `labMachine` = ชื่อ worker |
| login `admin@dome.tu.ac.th` / `labpass123` | เข้า `/admin` อัตโนมัติ เห็น 5 service ok + ห้องจาก label |
| login `sophia.dav@dome.tu.ac.th` / `sophia6764` | หน้านักศึกษา กด Start lab ได้ |

---

## 3. เทสยังไง

| อยากเทส | ทำแบบนี้ |
|---|---|
| เปิด lab บน**เครื่องแลป** (K3s) | เปิดเว็บแบบ "นั่งที่ worker" — ดูหัวข้อถัดไป |
| เปิด lab บน **AWS** | กดจากเครื่องที่ไม่ใช่ worker  เสียเงินจริง (~$0.12/ชม.) **ปิด lab ทุกครั้ง** แล้วเช็ก `sky status` ว่าไม่มีค้าง |
| ทุกอย่างในคำสั่งเดียว | `./script/vlab-tui.py` (ดู `docs/archive/TEST_ALL.md`) — `SKIP_AWS=1` ข้ามส่วนที่เสียเงิน |
| หน้า admin | `/admin`, API ทั้งหมดที่ `http://<webservice-ip>:8000/docs` |

### เปิดเว็บแบบ "นั่งที่ worker" (Chrome ผ่าน SOCKS)

backend ดูว่ากดจากเครื่องแลปไหนจาก **IP ของคนกด** — ให้ Chrome บนเครื่องเราวิ่งออกทาง worker
backend จะเห็นเป็น IP ของ worker เท่ากับนั่งกดอยู่หน้าเครื่องนั้น (worker ไม่ต้องมีหน้าจอ / desktop)

**Terminal 1** — เปิดทางผ่าน worker ค้างไว้ (ไม่มีอะไรขึ้น = ใช้ได้, ปิดด้วย Ctrl+C):
```bash
ssh -N -D 1080 vboxuser@100.83.96.97        # <user>@<worker-ip>
```

**Terminal 2** — เปิด Chrome ตัวแยก (profile ใหม่ ไม่ปนกับ Chrome ปกติ):
```bash
google-chrome --user-data-dir=/tmp/chrome-lab \
  --proxy-server="socks5://127.0.0.1:1080" \
  http://100.102.72.39
```

**เช็กก่อนกด Start** — ใน Chrome ตัวนั้นเปิด `http://100.102.72.39:8000/api/v1/whoami`
ต้องได้ `"labMachine": "worker-pete"` → login Sophia แล้วกด Start lab จะได้ pod บน worker-pete
(ถ้าได้ `null` = ไม่ได้ออกทาง worker / backend เห็น IP ผิด → กดไปจะไป AWS)

ดูสดว่า backend ตัดสินว่ากดจากไหน (Terminal 3):
```bash
ssh web@100.102.72.39 'docker logs -f virtual_lab_backend 2>&1 | grep --line-buffered "\[auto\]"'
# [auto] Start from lab machine worker-pete -> kubernetes   ← ถูก
# [auto] Start from outside (...) -> aws                    ← ไม่ได้ออกทาง worker
```

- Chrome เปิดอยู่แล้วก็ใช้ได้ `--user-data-dir` บังคับให้เป็นหน้าต่างใหม่ที่ใช้ proxy
- ถ้า worker หลายเครื่อง เปลี่ยน IP ใน Terminal 1 = เปลี่ยนว่านั่งเครื่องไหน
- เสร็จแล้วปิด lab ในหน้าเว็บก่อน แล้วค่อยปิด Chrome / Ctrl+C ที่ Terminal 1

---

## 4. เพื่อนคอมไม่พอ ตั้ง server ไม่ได้ ทำไงดี

ไม่รู้  🥀
---
