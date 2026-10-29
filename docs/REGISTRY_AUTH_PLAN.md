# แผน: Camp Registry แยก pull/push + Authentication + Tailscale ACL

แก้ช่องโหว่ข้อ 8.1 ใน `docs/archive/LAB_IMAGE_SCAN_GUIDE.md`: camp registry ไม่มี auth ใครเข้า `:5001` ได้ก็ push image ข้ามการสแกนได้ แล้ว `ecr-sync` จะพาขึ้น ECR ให้ด้วย

สถานะ: Phase 1-2 เสร็จ (รันบน rn ผ่าน 2026-10-29) / Phase 3-6 ยังไม่เริ่ม

## เครื่องที่มี (ansible/inventory.yml)

| host | Tailscale IP | หน้าที่ | tag |
|---|---|---|---|
| mn | 100.99.154.106 | K3s server | `tag:vlab-server` |
| wn1 | 100.68.15.113 | K3s agent | `tag:vlab-worker` |
| rn | 100.119.124.73 | camp registry, build scanner, ecr-sync | `tag:vlab-registry` |

backend (FastAPI) ตอนนี้รันบน WSL ของเครื่อง Windows ที่ไม่ได้ติด tag (เป็น `autogroup:member`) ไม่มีกลุ่ม `webservice` ใน inventory เครื่อง thinkpad และ vlab-web ถูกเลิกใช้แล้ว

## เป้าหมาย

```
rn: camp-registry-pull :5001  read-only ไม่มี auth   ← worker / master / ecr-sync pull
    camp-registry-push :5002  htpasswd (bcrypt)       ← master (scan Job) / Ansible บน rn push
    ทั้งสองตัวใช้ /srv/camp-registry ร่วมกัน (ตัว pull mount แบบ :ro)
```

- worker pull ได้อย่างเดียว: ACL ให้แค่ `:5001` และตัว 5001 เป็น read-only (กันซ้อนสองชั้น)
- master push ได้แต่ต้องมี user/password
- scan Job ต้องรันบน master เท่านั้น เพราะ traffic ของ Pod ที่ออกนอก cluster ถูก masquerade เป็น IP ของ node ถ้าไปลง worker จะ push ไม่ผ่าน ACL

## การตัดสินใจ (ตกลงแล้ว)

1. **worker → backend :8000 ลบออกจาก ACL** backend อยู่บน WSL ที่ไม่ติด tag ถ้าภายหลังต้องให้ Pod เรียก backend ค่อยติด tag ให้เครื่องนั้น
2. **เครื่องของคนในทีม (`autogroup:member` → `*:*`) คงไว้** ยังเข้า `:5002` ได้แต่ต้องมีรหัส เพราะ Tailscale ACL ไม่มีกฎ deny การตัดพอร์ตเดียวต้องเขียน dst ของ member ใหม่ทั้งหมด (รวม subnet route ของ AWS) เสี่ยงทำทีมเข้าเครื่องไม่ได้
3. **basic auth บน HTTP ธรรมดา** รับได้ เพราะวิ่งใน Tailscale (WireGuard เข้ารหัสแล้ว) ไม่ทำ TLS
4. **credential ของ scan Job อยู่ใน Secret ของ K8s** ที่ Ansible สร้าง backend ไม่ต้องรู้รหัส

## Phases

### Phase 1: role `registry` แบบ 2 พอร์ต + htpasswd  ✅
- [x] `defaults/main.yml`: พอร์ต, image pin เวอร์ชัน, path, `registry_users`
- [x] config ของ registry เป็นไฟล์ (`templates/config-pull.yml.j2`, `config-push.yml.j2`) แทน env
- [x] htpasswd ด้วย `apache2-utils`, ใส่รหัสทาง stdin (ไม่อยู่ใน argv), ตรวจก่อนเขียน (idempotent), ลบ user ที่ไม่อยู่ในรายการ
- [x] ลบ container `camp-registry` ตัวเก่า
- [x] สร้าง container ใหม่เมื่อ config เปลี่ยน (ดูจาก label hash)
- [x] ตรวจหลังรัน: 5001 → 200, 5002 ไม่มี auth → 401, 5002 มี auth → 200, 5001 push ไม่ได้
- [x] รันจริงบน rn: `ansible-playbook -i inventory.yml site.yml -K --limit rn --tags common,registry`
  (ใส่ `--tags` เพราะ role `scan-runner-image` ยังไม่ได้ทำ Phase 2 ถ้ารันทั้ง play จะล้มที่ role นั้น)
- ข้อจำกัด: container bind `0.0.0.0` เครื่องใน LAN เดียวกับ rn เข้า 5001/5002 ได้โดยไม่ผ่าน ACL (5002 ยังต้องมีรหัส) ถ้าจะปิดต้อง bind เฉพาะ IP Tailscale หรือใช้ iptables chain `DOCKER-USER` ทำทีหลัง

### Phase 2: role ที่ build image ต้อง login ก่อน push  ✅
- [x] `scan-runner-image`: เช็ก manifest ผ่าน `localhost:5001` / push ผ่าน `localhost:5002` (`docker login --password-stdin` user `ansible`, `no_log`, `docker logout` ใน `always`), `scan_runner_public_ref` ใช้ 5001 ตัวแปรเดิม `scan_runner_registry_port` เลิกใช้
- [x] `build-images.yml`: push ผ่าน `localhost:5002` (หรือ `<IP>:5002` ถ้า build เครื่องอื่น) + login เหมือนกัน, `insecure-registries` merge กับของเดิมแทนการเขียนทับ, image ที่ SkyPilot ดึงยังเป็น `<IP>:5001/...`
- [x] รัน: `ansible-playbook -i inventory.yml site.yml -K --limit rn` (ครบทั้ง play: registry + scan-runner + ecr-sync, ecr-sync อ่าน `localhost:5001` อยู่แล้ว ไม่ต้องแก้)
  ได้ `SCAN_RUNNER_IMAGE=100.119.124.73:5001/vlab/scan-runner@sha256:da714405a71a5cbe7eeb467d74b01edce47bf15b7d18a0faeb8c47de975b3afc`
- [x] ตรวจ: `curl http://100.119.124.73:5001/v2/_catalog` ต้องมี `vlab/scan-runner`

### Phase 3: scan Job push แบบมี auth
- role `k3s-server`: สร้าง Secret `registry-push` (username/password ของ `registry_users.scanner`) ใน namespace `vlab-scan` (`no_log`)
- `k8s/scan-namespace.yaml`: egress ไป `REGISTRY_IP/32` เปิด 5001 และ 5002
- `scan_job_service.py`: mount `registry-push` เฉพาะ container `publish` ที่ `/secrets/push` (0400), `REGISTRY` = push host, `nodeSelector` control-plane
- `settings.py`: `REGISTRY_PUSH_HOST` (default = host ของ `DOCKER_REGISTRY_HOST` + `:5002`), `SCAN_NODE_SELECTOR`
- `runner.py` `step_push`: อ่าน credential จากไฟล์ เขียน authfile 0600 ใน `/work/tmp` ส่ง `--dest-authfile` ลบทิ้งหลัง push ไม่มีไฟล์ = `ERROR` ไม่ retry
- unit test ของ runner (push credential + `evaluate_report`) และ test ของ backend
- bump `scan_runner_version` → `1.1.0`
- ลบ `REGISTRY_SCANNER_PASSWORD` ออกจาก `.env` ของ backend

### Phase 4: Tailscale ACL
- `tailscale/vlab-tags.tsv`: 3 เครื่องตามตารางข้างบน
- `tailscale/vlab-acl.hujson`: worker → server เหลือ `6443` (+ `8472/udp`), worker → registry `5001` เท่านั้น, tests: worker deny `registry:5002`, server accept `registry:5002`, อัปเดตคอมเมนต์ IP
- `script/tailscale-acl.sh check()`: อ่าน IP/ชื่อเครื่องจาก `vlab-tags.tsv` แทน hardcode, ใช้ image `vlab/acl-probe` (alpine + nc, push ใน `build-images.yml`), probe worker → registry 5001 open / 5002 closed
- token: admin console → Settings → Keys → API access tokens ตั้งอายุ 1 วันให้ revoke เอง

### Phase 5: รันและทดสอบ
```bash
ansible-playbook -i inventory.yml site.yml -K --limit rn                      # registry + scanner + ecr-sync
ansible-playbook -i inventory.yml site.yml -K --limit mn --tags k3s-server    # Secret + NetworkPolicy
./script/tailscale-acl.sh plan && ./script/tailscale-acl.sh apply && ./script/tailscale-acl.sh check wn1
```
- backend บน WSL: อัป tar ทดสอบ → Pod ต้องลง mn → PASS + digest → image โผล่ใน `:5001/v2/_catalog` → ขึ้น ECR
- ทดสอบติดลบ: จาก wn1 push 5001 ต้องได้ error, ต่อ 5002 ต้องไม่ติด

### Phase 6: เอกสาร
- อัปเดต guide ข้อ 5.4, 6.1, 6.2, 8.1

## หมายเหตุ
- `ansible/group_vars/all.yml` (gitignore) มี `registry_users.ecr_sync` ที่ไม่ได้ใช้ (ecr-sync อ่าน 5001 ไม่ต้อง auth) ลบได้
- secret ใน `all.yml` เป็นข้อความธรรมดา ควรย้ายไป `ansible-vault` ภายหลัง
