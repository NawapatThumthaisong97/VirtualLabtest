"""
Application Settings
Load environment variables and configuration
"""
import os
from datetime import datetime
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal, Optional


class PrewarmTarget(BaseModel):
    """image ที่ต้องมีอยู่บนทุก worker ในช่วง start_at ถึง end_at"""
    image: str
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        # ไม่มี timezone จะไม่รู้ว่าเป็นเวลาไทยหรือ UTC ห่างกัน 7 ชม.
        if value.tzinfo is None:
            raise ValueError("ต้องใส่ timezone เช่น 2026-10-17T14:00:00+07:00")
        return value


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # App Settings
    APP_NAME: str = "FastAPI Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # "development" or "production"
    API_PREFIX: str = "/api"
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    
    # Security
    SECRET_KEY: str = Field(min_length=32)
    ADMIN_SESSION_SECRET_KEY: str = Field(min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cookie Security Settings
    AUTH_COOKIE_SECURE: bool = False  # True ใน Production (HTTPS) / False ใน Dev (HTTP/Tailscale)
    AUTH_COOKIE_SAMESITE: str = "lax"  # "lax", "strict", "none"
    AUTH_COOKIE_DOMAIN: Optional[str] = None
    ACCESS_TOKEN_COOKIE_NAME: str = "access_token"
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"

    # University SSO (Google OAuth2 / OIDC) & Allowed Email Domains
    ALLOWED_EMAIL_DOMAINS_STR: str = "dome.tu.ac.th,tu.ac.th"
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/sso/callback"
    GOOGLE_AUTH_URI: str = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URI: str = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URI: str = "https://openidconnect.googleapis.com/v1/userinfo"
    GOOGLE_TOKENINFO_URI: str = "https://oauth2.googleapis.com/tokeninfo"

    # Thammasat University REST API (Active Directory Verify)
    TU_API_ENABLED: bool = True
    TU_API_URL: str = "https://restapi.tu.ac.th/api/v1/auth/Ad/verify"
    TU_API_APP_KEY: Optional[str] = None
    TAILSCALE_TRUSTED_PROXY_CIDRS_STR: str = ""
    
    # CORS - เก็บเป็น string คั่นด้วย comma แล้ว parse ใน code
    CORS_ORIGINS_STR: str = "http://localhost:3000,http://localhost:5173"

    # Storage - โฟลเดอร์ราก (relative กับที่รัน uvicorn) ที่เก็บไฟล์เอกสารแลป
    # ใช้ object key แบบเดียวกับ bucket (labs/{lab_id}/doc.pdf) ตั้งแต่ตอนนี้
    # วันที่ย้ายขึ้น S3/R2 จะได้ก๊อปไฟล์ขึ้นไปเฉย ๆ ไม่ต้องแตะ DB
    STORAGE_ROOT: str = "storage"
    
    # Cloudflare R2
    R2_ACCOUNT_ID: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_BUCKET_NAME: Optional[str] = None
    # ไม่ตั้ง = https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com
    R2_ENDPOINT_URL: Optional[str] = None
    # อายุ presigned PUT URL ของไฟล์ lab image (.tar) — R2 รับได้ 1 วินาทีถึง 7 วัน
    R2_PRESIGN_EXPIRES_SECONDS: int = Field(default=3600, ge=60, le=604800)
    # ต้องตรงกับ webhook_secret ใน terraform/cloudflare/r2-event-pipeline (Worker ส่งมาใน header Webhook-Secret)
    # ไม่ตั้ง = webhook ปฏิเสธทุก request
    R2_WEBHOOK_SECRET: Optional[str] = None
    # presigned URL เป็น PUT ครั้งเดียว R2 รับได้สูงสุด 5 GiB - 5 MiB ต่อ request (ใหญ่กว่านี้ต้อง multipart)
    LAB_IMAGE_MAX_ARCHIVE_BYTES: int = 5 * 1024**3 - 5 * 1024**2

    @property
    def r2_endpoint_url(self) -> Optional[str]:
        if self.R2_ENDPOINT_URL:
            return self.R2_ENDPOINT_URL
        if self.R2_ACCOUNT_ID:
            return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return None
    
    # Redis (Optional)
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    
    # Kubernetes Configuration (Optional)
    K8S_ENABLED: bool = True
    KUBECONFIG_PATH: Optional[str] = None
    K8S_DEFAULT_NAMESPACE: str = "default"
    K8S_TIMEOUT: int = 30
    
    # Docker Registry for SkyPilot
    DOCKER_REGISTRY_HOST: Optional[str] = None
    DOCKER_REGISTRY_PREFIX: Optional[str] = None

    # AWS (lab ที่ run_target = aws) ค่าตาม VPC vlab-ecr-pull ใน infra/ecr-pull-experiment
    AWS_REGION: str = "ap-southeast-1"
    AWS_LAB_AMI: Optional[str] = None          # AMI bake เช่น vlab-bake-0.12.3.post1-r2
    AWS_INSTANCE_TYPE: str = "m7i-flex.large"  # บัญชี free plan สร้างได้แค่บางชนิด
    AWS_DISK_SIZE: int = 30                    # ไม่ใส่ SkyPilot จะใช้ 256 GB
    # หน้า admin billing: ค่า EC2 ต่อชั่วโมงของ AWS_INSTANCE_TYPE (on-demand) + ดิสก์ — ใช้ประมาณค่าใช้จ่าย
    # m7i-flex.large ap-southeast-1 = $0.1197 (catalog ของ SkyPilot ~/.sky/catalogs/v8/aws/vms.csv 2026-10-23)
    # + gp3 30 GB × $0.096/GB-เดือน ÷ 730 ชม. ≈ $0.0039 → เปลี่ยน instance type ต้องแก้ค่านี้ด้วย
    AWS_HOURLY_PRICE_USD: float = 0.1236
    # budget AWS ต่อเดือน (USD) และเกณฑ์เตือน (%)
    AWS_MONTHLY_BUDGET_USD: float = 200.0
    AWS_BUDGET_ALERT_PCT: int = 80
    # ยอดจริงจาก Cost Explorer (วันละครั้ง ครั้งละ $0.01) แทนค่าประมาณของวันที่ผ่านไปแล้ว — ปิดไว้เป็นค่าเริ่มต้น
    # (เทส / dev ไม่ยิง AWS) prod เปิดผ่าน ansible บัญชีรวม → นับเฉพาะ resource ที่มี tag นี้
    AWS_COST_EXPLORER_ENABLED: bool = False
    AWS_COST_TAG_KEY: str = "skypilot-user"
    AWS_COST_TAG_VALUE: str = "vlab-backend"
    AWS_COST_LOOKBACK_DAYS: int = 62

    # เมลแจ้งผลจองห้อง (หน้า /admin/scheduler) — Gmail: บัญชีที่เปิด 2FA + App Password, smtp.gmail.com:587 STARTTLS
    # ไม่ตั้ง SMTP_USER = ไม่ส่ง (mail_status = skipped) — เปลี่ยนบัญชีผู้ส่งแก้แค่ค่าพวกนี้ใน group_vars/all.yml
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    MAIL_FROM_NAME: str = "Virtual Lab Team"
    # ช่วงเทส: ส่งทุกฉบับไปที่อยู่นี้แทนผู้รับจริง (บอกผู้รับจริงในเนื้อเมล) — prod ปล่อยว่าง
    MAIL_REDIRECT_TO: Optional[str] = None
    # ส่งได้เฉพาะผู้รับในรายการ (คั่นด้วย , : เมลเต็ม หรือ @โดเมน) — ว่าง = ไม่ส่งให้ใครเลยนอกจาก MAIL_REDIRECT_TO
    # "*" = ทุกคน (ใช้เมื่อบัญชีอาจารย์ใน DB เป็นของจริงทั้งหมดแล้ว — seed มีเมล @dome.tu.ac.th สมมติที่อาจเป็นของคนจริง)
    MAIL_ALLOWED_RECIPIENTS: str = ""
    # ต้องเป็นแบบ dual-stack (...dkr-ecr.<region>.on.aws) เพราะ private subnet ออกได้แค่ IPv6
    ECR_REGISTRY_HOST: Optional[str] = None
    # credential ที่ใช้ลบ image บน ECR (ไม่ตั้ง = ใช้ credential chain ของ AWS: env / profile / IAM role)
    # ต้องมีสิทธิ์ ecr:BatchDeleteImage, ecr:ListImages, ecr:DeleteRepository บน repository/vlab/*
    AWS_ECR_ACCESS_KEY_ID: Optional[str] = None
    AWS_ECR_SECRET_ACCESS_KEY: Optional[str] = None

    # ทุกกี่วินาทีให้ backend เช็กว่าเครื่องของ session ที่ RUNNING ยังอยู่ไหม (0 = ปิด)
    SESSION_RECONCILE_INTERVAL_SECONDS: int = 60

    # Default Run Target
    DEFAULT_RUN_TARGET: str = "aws"
    DEV_DEFAULT_NODE: Optional[str] = None
    # Lab image scan (docs/LAB_IMAGE_SCAN_ARCHITECTURE.md) ปิดไว้เป็นค่าเริ่มต้น
    # เปิดแล้ว backend จะรัน scan reconciler (ต้องมี K8S_ENABLED ด้วย)
    LAB_IMAGE_SCAN_ENABLED: bool = False
    SCAN_NAMESPACE: str = "vlab-scan"
    # ทุกกี่วินาทีให้ reconciler เก็บผล / เปิด Job ใหม่ / เก็บกวาด (0 = ปิด)
    SCAN_RECONCILE_INTERVAL_SECONDS: int = 15
    # Job สแกนที่รันพร้อมกันได้สูงสุด ที่เหลือรอเป็น QUEUED
    SCAN_MAX_CONCURRENT: int = 2
    # เปิด Job ได้กี่ครั้งต่อไฟล์หนึ่งไฟล์ ก่อนเป็น ERROR (Job ล้ม / หาย / ERROR ชั่วคราว)
    SCAN_MAX_ATTEMPTS: int = 2
    # RUNNING นานกว่านี้โดยที่ Job ยังไม่จบ ถือว่าค้าง (ควร >= activeDeadlineSeconds ของ Job + เผื่อ)
    SCAN_JOB_DEADLINE_SECONDS: int = 1800
    # FAILED / ERROR เก็บไว้กี่วันให้อาจารย์ดูเหตุผล ก่อน reject_image (ลบแถว + tar) 0 = ลบในรอบถัดไป
    SCAN_FAILED_RETENTION_DAYS: int = 7
    # image ของ runner (docs/SCAN_RUNNER_IMAGE.md) ปกติไม่ต้องตั้ง: ใช้ <DOCKER_REGISTRY_HOST>/vlab/scan-runner:<VERSION>
    # ที่ role Ansible scan-runner-image push ไว้ (tag นั้น immutable) ตั้งเองได้ถ้าอยากอ้างด้วย digest
    SCAN_RUNNER_IMAGE: Optional[str] = None
    SCAN_RUNNER_VERSION: str = "1.1.0"  # ต้องตรงกับ scan_runner_version ใน ansible/roles/scan-runner-image/defaults
    # camp registry แยก pull (DOCKER_REGISTRY_HOST, ไม่มี auth) กับ push (ต้อง login)
    # ไม่ตั้ง REGISTRY_PUSH_HOST = host ของ DOCKER_REGISTRY_HOST + REGISTRY_PUSH_PORT
    REGISTRY_PUSH_HOST: Optional[str] = None
    REGISTRY_PUSH_PORT: int = 5002
    # Secret (kubernetes.io/basic-auth) ใน SCAN_NAMESPACE ที่ Ansible role k3s-server สร้าง backend ไม่ต้องรู้รหัส
    SCAN_PUSH_SECRET: str = "registry-push"
    # Pod สแกนต้องรันบน master: ACL ของ Tailscale ให้แค่ master push เข้า registry ได้
    # (traffic ของ Pod ออกไปด้วย IP ของ node) ว่าง {} = ไม่บังคับ
    SCAN_NODE_SELECTOR: dict[str, str] = {"node-role.kubernetes.io/control-plane": "true"}
    # อายุ presigned GET ที่ Pod ใช้โหลด tar (ต้อง > เวลารอ schedule + เวลาโหลด)
    SCAN_DOWNLOAD_URL_TTL_SECONDS: int = 3600
    # ช่องโหว่ระดับนี้ขึ้นไปที่มีเวอร์ชันแก้แล้ว = FAIL (CRITICAL / HIGH / MEDIUM / LOW)
    SCAN_FAIL_SEVERITY: str = "CRITICAL"
    # พื้นที่ /work ของ Pod (tar + Trivy DB) ควรประมาณ 2 เท่าของ tar ใหญ่สุด
    SCAN_WORK_SIZE_LIMIT: str = "15Gi"
    # PriorityClass ต่ำ ให้ Job ถูกเบียดก่อน lab ของนักศึกษา (ไม่ตั้ง = ไม่ใส่)
    # (สร้างโดย k8s/scan-namespace.yaml ที่ Ansible apply ให้ตอนรัน role k3s-server)
    SCAN_PRIORITY_CLASS: Optional[str] = "vlab-scan"
    # หน้า admin การ์ด System status: ตรวจ backend / k8s / registry / SkyPilot / AWS ทุกกี่วินาที (0 = ปิด)
    HEALTH_CHECK_INTERVAL_SECONDS: int = 300
    # เก็บผลตรวจย้อนหลังกี่วัน (job ลบของเก่าทุกรอบ ตารางไม่บวม)
    HEALTH_CHECK_RETENTION_DAYS: int = 7
    # ตอบช้ากว่านี้ (ms) = degraded
    HEALTH_CHECK_SLOW_MS: int = 2000

    # Pre-pull image ลงทุก worker ก่อนคาบ (DaemonSet) ปิดไว้เป็นค่าเริ่มต้น ต้องสั่งเปิดเองเท่านั้น
    # เพราะเครื่องในห้องแลปจริงยังไม่รู้ว่าจะเปิดเครื่องตอนไหน (boot อัตโนมัติ / Deep Freeze ล้างดิสก์)
    # ถ้า scheduler รันเองตลอดจะ pull ใส่เครื่องที่ไม่พร้อม หรือ pull ทิ้งเปล่า ๆ
    PREWARM_ENABLED: bool = False
    # ทุกกี่วินาทีให้ scheduler เทียบ (มีผลเมื่อ PREWARM_ENABLED=true)
    PREWARM_INTERVAL_SECONDS: int = 60
    # เริ่ม pull ก่อน class_slots.starts_at กี่นาที (ลบ DaemonSet ตอน ends_at)
    PREWARM_LEAD_MINUTES: int = 30
    # worker ที่หลุด (NotReady) ไม่เกินกี่นาทียังนับว่าต้องมี image (slot จะยังไม่ READY จนกว่าจะกลับมา)
    # หลุดนานกว่านี้ถือว่าปิดเครื่องไปแล้ว ไม่นับ (เช่น workerfilm ที่ NotReady มาหลายสัปดาห์)
    PREWARM_NODE_GRACE_MINUTES: int = 5

    # Warm pod: รัน lab จริงรอไว้บนเครื่องแลปช่วงคาบ (1 เครื่อง = 1 pod) กด Start จากเครื่องนั้นได้ pod ทันที
    # ปิดไว้เป็นค่าเริ่มต้นแยกจาก PREWARM_ENABLED เพราะกิน CPU / RAM จริงทุกเครื่องตลอดคาบ
    # scheduler สร้าง / ลบ DaemonSet ให้เมื่อเปิดทั้ง PREWARM_ENABLED และตัวนี้ ส่วน launch ใช้ตัวนี้ตัวเดียว
    WARM_POD_ENABLED: bool = False
    # กด Start ตอนที่ warm pod ตัวใหม่ยังไม่ Ready (DaemonSet เพิ่งสร้างแทนตัวที่คนก่อนปิด) รอตัวนั้นกี่วินาที
    # ไม่รอ = ไปสร้าง pod อีกตัวชนกับ warm pod ที่จองที่ไว้ → เครื่องเต็ม (docs/archive/LAB_DIRECT_POD.md)
    WARM_POD_WAIT_SECONDS: int = 60

    # กดจากเครื่องแลปแต่ไม่มี warm pod: "pod" = สร้าง pod ตรงด้วย k8s API บนเครื่องนั้น (ไม่ต้องลงของ ไม่กี่วินาที)
    # "skypilot" = ทางเดิม SkyPilot in-cluster pin เครื่องนั้น (ลง apt / runtime / Ray ทุกครั้ง 3–5 นาที) เก็บไว้เป็นทางสำรอง
    LAB_MACHINE_LAUNCH: Literal["pod", "skypilot"] = "pod"
    # รอ pod ตรง Ready สูงสุดกี่วินาที (รวม pull image ตอนไม่มีคาบ ~700 MB จาก registry ในบ้าน)
    DIRECT_POD_READY_TIMEOUT: int = 180

    # กันเครื่องอื่นเปิด lab ของเรา (นักศึกษาเครื่องข้าง ๆ เปิด IDE ผ่าน Tailscale IP ได้)
    # - warm pod: hostPort ผูกกับ 127.0.0.1 → เปิดได้แค่ http://localhost:<port> บนเครื่องนั้น
    # - launch ผ่าน SkyPilot จากเครื่องแลป: บังคับ pod ลงเครื่องที่กด Start (nodeSelector)
    # - pod ของ lab ทั้งสองแบบติด label vlab/lab=true ให้ NetworkPolicy vlab-lab-isolation ปิดขาเข้า
    #   (k8s/lab-isolation-networkpolicy.yaml) กันการเข้าทาง pod IP จากเครื่องอื่นผ่าน flannel
    # ปิดไว้เป็นค่าเริ่มต้นจนกว่าจะทดลองครบ (docs/archive/DaemonSetsExperiment.md หัวข้อ Exp4)
    LAB_ISOLATION_ENABLED: bool = False
    # กำหนดเวลาเองเพิ่มจาก class_slots เป็น JSON ใน .env (ไว้ทดลอง) เวลาต้องมี timezone เช่น
    # PREWARM_TARGETS=[{"image":"100.127.74.48:5001/vlab/hello:v1","start_at":"2026-10-17T14:00:00+07:00","end_at":"2026-10-17T15:00:00+07:00"}]
    PREWARM_TARGETS: list[PrewarmTarget] = []

    # SkyPilot API server กลาง (helm บน master เช่น https://skypilot.bell-lab.space) + token ของ service account
    # ไม่ตั้ง = ใช้ API server ในเครื่อง (127.0.0.1:46580) เหมือนเดิม
    # sky SDK อ่านค่าจาก os.environ เท่านั้น ดู export_skypilot_env ข้างล่าง
    SKYPILOT_API_SERVER_ENDPOINT: Optional[str] = None
    SKYPILOT_SERVICE_ACCOUNT_TOKEN: Optional[str] = None

    @field_validator("AUTH_COOKIE_DOMAIN", mode="before")
    @classmethod
    def clean_cookie_domain(cls, v):
        if not v or not isinstance(v, str):
            return None
        v = v.split("#")[0].strip()
        return v if v else None

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def clean_environment(cls, v):
        if isinstance(v, str):
            return v.split("#")[0].strip()
        return v

    @field_validator("AUTH_COOKIE_SAMESITE", mode="before")
    @classmethod
    def clean_cookie_samesite(cls, v):
        if isinstance(v, str):
            v = v.split("#")[0].strip().lower()
            return v or "lax"
        return v

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    
    @property
    def scan_runner_image(self) -> Optional[str]:
        """image ที่ Pod สแกนใช้: ค่าที่ตั้งเอง หรือสร้างจาก registry + เวอร์ชัน (None = ยังไม่มี registry)"""
        if self.SCAN_RUNNER_IMAGE:
            return self.SCAN_RUNNER_IMAGE
        if self.DOCKER_REGISTRY_HOST:
            return f"{self.DOCKER_REGISTRY_HOST}/vlab/scan-runner:{self.SCAN_RUNNER_VERSION}"
        return None

    @property
    def registry_push_host(self) -> Optional[str]:
        """host:port ที่ Pod สแกน push ผลที่ผ่าน (None = ยังไม่มี registry)"""
        if self.REGISTRY_PUSH_HOST:
            return self.REGISTRY_PUSH_HOST
        if self.DOCKER_REGISTRY_HOST:
            host = self.DOCKER_REGISTRY_HOST.rsplit(":", 1)[0]
            return f"{host}:{self.REGISTRY_PUSH_PORT}"
        return None

    @property
    def cors_origins(self) -> list:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS_STR.split(",")]

    @property
    def allowed_email_domains(self) -> list[str]:
        """Parse allowed university email domains from comma-separated string"""
        return [
            domain.strip().lower().lstrip("@")
            for domain in self.ALLOWED_EMAIL_DOMAINS_STR.split(",")
            if domain.strip()
        ]

    @property
    def tailscale_trusted_proxy_cidrs(self) -> list[str]:
        return [
            cidr.strip()
            for cidr in self.TAILSCALE_TRUSTED_PROXY_CIDRS_STR.split(",")
            if cidr.strip()
        ]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT.lower() == "development"


SKYPILOT_ENV_KEYS = ("SKYPILOT_API_SERVER_ENDPOINT", "SKYPILOT_SERVICE_ACCOUNT_TOKEN")


def export_skypilot_env(s: Settings) -> None:
    """ส่งค่า SkyPilot จาก .env ไปที่ os.environ ให้ sky SDK เห็น

    pydantic อ่าน .env เข้า settings แต่ไม่ export ออก process env และ sky SDK cache endpoint
    ไว้ตั้งแต่เรียกครั้งแรก จึงต้องทำตอนโหลด settings (ก่อนโค้ดไหนเรียก sky)
    ค่าที่อยู่ใน environ แล้วชนะ (เช่น docker compose env_file หรือ export เองใน shell)
    """
    for key in SKYPILOT_ENV_KEYS:
        value = getattr(s, key)
        if value:
            os.environ.setdefault(key, value)


# Global settings instance
settings = Settings()
export_skypilot_env(settings)
