"""
Application Settings
Load environment variables and configuration
"""
from datetime import datetime
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


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
    API_PREFIX: str = "/api"
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
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
    R2_ENDPOINT_URL: Optional[str] = None
    
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

    # กันเครื่องอื่นเปิด lab ของเรา (นักศึกษาเครื่องข้าง ๆ เปิด IDE ผ่าน Tailscale IP ได้)
    # - warm pod: hostPort ผูกกับ 127.0.0.1 → เปิดได้แค่ http://localhost:<port> บนเครื่องนั้น
    # - launch ผ่าน SkyPilot จากเครื่องแลป: บังคับ pod ลงเครื่องที่กด Start (nodeSelector)
    # - pod ของ lab ทั้งสองแบบติด label vlab/lab=true ให้ NetworkPolicy vlab-lab-isolation ปิดขาเข้า
    #   (k8s/lab-isolation-networkpolicy.yaml) กันการเข้าทาง pod IP จากเครื่องอื่นผ่าน flannel
    # ปิดไว้เป็นค่าเริ่มต้นจนกว่าจะทดลองครบ (docs/DaemonSetsExperiment.md หัวข้อ Exp4)
    LAB_ISOLATION_ENABLED: bool = False
    # กำหนดเวลาเองเพิ่มจาก class_slots เป็น JSON ใน .env (ไว้ทดลอง) เวลาต้องมี timezone เช่น
    # PREWARM_TARGETS=[{"image":"100.127.74.48:5001/vlab/hello:v1","start_at":"2026-10-17T14:00:00+07:00","end_at":"2026-10-17T15:00:00+07:00"}]
    PREWARM_TARGETS: list[PrewarmTarget] = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )
    
    @property
    def cors_origins(self) -> list:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS_STR.split(",")]


# Global settings instance
settings = Settings()
