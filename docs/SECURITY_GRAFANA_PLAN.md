# แท็บ Security ใน Admin → Grafana SIEM ของ Nawapat

สถานะ (2026-10-30): ขึ้นจริงบน cluster บ้าน (master + worker-pete) + VM vlab-web แล้ว — branch `feature/siem-ui`
SIEM (`k8s/siem/**`) เป็นของ Nawapat ตาม PR #129 ทุกตัวอักษร ฝั่งเราทำแค่หน้าเว็บ + ช่องให้ cluster ส่ง / อ่าน log

## 1. ภาพรวม

```
เครื่องใน cluster                     master (control-plane)          VM เว็บ (vlab-web)
L1 Falco + Vector agent ─┐
                         ▼
L2 NATS ─▶ L3 Vector aggregator ──POST /api/v1/logs (X-Collector-Token)──▶ backend :8000 ─▶ Postgres infrastructure_logs
                         │                                                                      ▲
                         ▼                                                                      │ SELECT (grafana_ro)
                    L4 VictoriaLogs ◀── L5 Sigma CronJob (ทุก 2 นาที)      L5 Grafana :30300 ───┘
                                                                              ▲ iframe
                                                         เบราว์เซอร์ admin ── /admin/security
```

- dashboard ทั้ง 2 อัน (`vlab-siem-analytics`, `vlab-siem-5layer`) อ่านจาก Postgres `infrastructure_logs` บน VM
- Grafana ต้องอยู่ที่ control-plane (tag `vlab-server`) เพราะ Tailscale ACL ให้แค่ server เข้า VM :5432 — worker (เครื่องนักศึกษา) เข้าไม่ได้
- Grafana anonymous = Viewer: คนใน tailnet ดูได้โดยไม่ login เว็บ แต่แก้อะไรไม่ได้

## 2. ฝั่งเรา (ไฟล์ของเรา ไม่ใช่ของ Nawapat)

| อะไร | ที่ไหน |
|---|---|
| หน้า `/admin/security` โทนมืด iframe Grafana 2 แท็บ, ปุ่ม Security ในแถบ admin | `frontend/src/pages/SecurityPage.tsx`, `routes/index.tsx`, `components/admin/DashboardHeader.tsx` |
| URL Grafana ตอน build (`VITE_SIEM_GRAFANA_URL`) | `frontend/Dockerfile`, `docker-compose.prod.yml`, ansible `compose.env.j2` |
| token เฉพาะส่ง log `SIEM_COLLECTOR_TOKEN` (≥ 32 ตัว, ≠ `SECRET_KEY`) | `backend/app/routes/monitor_route.py`, `settings.py`, ansible `backend.env.j2` |
| DB publish ที่ Tailscale IP ของ VM เพิ่ม (เฉพาะตอนตั้งรหัส `grafana_ro`) | `docker-compose.prod.yml` (`DB_SIEM_BIND_IP`), ansible `compose.env.j2` |
| user `grafana_ro` = `SELECT infrastructure_logs` อย่างเดียว | ansible `roles/web-service/tasks/main.yml` |
| `POST /api/v1/logs` รับเป็น list + ตัวนับ Falco | โค้ดของ Nawapat จาก #129 (4 ไฟล์ monitor) |

## 3. ตั้งบน cluster ใหม่

1. `ansible/group_vars/all.yml` (gitignored)
   ```yaml
   vault_siem_collector_token: "<สุ่ม ≥ 32 ตัว>"
   vault_siem_grafana_ro_password: "<สุ่ม>"
   siem_grafana_url: "http://<Tailscale IP ของ control-plane>:30300"
   ```
   แล้ว deploy role web-service (backend ได้ token, DB publish Tailscale IP, สร้าง `grafana_ro`, frontend build ด้วย URL Grafana)
2. Tailscale ACL ของ cluster นั้น (`tailscale/vlab-acl.hujson.example`): server → VM :5432 ได้, worker → VM :8000 ได้, worker → VM :5432 **ไม่ได้**
3. Secret (ไม่อยู่ใน git)
   ```bash
   kubectl create ns siem-system
   kubectl -n siem-system create secret generic siem-collector-secrets \
     --from-literal=central-tailscale-endpoint=http://<VM>:8000/api/v1/logs \
     --from-literal=collector-token=<vault_siem_collector_token> \
     --from-literal=postgres-host=<VM>:5432 \
     --from-literal=postgres-user=grafana_ro \
     --from-literal=postgres-password=<vault_siem_grafana_ro_password> \
     --from-literal=grafana-admin-password=<สุ่ม>   # ไม่ใส่ = Grafana ใช้ admin/admin
   ```
4. apply `k8s/siem/` ทีละ layer ตาม `docs/SIEM.md` (L2 → L4 → L3 → L1 → L5)

## 4. ผลเทสบน cluster บ้าน (2026-10-30)

| เทส | ผล |
|---|---|
| ส่ง log มี token = 201 / ไม่มี = 401 | ✅ |
| master → VM :5432 ได้ / worker-pete → VM :5432 ไม่ได้ | ✅ |
| `grafana_ro` อ่านตาราง `users` ไม่ได้ | ✅ |
| `cat /etc/shadow` ใน pod บน worker-pete → `FALCO_SENSITIVE_FILE_READ` ใน DB | ✅ 1 แถว / เหตุการณ์ |
| log `SYSTEM_LOG` ระดับ INFO ไม่เข้า DB | ✅ |
| Sigma แจ้งเหตุละครั้ง (ไม่แจ้งเหตุเก่าซ้ำ) | ✅ |
| Grafana datasource Postgres + VictoriaLogs, รหัส admin จาก Secret | ✅ |
| `/admin/security` เห็นกราฟ | ✅ |

ปัญหาที่เจอระหว่างทางแล้ว Nawapat แก้ใน #129 แล้วทั้งหมด: filter INFO ไม่กรอง, ค่า DB ของ Grafana ตายตัว, Grafana RollingUpdate ค้าง (hostNetwork),
Falco ลง DB ซ้ำ 2 ทาง, Sigma ค้น 14 วันทุกรอบ (แจ้งซ้ำ), fast-track relay ไม่เช็ก token (ลบออก), `${VAR:-default}` ใน Grafana provisioning ได้ค่าว่าง

## 5. ข้อจำกัดที่รู้อยู่
- เบราว์เซอร์ต้องอยู่ใน tailnet ถึงจะเห็นกราฟ (iframe ชี้ Tailscale IP ของ master) และถ้าเว็บเป็น HTTPS ต้องมี HTTPS ให้ Grafana ด้วย (mixed content)
- Grafana ไม่มี volume ถาวร: restart แล้ว admin / ค่าที่แก้ผ่าน UI หาย (dashboard / datasource มาจาก ConfigMap จึงไม่หาย)
- ตัวลบ log เก่า (`INFRASTRUCTURE_LOG_RETENTION_DAYS`, 30 วัน) มากับ backend ของ #129 — ขึ้น VM หลัง #129 เข้า main
