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
    # secret ของ webhook approve/reject lab image (POST /api/webhook/approve-lab-image, reject-lab-image) แยกจาก R2_WEBHOOK_SECRET
    # เพราะ R2_WEBHOOK_SECRET ถูกเก็บใน Terraform / Cloudflare Worker ถ้าหลุด ต้องไม่ถึงขั้นอนุมัติ image ได้
    # ไม่ตั้ง = webhook ปฏิเสธทุก request
    LAB_IMAGE_APPROVE_WEBHOOK_SECRET: Optional[str] = None
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
    # ต้องเป็นแบบ dual-stack (...dkr-ecr.<region>.on.aws) เพราะ private subnet ออกได้แค่ IPv6
    ECR_REGISTRY_HOST: Optional[str] = None

    # ทุกกี่วินาทีให้ backend เช็กว่าเครื่องของ session ที่ RUNNING ยังอยู่ไหม (0 = ปิด)
    SESSION_RECONCILE_INTERVAL_SECONDS: int = 60

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
