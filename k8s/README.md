# Kubernetes Authentication Infrastructure & Secret Management (Issue #81)

โครงสร้างพื้นฐานสำหรับระบบยืนยันตัวตน (Authentication Infrastructure) ด้วย **Kubernetes-native Secrets**, **RBAC (Role-Based Access Control)**, และ **oauth2-proxy** ทำงานร่วมกับ **Google SSO / University Accounts**.

---

## 1. สถาปัตยกรรม (Architecture Overview)

```
                            [ Internet / University Network ]
                                          │
                                 vlab.dome.tu.ac.th
                                          │
                              ┌───────────▼───────────┐
                              │    Ingress / Router   │
                              │ (Traefik / NGINX CRD) │
                              └───────────┬───────────┘
                                          │ ForwardAuth
                                 ┌────────▼────────┐
                                 │  oauth2-proxy   │◄───► [ Google OAuth2 / SSO ]
                                 │  (Port: 4180)   │      (hd: dome.tu.ac.th, tu.ac.th)
                                 └────────┬────────┘
                                          │ Injects X-Forwarded-Email, X-Forwarded-User
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    │                                           │
           ┌────────▼─────────┐                       ┌─────────▼─────────┐
           │ virtual-lab-     │                       │ virtual-lab-      │
           │ frontend (:80)   │                       │ backend (:8000)   │
           └──────────────────┘                       └─────────┬─────────┘
                                                                │
                                                      ┌─────────▼─────────┐
                                                      │ postgres db (:5432)│
                                                      └───────────────────┘
```

---

## 2. การจัดการความลับ (Kubernetes-native Secrets)

ตามข้อกำหนด **Constraint 1 (Issue #81)**:
> ความลับทั้งหมด เช่น JWT Secret Key, OAuth Client ID, และ Client Secret จะต้องถูกจัดเก็บและอิงตามมาตรฐาน Kubernetes-native secret และ RBAC เท่านั้น **ห้าม Hardcode ลงใน Source Code เด็ดขาด**

รายการ Secrets ในระบบ (Namespace: `virtual-lab`):

| Secret Name | Keys | คำอธิบาย | ผู้มีสิทธิ์อ่านผ่าน RBAC |
|---|---|---|---|
| `jwt-secret` | `secret-key`, `algorithm` | Secret key สำหรับ sign/verify Access & Refresh JWT | `auth-service-account` |
| `google-oauth-secret` | `client-id`, `client-secret` | Credentials สำหรับ Google OAuth2 SSO | `auth-service-account`, `oauth2-proxy-sa` |
| `oauth2-proxy-secret` | `cookie-secret` | 32-byte secret สำหรับเข้ารหัส cookie ของ oauth2-proxy | `oauth2-proxy-sa` |
| `database-secret` | `database-url` | Connection string ของ PostgreSQL | `auth-service-account` |

---

## 3. การควบคุมสิทธิ์ (RBAC Least Privilege)

ใน [`01-rbac.yaml`](file:///c:/Users/Xplosion97/VirtualLabtest/k8s/auth/01-rbac.yaml):
- **ServiceAccount `auth-service-account`**: ผูกกับ Role `auth-secrets-reader` ซึ่งจำกัดสิทธิ์ (`resourceNames`) ให้ดึงได้เฉพาะ Secret ที่จำเป็นต่องาน Auth เท่านั้น ไม่สามารถอ่าน Secret อื่นใน Namespace หรือ Cluster ได้
- **ServiceAccount `oauth2-proxy-sa`**: ผูกกับ Role `oauth2-proxy-secret-reader` ซึ่งเข้าถึงได้เฉพาะ `google-oauth-secret` และ `oauth2-proxy-secret`

---

## 4. การทำงานร่วมกับ oauth2-proxy (Google SSO)

ใน [`03-oauth2-proxy-config.yaml`](file:///c:/Users/Xplosion97/VirtualLabtest/k8s/auth/03-oauth2-proxy-config.yaml) และ [`04-oauth2-proxy-deployment.yaml`](file:///c:/Users/Xplosion97/VirtualLabtest/k8s/auth/04-oauth2-proxy-deployment.yaml):
- กำหนด `provider = "google"` และจำกัด `email_domains = ["dome.tu.ac.th", "tu.ac.th"]`
- เปิด `set_xauthrequest = true` และ `pass_user_headers = true`
- Header ที่ส่งต่อไปยัง Backend ได้แก่:
  - `X-Forwarded-Email`: อีเมลมหาวิทยาลัยของผู้ใช้
  - `X-Forwarded-User`: ชื่อหรือ ID ของผู้ใช้
  - `X-Auth-Request-Email`: อีเมลที่ผ่านการยืนยันจาก Google
- Backend ของ Virtual Lab ได้รับการพัฒนาให้รองรับ Header เหล่านี้ผ่าน Endpoint `/api/auth/sso/callback` เพื่อทำ Auto-Provisioning ผู้ใช้เข้าสู่ฐานข้อมูลโดยอัตโนมัติ

---

## 5. ขั้นตอนการติดตั้งและทดสอบ (Deployment Steps)

### ขั้นตอนที่ 1: สร้าง Secret ใน Cluster (ไม่มีการเก็บใน Git)
```bash
# บน Linux/macOS
export JWT_SECRET_KEY=$(openssl rand -hex 32)
export GOOGLE_CLIENT_ID="<your-google-client-id>.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="<your-google-client-secret>"
bash k8s/scripts/setup-auth-secrets.sh

# บน Windows PowerShell
.\k8s\scripts\setup-auth-secrets.ps1 -GoogleClientId "<your-id>" -GoogleClientSecret "<your-secret>"
```

### ขั้นตอนที่ 2: ใช้ RBAC และ Workloads
```bash
kubectl apply -f k8s/auth/00-namespace.yaml
kubectl apply -f k8s/auth/01-rbac.yaml
kubectl apply -f k8s/auth/03-oauth2-proxy-config.yaml
kubectl apply -f k8s/auth/04-oauth2-proxy-deployment.yaml
kubectl apply -f k8s/auth/05-ingress-forward-auth.yaml
kubectl apply -f k8s/auth/06-backend-deployment.yaml
```

### ขั้นตอนที่ 3: ตรวจสอบสถานะ
```bash
kubectl -n virtual-lab get secrets
kubectl -n virtual-lab get pods -l app.kubernetes.io/name=oauth2-proxy
kubectl -n virtual-lab logs deployment/oauth2-proxy
```

