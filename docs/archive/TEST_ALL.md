# vlab-tui.py — เทส Ansible + launch ทั้งชุดในคำสั่งเดียว (ร่าง ให้ Pete รีวิวก่อนเขียน script)

เขียน 2026-10-20 หลังลง master ใหม่ (ผลอยู่ใน `docs/archive/NextToU.md` หัวข้อ 9)

## ทำไม

ตอนนี้เทสครบชุดต้องพิมพ์คำสั่งเองหลายสิบคำสั่ง (ansible, kubectl, curl, aws, ssh ไป worker) แล้วนั่งดูผลทีละอัน
อยากได้ **คำสั่งเดียว** ที่รันทุกอย่างตามลำดับ แล้ว**สรุปเป็นตาราง ✅ / ❌** ให้เองตอนจบ
ถ้าพังให้บอกว่าพังข้อไหนพร้อมบรรทัด error สั้น ๆ และ**ไม่ทิ้ง pod / EC2 ค้าง**

## วิธีใช้

```bash
./script/vlab-tui.py              # infra + launch (ไม่รัน playbook)
./script/vlab-tui.py ansible      # เฉพาะ Ansible
./script/vlab-tui.py infra        # เฉพาะเช็ก infra (อ่านอย่างเดียว ไม่แตะอะไร)
./script/vlab-tui.py launch       # เฉพาะ launch / terminate
./script/vlab-tui.py all          # ทั้งหมด

SKIP_AWS=1 ./script/vlab-tui.py launch     # ข้ามเทสที่สร้าง EC2 (ไม่เสียเงิน)
```

ค่าตั้งต้นแก้ด้วย env เหมือน `launch-test.sh`: `BACKEND_URL` (ค่าเริ่มต้น `http://100.102.72.39:8000`), `USER_ID`,
`LAB_K8S`, `LAB_AWS`, `LAB_AUTO`, `WORKER` (ค่าเริ่มต้น `vboxuser@100.83.96.97`)
ถ้าไม่ได้ตั้ง `USER_ID` จะถาม backend หา id ของ Sophia จากอีเมลให้เอง (seed ใหม่ id เปลี่ยนทุกครั้ง)

## ทำอะไรบ้าง (ตามลำดับ)

### ขั้น ansible
| # | เทส | วิธี | ผ่านเมื่อ |
|---|---|---|---|
| A1 | syntax | `ansible-playbook --syntax-check` | exit 0 |
| A2 | เข้าเครื่องได้ + sudo | `ansible all:!registry -b -m command -a hostname` | ทุกเครื่องตอบ |
| A3–A5 | playbook master / workers / webservice | `ansible-playbook --limit <กลุ่ม>` ทีละกลุ่ม | `failed=0 unreachable=0` |

A3–A5 แตะเครื่องจริง → **ถามยืนยัน `[y/N]` ก่อนทุกกลุ่ม** (ข้ามได้ด้วย `YES=1`)
log เต็มเก็บไฟล์ ไม่โชว์บนจอ บนจอโชว์แค่ `PLAY RECAP`

### ขั้น infra (อ่านอย่างเดียว)
| # | เทส | ผ่านเมื่อ |
|---|---|---|
| I1 | node | master + worker-pete Ready |
| I2 | SkyPilot NodePort 30880 ยิง 5 ครั้ง | 200 ทุกครั้ง < 0.5s |
| I3 | auth ไม่ใส่รหัส / รหัสผิด / รหัสถูก (ผ่าน NodePort) | 401 / 401 / 200 |
| I4 | memory limit / restart ของ server | 4Gi / 0 |
| I5 | `sky api info` ใน container backend | HEALTHY + user `vlab-backend` |
| I6 | AWS identity ใน backend | `user/Skypilot-IAM` (ไม่ใช่ root) |
| I7 | นาฬิกา master / worker / webservice เทียบเครื่องนี้ | ห่างกันไม่เกิน 30s |
| I8 | backend → master ยิงทุก 1s เป็นเวลา 30s | ไม่หลุดเลย (จับอาการ VM ถูกหยุด) |
| I9 | dashboard ผ่าน Cloudflare | 401 (ถ้า 530 = ❌ tunnel token) |

### ขั้น launch
| # | เทส | ยิงจาก | ผ่านเมื่อ |
|---|---|---|---|
| L1 | K8s | worker-pete (ผ่าน ssh) | `target: kubernetes`, pod ลง worker-pete |
| L2 | isolation | worker-pete / master / webservice | เปิดได้แค่ worker-pete |
| L3 | AUTO จากเครื่องแลป | worker-pete | `target: kubernetes` |
| L4 | AWS | เครื่องนี้ | `target: aws`, EC2 ไม่มี public IP, 8080 / 5173 / 8443 ตอบ |
| L5 | AUTO จากข้างนอก | เครื่องนี้ | `target: aws` |
| L6 | terminate ทุกตัวข้างบน | – | DELETE 200, ไม่มี pod / EC2 ค้าง |

แต่ละข้อ: launch → เช็ก → **ปิดทันที** ก่อนไปข้อถัดไป (ไม่เปิดค้างพร้อมกัน memory ของ server จะได้ไม่ชน)
ระหว่างขั้นนี้เก็บ memory ของ server ทุก 10s เบื้องหลัง → ตอนจบรายงานค่าสูงสุด

## หน้าตาบนจอ — TUI แบบ btop (Pete ขอ 2026-10-20)

เป็น **Python + `rich`** (`script/vlab-tui.py`) — `rich` มีใน python3 ของ ThinkPad และใน venv ของ backend อยู่แล้ว
ไม่ต้องลงอะไรเพิ่ม ข้อมูลทั้งหมดดึงด้วยคำสั่งเดิม (kubectl / curl / ssh / aws) ไม่ import โค้ด backend
หน้าจออัปเดตเองทุก 2s ไม่ต้องกดอะไร กล่องแบ่งแบบนี้:

```
┌ cluster ─────────────────────────┐┌ skypilot server ────────────────────────────┐
│ master       Ready   clock +0s   ││ health  200  0.02s   restart 0               │
│ worker-pete  Ready   clock +1s   ││ mem  2337Mi / 4096Mi  ▁▂▂▃▅▆▅▃▂▂▁  (5 นาที)   │
│ webservice   up      clock -0s ⚠ ││ auth 401/401/200   aws ✅  k8s ✅             │
│ backend→master  ▁▁▁▁▁█▁▁ 1 หลุด  ││ cloudflare  ❌ 530                           │
└──────────────────────────────────┘└──────────────────────────────────────────────┘
┌ tests ───────────────────────────────────────┐┌ ของที่เปิดอยู่ ─────────────────┐
│ ✅ A1 syntax                                  ││ lab pods                        │
│ ✅ A3 webservice      failed=0     2m14s      ││   music-lab-…  worker-pete      │
│ ✅ I3 auth 401/401/200                        ││ sessions (backend)              │
│ ❌ I9 Cloudflare dashboard   530              ││   a0a1eeb2  K8s  running        │
│ ⠹  L4 AWS            01:42                    ││ EC2 running                     │
│ ·  L5 AUTO จากข้างนอก                         ││   i-0821…  10.10.2.74  ⚠ เสียเงิน │
│ ·  L6 terminate                               ││                                 │
└───────────────────────────────────────────────┘└─────────────────────────────────┘
┌ log ──────────────────────────────────────────────────────────────────────────────┐
│ 22:31:05 [auto] Start from outside (100.93.121.17) -> aws                         │
│ 22:31:07 POST /api/sessions  lab AWS ...                                          │
└───────────────────────────────────────────────────────────────────────────────────┘
 a ansible  i infra  l launch  t ทั้งหมด  d ลบของค้างทั้งหมด  q ออก
```

- กล่อง **cluster / skypilot server / ของที่เปิดอยู่** = monitor สด (ทำงานตลอดแม้ไม่ได้รันเทส) ใช้แทน `watch` ได้เลย
- กล่อง **tests** = รายการเทสด้านล่าง กดปุ่ม `a` / `i` / `l` / `t` แล้วรันตามลำดับ ผลขึ้นทีละบรรทัด
- ตอนถามยืนยัน (playbook / ลบของค้าง) ขึ้นกล่องกลางจอ `y / n`
- ใช้แบบไม่มีจอ (เช่น pipe / CI) ได้: `./script/vlab-tui.py --plain infra` พิมพ์ทีละบรรทัดแล้วจบด้วยตารางสรุป
- เก็บ log เต็มที่ `/tmp/vlab-test-<เวลา>/` (บนจอโชว์แค่สรุป)

⚠️ ตอนออก (`q`) ถ้ายังมี session / EC2 ที่ script สร้างค้างอยู่ จะถามก่อนว่าจะลบไหม (ค่าเริ่มต้น = ลบ)

## ความปลอดภัย / ไม่ให้มีของค้าง

- จด session ทุกตัวที่ script สร้าง → `trap` ตอน Ctrl+C / script พัง → DELETE ให้หมด
- จบแล้วเช็ก EC2 ที่มี tag `skypilot-cluster-name` ถ้ายังมี → `sky down` ผ่าน token ให้ (ถ้าไม่สำเร็จ บอกคำสั่ง
  `aws ec2 terminate-instances --profile skypilot` ให้รันเอง) **ไม่ใช้ profile default (root)**
- ไม่พิมพ์ secret ออกจอ / ลง log (รหัส admin, token, key อ่านจาก `group_vars` / `artifacts` ใช้แค่ใน curl)
- ขั้น infra อ่านอย่างเดียว ขั้น ansible ถามก่อน ขั้น launch สร้างแค่ session ของ Sophia แล้วลบ

## ไม่ทำในรอบนี้

- prewarm / warm pod (ต้องสร้างคาบใน DB แล้วรอ scheduler) — ถ้าอยากได้ ทำเป็นขั้น `prewarm` แยกทีหลัง
- โหลดซ้ำ 3 รอบ — ใส่ `ROUNDS=3` ทีหลังได้ถ้าต้องการ

## ไฟล์ที่จะเพิ่ม / แก้

- `script/vlab-tui.py` (ใหม่) — Python 3 + rich ไฟล์เดียว เรียก kubectl / curl / ssh / aws ผ่าน subprocess
- `script/launch-test.sh` เดิมไม่แก้ (ยังใช้ได้เหมือนเดิม)
- `docs/archive/NextToU.md` หัวข้อ 5 — ชี้มาที่ script นี้

## คำถามให้ Pete

1. ขั้น ansible ให้รัน playbook จริง (ถามก่อนทุกกลุ่ม) หรือแค่ A1–A2 พอ?
2. กด `t` (ทั้งหมด) ให้รวมเทสที่สร้าง EC2 (เสียเงินนิดหน่อย ~2 เครื่อง × ไม่กี่นาที) หรือข้ามเป็นค่าเริ่มต้น?
