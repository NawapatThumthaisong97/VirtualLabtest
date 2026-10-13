# Backend tests

```bash
cd web-portal/backend
source venv/bin/activate
pytest                      # ทั้งหมด + ตารางสรุปรายเคส
pytest -k regression        # เฉพาะบั๊กที่เคยเจอ
pytest tests/session/test_reconcile.py
pytest --no-case-table      # ไม่เอาตาราง
```

## ต้องมีอะไร

| กลุ่ม | ไฟล์ | ต้องใช้ |
|---|---|---|
| task builder | `test_task_builder.py` | ไม่ต้องมีอะไร |
| create / delete / reconcile | `test_create_session.py`, `test_delete_session.py`, `test_reconcile.py` | Postgres DB ชื่อ `virtual_lab_test` |

สร้าง DB เทสครั้งเดียว (ใน container `virtual_lab_db`):

```bash
docker exec virtual_lab_db psql -U postgres -c "CREATE DATABASE virtual_lab_test;"
```

- schema ถูกสร้างใหม่จาก model ทุกครั้งที่รัน และทุกเทส rollback ทิ้ง ไม่ต้อง migrate เอง
- ถ้าต่อ DB ไม่ได้ เทสกลุ่มนี้ถูก **skip** (กลุ่ม builder ยังรัน)
- ใช้ DB อื่นได้ด้วย `TEST_DATABASE_URL=postgresql://...` (ชื่อ DB ต้องลงท้ายด้วย `_test`)

## เขียนเทสเพิ่ม

- บรรทัดแรกของ docstring ของ class = **Group**, ของเทส = **Case** ในตาราง (ภาษาอังกฤษ)
- บั๊กที่เคยเจอ ขึ้นต้น Case ด้วย `Regression:`
- ไม่เรียก SkyPilot จริง ใช้ fixture `fake_sky` (`tests/fakes.py`) ตั้งพฤติกรรม เช่น
  `fake_sky.launch_error = RuntimeError(...)`, `fake_sky.job_statuses = ["SETTING_UP", "FAILED_SETUP"]`
  แล้ว assert สิ่งที่ถูกเรียก เช่น `fake_sky.downed`, `fake_sky.status_calls`
- fixture `world` = user / course / lab K3s / lab AWS / lab ไม่มี image, `add_session` = ใส่ session สถานะใดก็ได้
