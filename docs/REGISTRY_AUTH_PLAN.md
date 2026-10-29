# แผน: Camp Registry แยก pull/push + Authentication + Tailscale ACL

แก้ช่องโหว่ข้อ 8.1 ใน `docs/archive/LAB_IMAGE_SCAN_GUIDE.md`: camp registry ไม่มี auth ใครเข้า `:5001` ได้ก็ push image ข้ามการสแกนได้ แล้ว `ecr-sync` จะพาขึ้น ECR ให้ด้วย

สถานะ: Phase 1-2 เสร็จ (รันบน rn ผ่าน 2026-10-29) / Phase 3 deploy แล้ว รอทดสอบสแกนจริงพร้อม Phase 5 / Phase 4 เสร็จ (apply + ตรวจด้วย curl 2026-10-29) / Phase 5-6 ยังไม่เริ่ม

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

### Phase 3: scan Job push แบบมี auth  (เขียนเสร็จ test ผ่าน รอ deploy)
- [x] role `k3s-server` (tag `scan`): Secret `registry-push` แบบ `kubernetes.io/basic-auth` จาก `registry_users.scanner` ใน `vlab-scan`
  apply `--server-side` (ไม่เก็บรหัสซ้ำใน annotation last-applied) เทียบค่าเดิมก่อน apply, `no_log` ค่าใน `roles/k3s-server/defaults/main.yml`
- [x] `k8s/scan-namespace.yaml`: egress ไป `REGISTRY_IP/32` เปิด 5001 และ 5002
- [x] `scan_job_service.py`: mount `registry-push` เฉพาะ container `publish` ที่ `/secrets/push` (0400), `REGISTRY` = `settings.registry_push_host`, `nodeSelector` จาก `SCAN_NODE_SELECTOR`
- [x] `settings.py`: `REGISTRY_PUSH_HOST` (ว่าง = host ของ `DOCKER_REGISTRY_HOST` + `REGISTRY_PUSH_PORT` 5002), `SCAN_PUSH_SECRET`, `SCAN_NODE_SELECTOR` (default `node-role.kubernetes.io/control-plane: "true"`)
- [x] `runner.py` `step_push`: อ่าน `/secrets/push/{username,password}` เขียน authfile 0600 ใน `TMPDIR` ส่ง `--dest-authfile` ลบใน `finally` ไม่มีไฟล์ / รูปแบบผิด = `ERROR` ไม่ retry
- [x] test: `scan-runner/tests/test_push.py` (9 ข้อ) + `tests/lab_image/test_scan_launch.py` (backend ทั้งชุด 533 ผ่าน)
  ยังไม่มี test ของ `evaluate_report` (guide ข้อ 8.2) ทำแยกทีหลัง
- [x] bump runner → `1.1.0` (`runner.py`, `Dockerfile`, role default, `SCAN_RUNNER_VERSION`)
- [x] ลบ `REGISTRY_SCANNER_USER/PASSWORD` ออกจาก `.env` ของ backend (เหลือ `REGISTRY_PUSH_PORT`)
- [x] deploy: rn `--tags scan-runner` (build 1.1.0, `sha256:8565ed4af32ff004e982d3f840211fbea124a85a7bbd99942e23c8003981b2ea`) → mn `--tags scan` (Secret + NetworkPolicy)
  ตรวจบน mn แล้ว: egress มี 5001 + 5002, node มี `control-plane=true`, Secret ไม่มี annotation
- [x] แก้ `changed_when` ของ task apply `scan-namespace.yaml` (หลาย resource: มีตัวเดียว unchanged ก็รายงาน ok ทั้งที่ตัวอื่นเปลี่ยน)
- [ ] ทดสอบสแกนจริง: **เลื่อนไปทำพร้อม Phase 5 หลังตั้ง ACL** (restart backend บน WSL → อัป tar → Pod ลง mn → PASS + digest → `:5001/v2/_catalog`)
  ถ้าไม่ผ่าน: `kubectl -n vlab-scan logs <pod> -c publish` ต่อไม่ติด/timeout = ACL, `unauthorized` = credential
- test DB: `virtual_lab_test` สร้างไว้ใน Postgres ของ WSL แล้ว (conftest ไม่สร้างให้เอง)

### Phase 4: Tailscale ACL  ✅
- [x] `tailscale/vlab-tags.tsv`: mn / wn1 / rn ลบ thinkpad, vlab-web
- [x] `tailscale/vlab-acl.hujson`: worker → server เหลือ `6443` (ลบ 8000 / 5173 / 80 / 443), `8472/udp` เหมือนเดิม, worker → registry `5001` เท่านั้น
  tests: worker deny `registry:5002` / `registry:22` / `server:10250`, server accept `registry:5001,5002`, registry เริ่มคุยกับใครไม่ได้
- [x] `script/tailscale-acl.sh check [node ...]`: อ่าน IP จาก `vlab-tags.tsv`, หาชื่อ node จาก InternalIP, ทดสอบทุก server + worker
  image ทดสอบ = `<registry>:5001/vlab/scan-runner:1.1.0` (มี python3 ต่อ TCP / DNS แทน nc) ไม่ต้องทำ `vlab/acl-probe`
  worker: 6443 open, 10250/22 closed, registry 5001 open / 5002 closed / 22 closed, DNS / server: registry 5001 + 5002 open, worker 10250 open, DNS
- [x] token: หัว script บอกให้ตั้งอายุ 1 วัน
- [x] apply 2026-10-29 (backup `tailscale/backup/acl-20261029-233315.hujson`) policy เดิมแยก 5001/5002 ไว้แล้วและ tag ติดครบอยู่แล้ว
  ที่เปลี่ยนจริง: worker → server เหลือ 6443, เพิ่ม tests ฝั่ง registry / server:10250
  คืนได้: `./script/tailscale-acl.sh rollback tailscale/backup/acl-20261029-233315.hujson`
- [x] ตรวจด้วย curl บนเครื่องจริง (WSL ไม่มี kubectl จึงไม่ได้ใช้ `check`):
  worker → rn:5001 = 200, rn:5002 = timeout, mn:6443 = 401 / master → rn:5002 = 401 / ทั้งสอง node Ready

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
