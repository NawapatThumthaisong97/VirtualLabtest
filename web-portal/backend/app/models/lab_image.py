from sqlalchemy import Column, String, Integer, BigInteger, DateTime, ForeignKey, Enum, Text, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid
import enum


class ImageStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ScanStatus(enum.Enum):
    """ขั้นของการสแกน image (แยกจาก ImageStatus ที่บอกว่าใช้งานได้หรือยัง)

    NOT_STARTED -> QUEUED (ไฟล์ขึ้น R2) -> RUNNING (มี Job) -> PASSED / FAILED / ERROR
    RUNNING -> QUEUED ได้เมื่อ retry หรืออัปไฟล์ทับ ดู docs/LAB_IMAGE_SCAN_ARCHITECTURE.md
    """
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


# สถานะที่สแกนจบแล้ว (ได้ผลสุดท้าย) — event อัปโหลดหลังจากนี้ไม่เริ่มสแกนใหม่
SCAN_FINISHED_STATUSES = (ScanStatus.PASSED, ScanStatus.FAILED, ScanStatus.ERROR)


class LabImage(Base):
    __tablename__ = "lab_images"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True)
    
    # Image Identification
    repository = Column(String(255), nullable=False)  # "skypilot/music-lab"
    tag = Column(String(100), nullable=False)         # "lab-01"
    # NULL ได้: ตอนขอ presign ยังไม่มีไฟล์ จึงยังไม่รู้ digest — scan reconciler เติมเมื่อ push เข้า registry สำเร็จ
    # ไม่ unique: tar เนื้อเดียวกันที่อัปโหลดสองชื่อได้ digest เดียวกัน (ปกติของ registry)
    # ความไม่ซ้ำที่สำคัญคือ (repository, tag) ใน uq_repository_tag
    image_digest = Column(String(255), nullable=True)
    # ตอน presign ใช้ค่าประมาณจากขนาดที่ client แจ้ง แล้ว webhook / approve ทับด้วยค่าจริง
    size_mb = Column(Integer, nullable=False)
    
    # Resource Requirements (for SkyPilot)
    cpu_requirement = Column(String(20), nullable=False, default="2+")          # "2+", "4", "8+"
    memory_requirement = Column(String(20), nullable=False, default="4+")       # "4+", "8", "16+" (GB)
    disk_size = Column(Integer, nullable=False, default=50)                     # GB
    lifespan_minutes = Column(Integer, nullable=False, default=60)              # อายุขัยของ lab (นาที): 60 = 1 ชั่วโมง
    
    # Port Configuration
    exposed_ports = Column(JSONB, nullable=False, default=lambda: [])           # [8080, 5173, 8443]

    # Container Runtime
    entrypoint_script = Column(String(255), nullable=False, default="/bin/bash /run.sh")  # path to startup script
    workdir = Column(String(255), nullable=True)                                # working directory (optional, defaults to image WORKDIR)
    
    # Environment Variables (optional)
    env_vars = Column(JSONB, nullable=True)                                     # {"IDE_PASSWORD": "musiclab"}
    
    # Metadata
    description = Column(Text, nullable=True)
    status = Column(Enum(ImageStatus), default=ImageStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Metadata After Upload to R2
    # archive_key: server สร้างตอนขอ presign (ห้ามใช้ชื่อไฟล์จาก client) และใช้เป็นตัวจับคู่กับ
    #   object_key ที่ Webhook ส่งมา จึงต้อง unique + index (NULL ซ้ำได้ = ยังไม่เคยขอ presign)
    # archive_etag / archive_size_bytes / archive_uploaded_at: Webhook เป็นคนเติม
    #   archive_uploaded_at เป็น NULL = ยังไม่มีไฟล์ขึ้น R2 (draft), มีค่า = อัปโหลดแล้วรออนุมัติ
    archive_key = Column(String(500), nullable=True, unique=True, index=True)
    archive_etag = Column(String(255), nullable=True)
    archive_size_bytes = Column(BigInteger, nullable=True)
    archive_uploaded_at = Column(DateTime(timezone=True), nullable=True)

    # Scan (เขียนโดย webhook ตอนไฟล์ขึ้น R2 และ scan reconciler เท่านั้น)
    # scan_attempts: จำนวน Job ที่เปิดไปแล้วสำหรับไฟล์ปัจจุบัน (etag นี้) รีเซ็ตเป็น 0 เมื่อ etag เปลี่ยน
    # scan_job_name: Job ใน K8s ของความพยายามล่าสุด ใช้จับคู่แถวกับ Job
    # scan_finished_at: ได้ผลสุดท้ายเมื่อไหร่ ใช้นับ retention ก่อนลบแถวที่ FAILED/ERROR
    # scan_summary: ผลสรุปจาก termination message ของ Pod (verdict, reasons, warnings, จำนวนช่องโหว่)
    scan_status = Column(
        Enum(ScanStatus),
        default=ScanStatus.NOT_STARTED,
        server_default=ScanStatus.NOT_STARTED.name,
        nullable=False,
        index=True,
    )
    scan_attempts = Column(Integer, default=0, server_default="0", nullable=False)
    scan_job_name = Column(String(63), nullable=True)
    scan_started_at = Column(DateTime(timezone=True), nullable=True)
    scan_finished_at = Column(DateTime(timezone=True), nullable=True)
    scan_summary = Column(JSONB, nullable=True)
    
    # Relationships
    uploader = relationship("User", back_populates="uploaded_images", foreign_keys=[uploaded_by])
    course = relationship("Course", back_populates="lab_images", foreign_keys=[course_id])
    labs = relationship("Lab", back_populates="image")
    sessions = relationship("Session", back_populates="lab_image")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('repository', 'tag', name='uq_repository_tag'),
    )
    
    def __repr__(self):
        return f"<LabImage(id={self.id}, repository='{self.repository}', tag='{self.tag}', status='{self.status.value}')>"
    
    @property
    def full_image_name(self) -> str:
        """สร้าง full image path: repository:tag"""
        return f"{self.repository}:{self.tag}"
    
    def get_skypilot_resources(self) -> dict:
        """ดึงข้อมูล resource requirements สำหรับ SkyPilot YAML"""
        return {
            "cpus": self.cpu_requirement,
            "memory": self.memory_requirement,
            "disk_size": self.disk_size,
            "ports": self.exposed_ports or []
        }
