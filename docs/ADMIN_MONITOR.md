# Admin Monitor — แผน API หน้า overview + ระบบจองห้อง (ร่าง ให้ Pete รีวิวก่อนเขียนโค้ด)

เขียน 2026-10-23 หลังรีวิว PR #98 (monitor / billing / SIEM ของ Nawapat) แล้วพบว่าข้อมูลส่วนใหญ่เป็นค่าตายตัว
UI อ้างอิง: `Design system introduction.zip` (`dashboard-src/`) preview อยู่ที่ `http://100.102.72.39:8090/`
UI ยังไม่ครบ Pete จะเพิ่มเองตาม feature — เอกสารนี้กำหนดเฉพาะ **API + แหล่งข้อมูล**

## ทำไมไม่แก้ต่อจาก PR #98

| ของเดิม | ทำอะไรกับมัน | เหตุผล |
|---|---|---|
| permission RBAC `monitoring:read:all`, `billing:read:global` | ใช้ต่อ | ใช้ได้เลย |
| `LogMaskerService` (mask PII, anon_id) | ใช้ต่อ | ออกแบบดี |
| ตาราง `infrastructure_logs` | ใช้ต่อ | เปลี่ยนแค่คนเขียนข้อมูลลง |
| `GET /metrics`, `/security-counters`, `/logs` | ลบหลังหน้าใหม่ใช้ได้ | รูป JSON ไม่ตรงการ์ด, ค่าปลอม (42/15/7, log ตัวอย่าง 6 อัน, AWS 128 CPU, วง NAT 192.168.x) |
| `/billings*` + export | ลบ | ไม่มีใครเขียน `usage_records`, ไม่มี budget |
| role `siem-log-forwarding` (Fluent Bit) | พักไว้ | ส่งเป็น array → endpoint รับ object (422), ไม่มี Squid / Kyverno ใน cluster, group `webportal` ไม่ตรง inventory บ้าน |
| `siem_ingest_token` ใน `ansible/roles/siem-log-forwarding/defaults/main.yml` | **ลบ + เปลี่ยน `SECRET_KEY` บน prod** | JWT admin หมดอายุปี 2107 อยู่ใน git |

endpoint ใหม่ทั้งหมดอยู่ใต้ `/api/v1/admin/*` ต้องมี role admin ยกเว้น `POST /api/v1/bookings` (อาจารย์)

## สิ่งที่ตัดสินใจแล้ว (Pete 2026-10-23)

| เรื่อง | ตัดสินใจ |
|---|---|
| ห้อง | นับเป็น **จำนวนคอมจริง** ในห้อง, **คอม 1 เครื่อง = 1 worker node** (ปกติ ~50 ห้อง ตอนนี้มี worker-pete ตัวเดียว → สมมติเป็นห้อง `LC-123`) |
| cluster | ตอนนี้ k3s 1 cluster (master ตัวเดียว) + AWS |
| ค่า AWS | (ก) ประมาณจาก ชั่วโมงที่รัน × ราคา instance ก่อน แล้ว (ข) กระทบยอดกับ Cost Explorer วันละครั้ง — บัญชีรวม **ต้อง filter ด้วย tag** |
| on-prem | แสดง **ชั่วโมงอย่างเดียว** + สัดส่วนเทียบ AWS ไม่คิดค่าไฟ |
| budget AWS เกิน | แจ้งเตือน (log + เมล admin) และมี **API เปิด/ปิด burst** ไม่ต้องมี UI |
| เมล | Gmail SMTP |
| Azure ใน UI | ตัดออก (ไม่ได้ใช้) |

## ข้อมูลพื้นฐานที่ต้องเพิ่มก่อน

1. **ห้อง = label บน node** `vlab/room=LC2-123` ใส่ผ่าน ansible (inventory ต่อ host: `vlab_room: LC2-123`)
   - **คอม 1 เครื่องในห้อง = 1 worker node** ⇒ `pcsTotal` = จำนวน node ที่ label ห้องนั้น,
     `pcsInUse` = node ที่มี session RUNNING อยู่ ≥ 1 ตัว
   - node ที่ไม่มี label → กลุ่ม `unassigned` (เช่น master, worker-pete ตอนนี้)
   - ตาราง `rooms` (id, name, building, note) มีไว้แสดงชื่อ/ใช้ตอนจอง ส่วนจำนวนเครื่องนับสดจาก k8s
2. **`sessions.class_slot_id`** — ตอนสร้าง session ใส่ slot ของวิชานั้นที่ `starts_at <= now < ends_at` (ตอนนี้ไม่มีใครใส่)
3. **`usage_records`** — เขียนตอน session จบ (ทุก end_reason): `cpu_seconds` = ชั่วโมงที่รัน × CPU ที่ขอ,
   `is_cloud_burst`, `est_cost_thb` → เปลี่ยนเป็น `est_cost_usd` (on-prem = 0)
4. **ตาราง `health_checks`** (service, status, latency_ms, checked_at) — job ใน backend ping ทุก 5 นาที เก็บ 7 วัน
5. **settings**: `AWS_MONTHLY_BUDGET_USD=200`, `AWS_HOURLY_PRICE_USD` (ของ `AWS_INSTANCE_TYPE`),
   `AWS_BUDGET_ALERT_PCT=80`, `SMTP_HOST/PORT/USER/PASSWORD`, `MAIL_FROM="Virtual Lab Team <...>"`
6. **ตาราง `cloud_controls`** (1 แถว): `burst_enabled`, `changed_by`, `changed_at`, `reason` — session launch เช็กก่อนขึ้น AWS

## การ์ดใน overview → endpoint → JSON

### 1. Header stats
```
GET /admin/overview/stats
{ "activeSessions": 42, "runningCourses": 3, "pendingBookings": 2, "openIncidents": 1 }
```
`openIncidents` = log ระดับ ERROR+ ใน 24 ชม. ที่ยังไม่ acknowledge (ถ้าไม่ทำ ack ก็นับ 24 ชม.)

### 2. System status (SystemTable)
```
GET /admin/system/status
{
  "checkedAt": "2026-10-23T17:00:00+07:00",
  "services": [
    { "key": "backend",  "name": "FastAPI Server", "version": "1.6.8",
      "status": "ok",    "latencyMs": 80, "hourly": ["ok", "ok", "down", "..."] }
  ]
}
```
| key | เช็กยังไง |
|---|---|
| `backend` | ตัวเอง + `SELECT 1` DB |
| `k8s` | `GET /version` ของ k8s API (version มาจากตรงนี้) |
| `registry` | `GET http://<registry>/v2/` |
| `skypilot` | `sky api status` / health endpoint |
| `aws` | `sts:GetCallerIdentity` |

`hourly` = 24 ช่องย้อนหลัง ช่องละ status แย่สุดในชั่วโมงนั้น (`ok` / `degraded` / `down` / `nodata`)

### 3. Infra map (InfraMap)
```
GET /admin/infra/map
{
  "clusters": [
    { "id": "k3s-main", "type": "k3s", "status": "ok",
      "controlPlane": { "node": "master", "ready": true },
      "rooms": [
        { "room": "LC2-123", "status": "ok", "pcsTotal": 30, "pcsReady": 29, "pcsInUse": 28 },
        { "room": "unassigned", "status": "warn", "pcsTotal": 1, "pcsReady": 0, "pcsInUse": 0 }
      ] },
    { "id": "aws", "type": "cloud", "status": "ok", "region": "ap-southeast-1",
      "instancesRunning": 2, "burstEnabled": true }
  ]
}
```
ตอนนี้มี 1 cluster k3s (master ตัวเดียว) + AWS แต่ `clusters` เป็น array ไว้ก่อน
ห้อง status: `down` = ไม่มี node Ready, `warn` = Ready ไม่ครบ, `ok` = ครบ

### 4. Room usage + resources (InfraVisualizer)
```
GET /admin/rooms/usage
{
  "rooms": [
    { "room": "LC2-123", "pcsInUse": 28, "pcsTotal": 30, "state": "launched",
      "slot": { "course": "Software Engineering", "startsAt": "2026-10-23T13:00:00+07:00",
                "endsAt": "2026-10-23T16:00:00+07:00", "status": "running" } }
  ],
  "resources": [
    { "name": "Docker registry", "reachable": true, "latencyMs": 20, "level": "good" }
  ]
}
```
`state`: `launched` (มีคาบ + มีคนใช้), `queue` (มีคาบ ยังไม่มีคนใช้ / prewarm อยู่), `idle` (ไม่มีคาบ)
`resources` ใช้ผลล่าสุดจาก `health_checks` (registry, k8s API, worker แต่ละห้อง)

### 5. Billing (BillingEstimate + BillingUsage)
```
GET /admin/billing/summary?month=2026-10
{
  "month": "2026-10",
  "aws":    { "budgetUsd": 200, "usedUsd": 63.4, "forecastUsd": 140, "usedPct": 31.7,
              "source": "estimate", "reconciledAt": "2026-10-22T02:00:00Z",
              "instancesRunning": 2, "sessionHours": 120 },
  "onPrem": { "sessionHours": 812 },
  "share":  { "onPremPct": 87.1, "awsPct": 12.9 },
  "daysRemaining": 8, "daysTotal": 31
}

GET /admin/billing/monthly?from=2026-05&to=2026-10
{ "months": [ { "month": "2026-10", "onPremHours": 812, "awsHours": 120, "awsUsd": 63.4 } ] }
```
- `usedUsd` = ยอด Cost Explorer ถึงเมื่อวาน (ถ้ามี) + estimate ของวันนี้ ⇒ `source` = `estimate` / `mixed`
- `forecastUsd` = used / วันที่ผ่าน × วันทั้งเดือน (เส้นตรงพอ)
- `share` คิดจาก**ชั่วโมง** ไม่ใช่เงิน
- job กระทบยอดวันละครั้ง (`ce:GetCostAndUsage` filter tag ของ SkyPilot ถ้ามี ไม่งั้นทั้งบัญชี) ค่าเรียก $0.01/ครั้ง

### 6. Budget + ปิด burst (API อย่างเดียว)
```
GET   /admin/cloud/controls          { "burstEnabled": true, "changedBy": "...", "changedAt": "...", "reason": null }
PATCH /admin/cloud/controls          { "burstEnabled": false, "reason": "เกิน budget ต.ค." }
```
- ถึง `AWS_BUDGET_ALERT_PCT` (80%) และ 100% → เขียน log `BUDGET_ALERT` + เมล admin (ครั้งเดียวต่อเกณฑ์ต่อเดือน)
- **ไม่ปิดเอง** — admin ตัดสินใจผ่าน PATCH
- `burstEnabled=false` → lab ที่ `run_target=AWS` ได้ 409 พร้อมข้อความ, lab `AUTO` ไม่ขึ้น cloud (รอคิว / แจ้งเต็ม)

### 7. Log Explorer
ใช้ตาราง `infrastructure_logs` เดิม + `LogMaskerService` แต่คนเขียน log เปลี่ยนเป็นแหล่งที่มีจริง:

| type | source | มาจาก |
|---|---|---|
| `SESSION_FAILED` | cluster / cloud | session จบด้วย LAUNCH_FAILED / LOST / STALE_PENDING |
| `NODE_NOT_READY` | cluster | health job เห็น node Ready=False (เขียนตอนเปลี่ยนสถานะ ไม่ใช่ทุกรอบ) |
| `POD_EVENT` | cluster | k8s Events ของ namespace lab: OOMKilled, ImagePullBackOff, Evicted, FailedScheduling |
| `CLOUD_LAUNCH_FAILED` | cloud | SkyPilot launch ไม่สำเร็จ |
| `HEALTH_DOWN` | cluster / cloud | service ใน `health_checks` เปลี่ยนเป็น down |
| `BUDGET_ALERT` | cloud | ข้อ 6 |
| `BURST_TOGGLED` | cloud | มีคน PATCH controls |

```
GET /admin/logs/histogram?source=cluster&from=2026-10-21&to=2026-10-23&bucket=1h
{ "buckets": [ { "t": "2026-10-23T09:00:00+07:00", "count": 12 } ],
  "byType": { "SESSION_FAILED": 4, "POD_EVENT": 8 } }

GET /admin/logs?source=&type=&severity=&from=&to=&limit=50&offset=0
{ "items": [ { "id": "...", "t": "...", "severity": "ERROR", "type": "POD_EVENT", "source": "cluster",
               "room": "LC2-123", "node": "lc2-123-pc05", "message": "...", "anonId": "..." } ],
  "total": 37 }
```

## ระบบจองห้อง (API อย่างเดียว ยังไม่มี UI)

```
อาจารย์ ──POST /bookings──▶ pending ──admin approve──▶ approved ──▶ class_schedule + class_slots ──▶ prewarm DaemonSet
                                     └─admin reject──▶ rejected        └──▶ เมลแจ้งอาจารย์ "Virtual Lab Team จองให้แล้ว"
```

ตาราง `booking_requests`: id, requested_by, course_id, lab_image_id, preferred_room_id, weekday, start_time, end_time,
valid_from, valid_until, pcs_needed, note, status (`pending` / `approved` / `rejected` / `cancelled`),
room_id, decided_by, decided_at, decision_note, class_schedule_id, mail_status (`pending` / `sent` / `failed`)

```
POST /bookings                              (อาจารย์)  สร้าง request
GET  /bookings/mine                         (อาจารย์)  ดูของตัวเอง
GET  /admin/bookings?status=pending&month=2026-11
POST /admin/bookings/{id}/approve           { "roomId": "LC2-123", "note": "" }
POST /admin/bookings/{id}/reject            { "reason": "ห้องเต็ม" }
GET  /admin/rooms/calendar?month=2026-11    ทุก slot ของเดือน แยกห้อง (ใช้ดูว่าว่างไหม)
```

- approve: transaction เดียว → สร้าง `class_schedule` (+ `room_id`) → `schedule_service.generate_slots` → commit → ส่งเมลเป็น background task
- **กันห้องชน**: เพิ่ม `room_id` ใน `class_slots` + exclusion constraint `(room_id =, tstzrange &&)`
  (ตอนนี้ `ex_class_slots_no_overlap` กันแค่วิชาเดียวกัน) ชน → 409 พร้อม slot ที่ชน
- `pcs_needed` > `pcsTotal` ของห้อง → 422
- เมลส่งไม่ผ่าน → `mail_status=failed`, ไม่ rollback การจอง, มี `POST /admin/bookings/{id}/resend-mail`
- Gmail: บัญชีที่เปิด 2FA + App Password, `smtp.gmail.com:587` STARTTLS (ส่งได้ราว 500 ฉบับ/วัน พอ)

## ลำดับทำ (PR เล็ก ทีละข้อ แต่ละ PR เทสกับ cluster จริงก่อน)

| # | PR | ต้องมีของจริงอะไร |
|---|---|---|
| 1 | label ห้อง (ansible) + `class_slot_id` + `/admin/infra/map`, `/admin/rooms/usage` | master + worker อย่างน้อย 1 ตัว ติด label |
| 2 | `health_checks` job + `/admin/system/status` + log `HEALTH_DOWN`, `NODE_NOT_READY` | master, worker, registry, SkyPilot API |
| 3 | `usage_records` + `/admin/billing/*` + budget alert + `/admin/cloud/controls` | AWS credential, launch AWS 1 ครั้ง |
| 4 | Cost Explorer reconcile | IAM `ce:GetCostAndUsage` |
| 5 | log จาก k8s Events / session / SkyPilot + `/admin/logs*` | cluster จริง (ทำให้ pod OOM / pull fail ดู) |
| 6 | booking + rooms + SMTP | Gmail App Password |
| 7 | ลบ API เก่าของ PR #98 + พัก role Fluent Bit | — |

## ตอบแล้ว (2026-10-23)

1. คอม 1 เครื่อง = 1 worker node
2. ห้องจริงยังไม่มี worker — ใช้ worker-pete เป็น `LC-123` ไปก่อน ห้องที่ยังไม่มี worker ไม่โผล่ใน map
3. AWS เป็นบัญชีรวม → PR 4 ต้องให้ EC2 ที่ SkyPilot เปิดมี tag (เช่น `vlab=true`) แล้ว filter Cost Explorer ด้วย tag นั้น
   (ต้องเปิด tag เป็น cost allocation tag ใน Billing console ก่อน และยอดย้อนหลังก่อนเปิดจะไม่มี tag)

ทุก PR ต้องเทสกับเครื่องจริง (webservice + master + worker-pete) ก่อนเปิด PR และแนบผลเป็นตาราง
