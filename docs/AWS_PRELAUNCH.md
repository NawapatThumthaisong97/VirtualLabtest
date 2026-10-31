# คาบ online: เปิด EC2 รอไว้ให้นักศึกษาทุกคนก่อนคาบ (pre-launch)

> สถานะ: **โค้ดเสร็จบน branch `feature/online-prelaunch` (2026-10-31) รอเทสบน VM** — Pete อนุมัติ doc แล้ว
> ที่มา: tester ถามว่าทำไม AWS ยังรอ ~2 นาที และถ้า launch รอไว้ให้แต่ละ account ก่อนคาบได้ไหม (2026-10-31)

## 1. สรุป

ฟอร์มจองคาบให้อาจารย์เลือกว่าคาบนี้เป็น **on-site** หรือ **online**

| ประเภทคาบ | นักศึกษาอยู่ที่ | ได้เครื่องจาก | เวลารอตอนกด Start |
|---|---|---|---|
| on-site | ห้องแลป | warm pod (DaemonSet) — **มีอยู่แล้ว ไม่แก้** | แทบทันที |
| online | บ้าน / ที่ไหนก็ได้ | **EC2 ที่เปิดรอไว้ให้ account นั้น** (ของใหม่) | < 5 วิ ถ้ากดภายใน 15 นาทีแรก |
| ไม่มีคาบ | ที่ไหนก็ได้ | Sky launch ตอนกด (เหมือนเดิม) | ~1.5–2 นาที |

สองประเภทคาบแยกกันเด็ดขาด คาบ online ไม่ใช้ warm pod / คาบ on-site ไม่เปิด EC2 รอ

กติกาคาบ online (ตกลงกับ Pete 2026-10-31)
- เปิดให้**ทุกคนที่ลงทะเบียนวิชา** (role STUDENT) — use case คือให้ทุกคนได้เรียนครบ
- เปิดล่วงหน้า **10 นาที** ก่อนคาบเริ่ม
- ใครยังไม่กด Start ภายใน **15 นาที** หลังคาบเริ่ม → terminate (`sky down`) เครื่องของคนนั้น
- คนที่ถูก terminate แล้วมากดทีหลัง → Sky launch ปกติ รอ ~1.5–2 นาที (ยังเรียนได้ แค่ช้า)

## 2. ทำไม AWS ยังรอ ~1.5–2 นาที ทั้งที่มี AMI กับ VPC endpoint

เวลาที่วัดได้ ~85–110 วิ (`docs/archive/AWS_LAB_FLOW.md`, `docs/archive/RUN_TARGET_AUTO.md`)

| ขั้น | เวลา | ลดได้ด้วย |
|---|---|---|
| สร้าง EC2 + boot จาก AMI | ~30–40 วิ | ไม่ได้ — เวลาของ AWS เอง |
| SSH ผ่าน Tailscale router → skylet → submit job | ส่วนที่เหลือเกือบทั้งหมด | ไม่ได้ — handshake ของ SkyPilot |
| `docker login` + `docker pull` จาก ECR | ~10 วิ | network (ทำไปแล้ว) |
| backend poll สถานะทุก 5 วิ | 0–5 วิ | — |

- network ใช้ทั้งสองอย่าง ไม่มี NAT (`terraform/network.tf`): **S3 Gateway endpoint** สำหรับ layer ของ image + **EIGW (IPv6)** สำหรับ ECR API แบบ dual-stack
- AMI ที่ bake SkyPilot runtime ไว้ลดจาก ~5 นาที เหลือ ~1.5 นาทีแล้ว (`session_service.py` `_build_aws_task`)
- ส่วนที่เหลือคือ EC2 boot + SkyPilot handshake → **ทางเดียวที่จะเร็วกว่านี้คือเปิดไว้ก่อน** = doc นี้

## 3. ทำไมห้องแลปใช้ DaemonSet ไม่ใช้ Sky launch

- warm pod เปิดรอบนเครื่องของนักศึกษาเองอยู่แล้ว กด Start = แค่ claim (~0.5 วิ)
- Sky launch บน k8s ต้องสร้าง pod + SkyPilot setup ตอนกด ช้ากว่าแม้เครื่องแรง (ช้าที่ handshake ไม่ใช่ CPU)
- warm pod ที่รอเปล่าไม่มีค่าใช้จ่าย เพราะเครื่องในห้องมีไว้ให้นักศึกษาใช้อยู่แล้ว
- คาบ online คือแนวคิดเดียวกับ warm pod (เปิดรอทุกที่นั่ง) ต่างแค่ EC2 คิดเงินเป็นนาที จึงต้องมี X นาทีคืนเครื่อง

## 4. Flow ของคาบ online

```
T-10 นาที   scheduler เห็น slot online → sky launch 1 cluster ต่อนักศึกษา 1 คน
            สร้าง session (status PENDING, prelaunched_at) ผูก user_id + class_slot_id
            launch เสร็จ → RUNNING (ยังไม่มีคน claim)
T0          คาบเริ่ม
T0..T+15    นักศึกษากด Start → เจอ session ที่เปิดรอไว้ของตัวเอง → claimed_at = now
            → ตั้ง autostop ใหม่ตาม lifespan ของ image → ตอบ endpoints ทันที
T+15        scheduler: session ที่ยังไม่ claim → sky down → STOPPED, end_reason PRELAUNCH_UNCLAIMED
หลัง T+15   คนที่มาสายกด Start → Sky launch ปกติ (~1.5–2 นาที)
```

ถ้า launch ของใครพังตอน T-10 → scheduler ลองใหม่รอบถัดไป (ทุก 60 วิ) จนถึง T0
ถ้ายังไม่ได้ คนนั้นกด Start แล้วจะได้ Sky launch ปกติ

## 5. สิ่งที่ต้องแก้

### 5.1 ฟอร์มจองคาบ (frontend + backend)
- เพิ่มช่อง **ประเภทคาบ: on-site / online** ใน `BookingCreate`, `ScheduleForm`, `ScheduleCreate` (`app/schemas/booking_schema.py`) และหน้า `/admin/scheduler` + ฟอร์มขอจองของอาจารย์
- online: ไม่ต้องเลือกห้อง ไม่เช็กห้องชน (ยังเช็กวิชาเดียวกันเวลาทับกัน) จำนวนเครื่อง = จำนวนนักศึกษาที่ลงทะเบียน (แสดงให้เห็น ไม่ให้แก้)
- on-site: เหมือนเดิมทุกอย่าง

### 5.2 Database (migration ใหม่)
- `booking_requests.mode`, `class_schedules.mode` (`onsite` | `online`, default `onsite` → ของเดิมไม่เปลี่ยน)
- `class_slots.run_target` มีอยู่แล้ว: on-site → `KUBERNETES`, online → `AWS` (`generate_slots` คัดลอกจาก schedule)
- `class_slots.room` เป็น NULL ได้อยู่แล้ว
- `sessions.prelaunched_at`, `sessions.claimed_at` (nullable)
- `SessionEndReason` เพิ่ม `PRELAUNCH_UNCLAIMED`

### 5.3 Scheduler (`app/services/prewarm_scheduler.py`)
- เพิ่ม `sync_prelaunch` ทำงานรอบเดียวกับ `sync_prewarm` (ทุก 60 วิ) ใช้ advisory lock เดิม
- slot online ที่ `starts_at - 10 นาที <= now < starts_at`: นักศึกษาที่ยังไม่มี session ของ slot นี้ → launch
- slot online ที่ `now >= starts_at + 15 นาที`: session ที่ `claimed_at IS NULL` → `sky down`
- launch ใช้ `_build_aws_task` เดิม แต่ autostop ตั้งไว้ `10 + 15 + 5 = 30 นาที` เป็นตาข่ายกันตก (ถ้า backend ตาย เครื่องลบตัวเองได้)
- launch ทีละหลายเครื่องพร้อมกัน แต่จำกัด concurrency (ค่าตั้ง `PRELAUNCH_MAX_PARALLEL`) ดูข้อ 7

### 5.4 กด Start (`SessionService.create_session`)
- ก่อนตัดสินว่าจะ launch แบบไหน: ถ้า user มี session ที่ `prelaunched_at` ไม่ว่าง, `claimed_at` ว่าง, ผูกกับ slot online ที่กำลังมีคาบ → claim
  - `claimed_at = now`, เรียก `sky.autostop(cluster, idle_minutes=lifespan)` ให้นับอายุใหม่จากตอน claim
  - ถ้ายัง PENDING (launch ยังไม่เสร็จ) → รอจนเสร็จ แทนที่จะ launch ซ้ำ
- slot online: ไม่สน IP (กดจากเครื่องแลปก็ได้ EC2) ตามกติกา "แยกกันเด็ดขาด"

### 5.5 ค่าตั้ง (`app/configs/settings.py`)
| ชื่อ | ค่า default |
|---|---|
| `PRELAUNCH_ENABLED` | `false` (เปิดบน VM ทีหลัง) |
| `PRELAUNCH_LEAD_MINUTES` | `10` |
| `PRELAUNCH_CLAIM_MINUTES` | `15` |
| `PRELAUNCH_MAX_PARALLEL` | `5` (รอผลเทส) |

## 5.6 ที่ทำจริงต่างจากแผน / เพิ่มจากแผน
- ฝั่งอาจารย์ยังไม่มีฟอร์มขอจองในหน้าเว็บ (มีแค่ API `POST /v1/bookings`) — แก้ฟอร์มของ admin (`CreateEventModal`) ที่เดียว
- ชื่อ cluster ของเครื่องที่ prelaunch ต่อท้าย hex 4 ตัว เพราะเปิดหลายเครื่องในวินาทีเดียว ชื่อเดิม (image + วินาที) จะซ้ำ
  แล้ว sky launch เอา cluster เดิมมาใช้ซ้ำ
- scheduler เปิดเมื่อ `PREWARM_ENABLED` **หรือ** `PRELAUNCH_ENABLED` (คาบ online ไม่ต้องพึ่ง K3s)
- เครื่องที่ยัง PENDING ตอนหมดเวลารับ ยังไม่คืนในรอบนั้น รอรอบถัดไปตอนเป็น RUNNING (กัน thread launch เขียนทับสถานะ)
- กด Start ตอนเครื่องยัง PENDING → รอจน launch เสร็จแล้วรับเครื่องนั้น (ไม่เปิดซ้อน)
- ตั้ง autostop ใหม่ตอนรับเครื่องไม่สำเร็จ → error ให้กดใหม่ (ไม่ claim) เพราะไม่งั้นเครื่องจะลบตัวเองกลางคาบ

## 6. แผนเทส (ทำหลัง Pete อนุมัติ doc + โค้ดเสร็จ)

เทสจาก **ThinkPad** (IP บ้าน ไม่ใช่ worker node) ด้วย 2 account ในวิชาเดียวกัน
ระหว่างเทสลดค่าเวลาลงเพื่อประหยัด: lead 5 นาที, claim 3 นาที

| # | เคส | สิ่งที่ต้องเห็น |
|---|---|---|
| 1 | สร้างคาบ online เริ่มอีก 5 นาที | ครบเวลา lead → EC2 ขึ้น 2 เครื่อง (1 ต่อ account) session RUNNING ยังไม่ claim |
| 2 | account A กด Start ภายใน 3 นาที (claim ทัน) | ได้ endpoints ภายใน < 5 วิ, `claimed_at` ถูกตั้ง, autostop ถูกตั้งใหม่ |
| 3 | account B ไม่กด (claim ไม่ทัน) | ครบ 3 นาที → `sky down`, session STOPPED / PRELAUNCH_UNCLAIMED, EC2 หายจาก AWS console |
| 4 | account B กด Start หลังโดน terminate | Sky launch ปกติ ~1.5–2 นาที |
| 5 | ไม่มีคาบ กดจาก ThinkPad | Sky launch ปกติ (เหมือนเดิม) |
| 6 | คาบ on-site | warm pod เหมือนเดิม ไม่มี EC2 ถูกเปิด |

เก็บกวาดหลังเทส: ปิด session, ลบคาบเทส, เช็ก `sky status` และ EC2 console ว่าไม่มีเครื่องค้าง

## 7. คำถามที่ยังเปิดอยู่

1. **vCPU quota ของ AWS account** — m7i-flex.large ใช้ 2 vCPU/เครื่อง คาบ 40 คน = 80 vCPU ต้องเช็ก quota on-demand ของ ap-southeast-1 (`aws service-quotas`) ก่อนใช้กับคาบจริง
2. **SkyPilot API server รับ launch พร้อมกันได้กี่ตัว** — ต้องวัดจริง แล้วตั้ง `PRELAUNCH_MAX_PARALLEL` ให้ launch ครบทุกคนภายใน 10 นาที
3. **ค่าใช้จ่ายต่อคาบ** = จำนวนคน × (10 + 15) นาทีสำหรับคนไม่มา + เวลาเรียนจริงของคนที่มา — ดูราคาจริงจาก Bill Explorer หลังเทส
4. **คาบ on-site แต่มีคนกดจากบ้าน** → เสนอให้เป็น Sky launch ปกติเหมือนตอนนี้ (ไม่เปิดรอให้)
5. **แจ้งเตือนอาจารย์** ถ้าเปิดไม่ครบตอนคาบเริ่ม (เช่น quota เต็ม) — รอบแรกขึ้นใน log + หน้า admin monitor พอไหม
