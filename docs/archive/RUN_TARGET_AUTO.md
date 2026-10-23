# run_target = AUTO — เลือก K8s / AWS ตามเครื่องที่กด Start

สถานะ: **ทำแล้ว** (2026-10-20) — **2026-10-21 แทนด้วยกฎเดียวทุก lab** (เครื่องแลป → pod ตรง / warm, ที่อื่น → EC2 ไม่ดู labs.run_target) ดู `docs/archive/LAB_DIRECT_POD.md` — ผลอยู่หัวข้อท้ายสุด

## ทำไม
ตอนนี้ lab ไป K8s หรือ AWS ตาม `labs.run_target` ที่อาจารย์ตั้งราย lab (PR #88) ไม่ดูว่าใครกดจากไหน
- lab AWS แต่นักศึกษานั่งเครื่องแลป → ไป EC2 เสียเงิน ทั้งที่เครื่องตรงหน้าว่าง
- lab K8s แต่กดจากบ้าน → ได้ pod บน cluster แบบไม่ pin เครื่อง ไม่ติด label isolation และแย่งเครื่องในห้องแลป

ที่ต้องการ: **กดจากเครื่อง worker ในห้องแลป → K8s (warm pod / pin เครื่องนั้น), กดจากที่อื่น → burst ไป AWS**

## แบบ
| `labs.run_target` | กดจากเครื่อง worker | กดจากที่อื่น |
|---|---|---|
| `KUBERNETES` (เดิม) | K8s + warm pod / pin | K8s ไม่ pin (เหมือนเดิม) |
| `AWS` (เดิม) | AWS | AWS |
| **`AUTO`** (ใหม่) | **K8s + warm pod / pin** | **AWS** |

"เครื่อง worker" = IP ของ connection ตรงกับ InternalIP ของ node ที่ไม่ใช่ control-plane และ Ready
(ของเดิม `WarmPodService.node_for_ip` ผ่าน `SessionService._client_node`) — master / ThinkPad ที่ไม่ใช่ node / บ้าน = ที่อื่น
endpoint ของคนข้างนอก = private IP บน AWS (`10.10.2.x`) เปิดได้ผ่าน Tailscale router (ต้องอยู่ใน tailnet)
ทางเข้าแบบ Cloudflare / public เป็นงานแยก (เพื่อนทำ)

## แก้อะไร
1. `app/models/lab.py`: `RunTarget.AUTO = "auto"` + docstring
2. `app/services/session_service.py`
   - ฟังก์ชันล้วน `resolve_run_target(lab_target, client_node) -> RunTarget` (KUBERNETES / AWS ตามตาราง)
   - `create_session`: lab เป็น AUTO → หา node ของคนกด**เสมอ** (เดิมหาเฉพาะตอนเปิด WARM_POD / LAB_ISOLATION)
     แล้วใช้ target ที่ resolve แล้วต่อตามเส้นเดิมทั้งหมด (warm pod → task builder → ECR token → is_cloud)
   - log ว่า AUTO เลือกอะไรเพราะอะไร
3. `app/services/prewarm_scheduler.py`: `active_slots` นับคาบที่ `run_target` เป็น `KUBERNETES` **หรือ `AUTO`**
   (นักศึกษาในห้องแลปจะใช้ K8s ต้องมี pre-pull / warm pod)
4. response ของ `POST /api/sessions` เพิ่ม `run_target` ที่ใช้จริง (`kubernetes` / `aws`) ให้เห็นว่า AUTO เลือกอะไร
5. `LabCreateRequest` / `LabUpdateRequest` รับ `run_target` (optional) → ตั้ง AUTO / AWS ผ่าน API ได้ ไม่ต้องแก้ DB เอง
   (lab AWS สำหรับเทสก็สร้างผ่าน API ได้)
6. DB: `ALTER TYPE runtarget ADD VALUE 'AUTO';` (ไม่กระทบ row เดิม) จดใน `docs/archive/DB_DIAGRAM.md` แบบที่ทำกับ PR #88
   ถอย: ตั้ง lab ที่เป็น AUTO กลับเป็นค่าเดิม (Postgres ลบค่าออกจาก enum ไม่ได้ ค่าค้างไว้เฉย ๆ ไม่มีผล)

## ที่ตัดสินแล้ว
- **AUTO แล้วเช็ก node ไม่ได้ (ต่อ K8s ไม่ได้)** → **ไป AWS** (เปิด lab ได้ดีกว่าเปิดไม่ได้)
- `run_target` เก็บไว้เป็นข้อยกเว้นราย lab (KUBERNETES = ห้ามออก cloud / image ยังไม่มีใน ECR, AWS = หนักเกินเครื่องแลป)
- pin เครื่องยังขึ้นกับ `LAB_ISOLATION_ENABLED` เหมือนเดิม (AUTO รู้ว่าเป็นเครื่องแลปเสมอ แต่ pin / label เฉพาะตอนเปิด isolation)
- **กดจากเครื่องแลปแต่เครื่องนั้นเต็ม** → ตอนนี้ไม่ทำอะไรพิเศษ (SkyPilot รอจนหมด timeout แล้ว error เหมือนเดิม)
  การ fallback K8s → AWS อัตโนมัติ (resources แบบ `ordered`) แยกเป็นงานถัดไป

## เทส
unit (FakeSky ไม่ launch จริง)
| เคส | คาด |
|---|---|
| `resolve_run_target` ทุกคู่ในตาราง | ตามตาราง |
| lab AUTO + client_ip = worker | task infra kubernetes, pin node + label, is_cloud false |
| lab AUTO + client_ip = worker + มี warm pod ว่าง | launch_mode warm_pod |
| lab AUTO + client_ip ไม่ใช่ worker / ไม่มี | task infra aws, ECR token, is_cloud true |
| lab AUTO + K8s ต่อไม่ได้ | ตามที่ Pete เลือก |
| lab KUBERNETES / AWS | เหมือนเดิม (เทสเดิมต้องผ่านทั้งหมด) |
| prewarm: คาบ AUTO | ถูกนับ ได้ DaemonSet + warm pod |

ของจริง (ด้วย `script/launch-test.sh` ที่ยิงแค่ curl — IP ของคนกด = เครื่องที่รัน script)
| ยิงจาก | `BACKEND_URL` | คาด |
|---|---|---|
| ThinkPad (เป็น node `thinkpad`) | `http://100.93.121.17:8000` (Tailscale IP) | K8s ลง thinkpad |
| worker-pete | copy script ไปรัน หรือ pod hostNetwork | K8s / warm pod บน worker-pete |
| master (control-plane ไม่นับเป็นเครื่องแลป) | `http://100.93.121.17:8000` | AWS, เปิด IDE จาก ThinkPad ผ่าน router ได้ |
| ThinkPad ผ่าน `127.0.0.1` | `http://127.0.0.1:8000` | AWS (ไม่ใช่ IP ของ node) |

## ลำดับงาน
1. Pete อนุมัติ doc นี้ + `docs/archive/LAUNCH_CONSOLE.md` (launch-test.sh)
2. branch ใหม่จาก `feature/skypilot-central`: backend + เทส → `ALTER TYPE` บน DB dev → เทสของจริง
3. `script/launch-test.sh` เมนู Start lab ให้เลือก lab K8s / AWS / AUTO

## ผล (2026-10-20)

| เทส | ผล |
|---|---|
| unit test (resolve ทุกคู่, AUTO จากเครื่องแลป → K8s pin / warm pod, จากที่อื่น / ไม่มี IP → AWS + ECR token, K8s ต่อไม่ได้ → AWS, ปิด WARM_POD/ISOLATION ก็ยังรู้ว่าเป็นเครื่องแลป, คาบ AUTO ถูก prewarm, PATCH run_target) | ✅ 161/161 |
| DB dev: `ALTER TYPE runtarget ADD VALUE 'AUTO'` + lab "OOP with Spring Boot (AUTO)" (`035a1861-…`) | ✅ |
| ของจริง ผ่าน `script/launch-test.sh` เมนู 3: กดจาก `127.0.0.1` | ✅ log `[auto] Start from outside (127.0.0.1) -> aws` → EC2 110s, ลบ 9s |
| ของจริง: กดจาก ThinkPad ผ่าน Tailscale IP (`BACKEND_URL=http://100.93.121.17:8000`) | ✅ log `[auto] Start from lab machine thinkpad -> kubernetes` → pod บน thinkpad 201s, ลบ 9s |

ก่อนหน้านี้ launch ทุกแบบพังเพราะ SkyPilot API server ชนลิมิตหน่วยความจำ 2Gi (ดู `docs/archive/SKYPILOT_CENTRAL_SERVER.md` หัวข้อ 9)
ขยายเป็น requests 2Gi / limits 4Gi แล้วผ่าน — peak ระหว่างเทส 2048Mi (เท่าลิมิตเก่าพอดี)
