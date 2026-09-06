from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum, Text, UniqueConstraint
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


class LabImage(Base):
    __tablename__ = "lab_images"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True)
    
    # Image Identification
    repository = Column(String(255), nullable=False)  # "skypilot/music-lab"
    tag = Column(String(100), nullable=False)         # "lab-01"
    image_digest = Column(String(255), nullable=False, unique=True)
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
