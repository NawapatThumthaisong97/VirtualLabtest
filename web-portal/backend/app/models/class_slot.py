from sqlalchemy import (Column, Integer, Text, DateTime, ForeignKey, Enum, CheckConstraint, Index,
                        DDL, event, text)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import relationship
from app.configs.db import Base
from app.models.lab import RunTarget
import uuid
import enum


class ClassSlotStatus(enum.Enum):
    """สถานะของรอบเรียน 1 รอบ (prewarm scheduler เป็นคนเลื่อน)

    - SCHEDULED: ยังไม่ถึงเวลา pre-warm
    - PREWARMING: สร้าง DaemonSet แล้ว worker ยัง pull ไม่ครบ
    - READY: ทุก worker มี image แล้ว
    - DONE: เลย ends_at แล้ว
    - CANCELLED: ยกเลิก (scheduler ไม่สนใจ และไม่นับใน constraint เวลาทับกัน)
    """
    SCHEDULED = "scheduled"
    PREWARMING = "prewarming"
    READY = "ready"
    DONE = "done"
    CANCELLED = "cancelled"


class ClassSlot(Base):
    """รอบเรียนจริง 1 รอบ: วิชาไหน ใช้ image อะไร ช่วงเวลาไหน กี่คน

    ใช้บอก prewarm scheduler ว่าต้อง pull image อะไรลงทุก worker ก่อนคาบ
    ยังไม่บังคับการจอง นักศึกษาเปิด lab นอกคาบได้ตามปกติ
    """
    __tablename__ = "class_slots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    # null = จองครั้งเดียว ไม่ได้มาจากตารางประจำสัปดาห์
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("class_schedules.id"), nullable=True, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    lab_id = Column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=True)
    lab_image_id = Column(UUID(as_uuid=True), ForeignKey("lab_images.id", ondelete="RESTRICT"), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)   # UTC
    ends_at = Column(DateTime(timezone=True), nullable=False)
    expected_seats = Column(Integer, nullable=False)
    # enum ตัวเดียวกับ labs.run_target (type runtarget ใน Postgres)
    run_target = Column(Enum(RunTarget), default=RunTarget.KUBERNETES,
                        server_default=RunTarget.KUBERNETES.name, nullable=False)
    status = Column(Enum(ClassSlotStatus), default=ClassSlotStatus.SCHEDULED,
                    server_default=ClassSlotStatus.SCHEDULED.name, nullable=False)
    note = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    schedule = relationship("ClassSchedule", back_populates="slots", foreign_keys=[schedule_id])
    course = relationship("Course", back_populates="class_slots", foreign_keys=[course_id])
    lab = relationship("Lab", foreign_keys=[lab_id])
    lab_image = relationship("LabImage", foreign_keys=[lab_image_id])
    sessions = relationship("Session", back_populates="class_slot")

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_class_slots_time_order"),
        CheckConstraint("expected_seats > 0", name="ck_class_slots_seats"),
        Index("ix_class_slots_starts_at", "starts_at"),
        Index("ix_class_slots_course_starts_at", "course_id", "starts_at"),
        # slot ของวิชาเดียวกันห้ามเวลาทับกัน ([starts_at, ends_at) ต่อกันพอดีได้ เช่น 09-12 กับ 12-15)
        # enum เก็บเป็นชื่อ (CANCELLED) ไม่ใช่ value ใน WHERE จึงต้องเป็นตัวใหญ่
        ExcludeConstraint(
            ("course_id", "="),
            (text("tstzrange(starts_at, ends_at)"), "&&"),
            name="ex_class_slots_no_overlap",
            using="gist",
            where=text("deleted_at IS NULL AND status <> 'CANCELLED'"),
        ),
    )

    def __repr__(self):
        return (f"<ClassSlot(id={self.id}, course_id={self.course_id}, {self.starts_at}-{self.ends_at}, "
                f"status='{self.status.value if self.status else None}')>")


# exclusion constraint ที่มี "=" บน uuid ต้องใช้ btree_gist สร้างไว้ก่อนตาราง
# ผูกกับ create_all เลย init_db.py และ DB ของเทสไม่ต้องรันอะไรเพิ่ม (Postgres 13+ ไม่ต้องเป็น superuser)
event.listen(
    ClassSlot.__table__,
    "before_create",
    DDL("CREATE EXTENSION IF NOT EXISTS btree_gist"),
)
