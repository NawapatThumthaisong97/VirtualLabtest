# Comprehensive Architecture Guide: SIEM Log Forwarding, Boundary Monitoring & Zero-Trust Control Plane

เอกสารสรุปเชิงสถาปัตยกรรมและการตัดสินใจทางวิศวกรรม (Engineering Decision Records & Architectural Layers) สำหรับระบบ Virtual Lab

---

## 1. ภาพรวมสถาปัตยกรรมแบบแบ่งเลเยอร์ (Architectural Layers)

ระบบรักษาความปลอดภัยและการติดตามพฤติกรรม (Telemetry) ถูกแบ่งออกเป็น 4 เลเยอร์หลักตามหลักการ **Plane Separation & Least Privilege**:

```
+------------------------------------------------------------------------+
|  Layer 4: Presentation Layer (Admin Monitor & Billing Dashboard)       |
|  - Real-time Violation Counters, Subnet Topologies, Log Drawer         |
+------------------------------------------------------------------------+
                                   ▲
                                   │  HTTP / HTTPS REST + JWT RBAC
+------------------------------------------------------------------------+
|  Layer 3: Control Plane & Data Governance (FastAPI Backend)            |
|  - Ingestion API (X-Collector-Secret / RBAC Protection)                |
|  - Data Normalization & Sanitization Pipeline                          |
|  - Deterministic HMAC-SHA256 PII Pseudonymization Engine               |
+------------------------------------------------------------------------+
                                   ▲
                                   │  Encrypted Overlay Mesh (Tailscale)
+------------------------------------------------------------------------+
|  Layer 2: Transport & Collection Layer (Ansible + Fluent Bit)          |
|  - Fluent Bit Daemon with SQLite Buffer                                |
|  - Lua Event Normalizer & Tag Rewriter (transform_siem.lua)            |
|  - Zero Trust Plane Separation (Forbid Pod Log Mount)                  |
+------------------------------------------------------------------------+
                                   ▲
                                   │  Kernel / Daemons / Access Logs
+------------------------------------------------------------------------+
|  Layer 1: Node & Boundary Enforcement Layer (VM / K8s / Cloud)         |
|  - Egress Proxy: Squid (/var/log/squid/access.log)                     |
|  - Policy Engine: Kyverno (/var/log/kyverno/audit.log)                 |
|  - Network Mesh: Tailscale ACLs (/var/log/tailscale/acl.log)           |
|  - Host Kernel: Systemd Journal (OOM-Killer, Panic, Segfault)          |
+------------------------------------------------------------------------+
```

---

## 2. เจาะลึกการตัดสินใจแต่ละ Layer (Deep Dive: Why, Trade-offs & Alternatives)

### 🔹 Layer 1: Node & Boundary Enforcement Layer (จุดเกิดเหตุ)
**หน้าที่:** สกัดกั้นและบันทึกเหตุการณ์ผิดปกติที่ขอบเขตของระบบ (Perimeter & Host Guardrails)

* **ทำไมต้องดักจับ 4 แหล่งนี้?**
  1. `Squid Proxy`: สกัดกั้นการออกนอกเครือข่ายเถื่อน (Egress Drop: บิตคอยน์, C2, โดเมนภายนอก)
  2. `Kyverno`: สกัดกั้นการยกระดับสิทธิ์ในคลัสเตอร์ (Privilege Escalation, HostPath Mount)
  3. `Tailscale ACL`: สกัดกั้นการพยายามเจาะข้ามวง Subnet ระหว่างห้องแลป
  4. `Systemd Journal`: เฝ้าระวัง Kernel OOM-Killer เมื่อนักศึกษารันโค้ดกิน Memory เกินโควต้า
* **กฎเหล็ก (Plane Separation):** สั่งบล็อกการเข้าถึงพาธ `/var/log/pods/*/*/*.log` เด็ดขาด เพื่อคุ้มครองความเป็นส่วนตัว ไม่ส่องโค้ดหรือ Output งานของนักศึกษา
* **Trade-off & Alternatives:**
  - *ทำไมไม่ใช้ eBPF / Falco?* 
    - **ข้อดีของ eBPF:** จับ System Call ได้ลึกถึงระดับ Kernel
    - **เหตุผลที่ไม่เลือก:** Overhead สูงเกินไปสำหรับเครื่อง Lab VM สเปกจำกัด และ Kernel ของ Node มีความหลากหลาย ทำให้ eBPF อาจ Compiled ไม่ผ่านบนบาง Distribution การใช้ Log-based Enforcement จึงเสถียรและบำรุงรักษาง่ายกว่ามาก

---

### 🔹 Layer 2: Transport & Collection Layer (การรวบรวมและนำส่ง)
**หน้าที่:** อ่าน Log ไฟล์ แปลง Format ดึง Metadata และส่งออกผ่านเครือข่าย

* **ทำไมถึงเลือก Fluent Bit?**
  - กิน RAM ต่ำมาก (เพียง ~20MB เทียบกับ Logstash ที่กินระดับ 500MB+)
  - มี Built-in SQLite Buffer (`DB /var/log/fluent-bit-*.db`) ช่วยให้ Log ไม่หายแม้ Network หลุดหรือ Backend ปิดปรับปรุง
* **ทำไมต้องใช้ Lua Script (`transform_siem.lua`) แทน Fluent Bit Filter ทั่วไป?**
  - ใน Fluent Bit v3+/v5+ การใช้ `record_modifier` มีข้อจำกัดเรื่อง Dynamic Tagging และ Nested Key Injection
  - การเขียน Lua Function ทำให้เรา Inject ฟิลด์ `clusterOrSubnet`, จัดการ Timestamp และครอบ Object `metadata` ได้ยืดหยุ่นในโค้ดบล็อกเดียว
* **Trade-off & Alternatives:**
  - *ทำไมไม่ใช้ Vector หรือ Promtail?*
    - **Promtail:** ถูกออกแบบมาเพื่อ Grafana Loki เท่านั้น ไม่เหมาะกับการยิง REST Payload เข้า Custom Backend
    - **Vector:** ทรงพลังแต่การ Deploy และ Binary Size มีขนาดใหญ่กว่า Fluent Bit

---

### 🔹 Layer 3: Control Plane & Data Governance (หัวใจความปลอดภัยฝั่งรับ)
**หน้าที่:** คัดกรองสิทธิ์, ทำความสะอาดข้อมูล (Sanitization) และตัดข้อมูลส่วนบุคคล (PII)

* **ทำไมต้องทำ Data Masking & PII Redaction ในเลเยอร์นี้?**
  - ข้อมูลที่ถูกส่งมาจาก Edge แม้จะผ่านการกรองมาบ้าง แต่ยังมีโอกาสติด Student Email, รหัสนักศึกษา หรือ Source Code ติดมาใน Error Message
  - **Zero Trust Rule:** Backend จะไม่ยอมบันทึก Log ลง Database ในสภาพ Raw หากตรวจพบ Pattern อีเมลหรือรหัสนักศึกษา ระบบจะ Regex แทนที่ด้วย `[REDACTED_EMAIL]` หรือ `[REDACTED_STUDENT_ID]` ทันที
* **ทำไมต้องใช้ HMAC-SHA256 (Deterministic Pseudonymization) แทนที่จะ Random ID?**
  - *ถ้าสุ่ม ID ใหม่ทุกครั้ง (Random UUID):* เราจะไม่สามารถนำข้อมูลไปวิเคราะห์ต่อได้เลยว่า "การโจมตีหรือการเกิด OOM ซ้ำซาก 5 ครั้งนี้ มาจากผู้ใช้คนเดียวกันหรือไม่"
  - *การใช้ HMAC-SHA256:* เมื่อนำ User ID มา Hash ด้วย Secret Key จะได้ `anon_xxxx` ที่เหมือนเดิมเสมอ ทำให้คำนวณสถิติและคิดเงิน (Billing) ได้อย่างแม่นยำ โดยที่ Admin ก็ไม่สามารถย้อนรอยกลับไปเป็นชื่อหรือตัวตนนศ.ได้
* **การป้องกัน Ingestion API:**
  - กำหนดให้รับเฉพาะ Request ที่มี Header `X-Collector-Secret` ที่ตรงกับค่าที่แจกให้เฉพาะ Daemon ในวง Tailscale เท่านั้น หากเป็น Student หรือ Instructor ยิงเข้ามาจะถูก Reject ด้วย HTTP 403 Forbidden ทันที
* **Trade-off & Alternatives:**
  - *ทำไมไม่บันทึกลง ElasticSearch หรือ ClickHouse?*
    - สเกลของ Virtual Lab ในปัจจุบันยังรองรับได้สบายบน PostgreSQL ที่มีการทำ Composite Index `(created_at DESC, severity)` และ `(created_at DESC, category)`
    - การใช้ PostgreSQL ร่วมกับระบบหลักช่วยลดภาระการดูแล Infrastructure เพิ่มอีกหนึ่งตัว (Single Source of Truth)

---

### 🔹 Layer 4: Presentation Layer (หน้าจอ Admin Monitor & Billing)
**หน้าที่:** ประมวลผลและนำเสนอข้อมูลให้ผู้ดูแลระบบมองเห็นภาพรวมความมั่นคงปลอดภัย

* **หลักการออกแบบ (Read-Only Philosophy):**
  - หน้านี้ถูกจำกัดสิทธิ์เฉพาะบทบาท **Admin** เท่านั้น (Role-Based Access Control)
  - ไม่อนุญาตให้มี Endpoint สำหรับแก้ไข ดัดแปลง หรือลบ Log จากหน้าจอเด็ดขาด เพื่อป้องกันการทำลายหลักฐาน (Audit Trail Integrity)
* **การจัดกลุ่มตามวงเครือข่าย (NAT Subnet & Multi-Cloud):**
  - ออกแบบ UI ให้แยกแยะชัดเจนระหว่างโหนดภายใน (`Local K3s Edge`) และโหนดบนคลาวด์ (`AWS SkyPilot Cloud`)
  - ช่วยให้ผู้ดูแลระบบตรวจสอบได้ทันทีว่า เหตุการณ์ผิดปกติเกิดขึ้นที่แลปห้องไหน หรือวง Subnet ใด
* **Executive Export Security:**
  - การส่งออกรายงาน Billing เป็น CSV หรือ PDF จะส่งออกเฉพาะยอดสรุปรายวิชาและรหัส `anon_id` เท่านั้น เพื่อให้ฝ่ายบริหารตรวจสอบงบประมาณได้โดยไม่ละเมิดความเป็นส่วนตัวของผู้เรียน

---

## 3. สรุปตารางเปรียบเทียบเทคโนโลยี (Architecture Trade-off Matrix)

| เทคโนโลยีที่เลือก | ตัวเลือกอื่นที่ถูกพิจารณา | เหตุผลที่เลือก | ข้อจำกัด/Trade-off ที่ต้องยอมรับ |
| :--- | :--- | :--- | :--- |
| **Fluent Bit** | Logstash, Promtail, Vector | ใช้ทรัพยากรต่ำมาก (~20MB RAM), มี SQLite buffering ในตัว | Syntax Configuration มีความเข้มงวด ต้องพึ่งพา Lua เมื่อต้องการ Logic ซับซ้อน |
| **Lua Filtering** | Native Record Modifier | จัดการ Nested JSON และ Dynamic Tags ได้ยืดหยุ่น | ทีมต้องมีความเข้าใจพื้นฐานของภาษา Lua เพิ่มเติม |
| **Tailscale Mesh** | Public IP + TLS, OpenVPN | ทำ Zero-Trust Network ข้าม Cloud/Local ได้โดยไม่ต้องเปิด Port สู่ Public Internet | ต้องติดตั้ง Client Daemon บนทุกโหนดที่เข้าร่วม |
| **HMAC-SHA256 Anonymization** | Random UUID, AES-256 Encryption | ช่วยให้คำนวณความถี่และทำ Billing ได้ถูกต้อง โดยที่ย้อนกลับไปหาตัวตนจริงไม่ได้ | ต้องจัดเก็บและรักษาความลับของ Secret Key ไว้อย่างเข้มงวด |
| **PostgreSQL Partitioning/Index** | Elasticsearch, OpenSearch | ใช้ Database ตัวเดียวกับระบบหลัก ประหยัด Resource | รองรับ Throughput ปานกลาง (หากระบบขยายไประดับล้าน log/วัน ต้องย้ายไป ClickHouse) |

---

## 4. วิธีการทดสอบและทวนสอบระบบ (Verification & Testing Guide)

### 4.1 Automated Backend & Frontend Tests
- **Monitor API Test Suite:**
  ```bash
  pytest tests/monitor/ --color=yes
  ```
  ทดสอบการทำงานของ PII Redaction, HMAC Anonymization, RBAC Protection, Data Normalization และ Ingestion Logic (18/18 ผ่าน)
- **Billing API Test Suite:**
  ```bash
  pytest tests/billing/ --color=yes
  ```
  ทดสอบการคิดค่าใช้จ่าย, การสรุปผลตามวง Subnet และการส่งออก CSV/PDF แบบ Anonymized (16/16 ผ่าน)
- **Frontend Dashboard Tests:**
  ```bash
  npm test
  ```
  ทดสอบการ Render Dashboard, การแสดงผลตาราง Log, การเปิด Side Drawer และการกด Export รายงาน (15/15 ผ่าน)

### 4.2 End-to-End Live Pipeline Test Script
สามารถทดสอบการยิง Log จำลองผ่านทั้ง 4 เสาหลักความปลอดภัย (Squid, Kyverno, Tailscale, Kernel OOM) และยืนยันการขึ้นผลบน Dashboard:
```bash
python script/test_monitoring_siem_pipeline.py
```
ผลลัพธ์ที่ได้จะตรวจสอบความสมบูรณ์ 4 ด้าน:
1. การเชื่อมต่อกับ Backend API Endpoint
2. การ Ingest และ Mask PII ข้อมูล Log สำเร็จ
3. การอัปเดต Counter การละเมิดความปลอดภัยบนหน้าระบบ
4. การทวนสอบการรักษา Zero Trust Plane Separation ในระดับ Ansible Configuration

