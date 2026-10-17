from sqlalchemy import Column, Integer, Time, Date, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.configs.db import Base
import uuid


class ClassSchedule(Base):
    """กฎการเรียนประจำสัปดาห์ของวิชา เช่น "SE301 ทุกวันจันทร์ 09:00–12:00 ตลอดเทอม"

    ตัวนี้ไม่ได้ใช้ pre-warm ตรง ๆ ต้อง generate เป็น class_slots (รอบจริงรายวัน) ก่อน
    ด้วย app.services.schedule_service.generate_slots
    เวลาเป็นเวลาไทย (Asia/Bangkok) ไม่มี timezone ติดมา ตอน generate ค่อยแปลงเป็น UTC
    """
    __tablename__ = "class_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True)
    weekday = Column(Integer, nullable=False)          # 0 = จันทร์ … 6 = อาทิตย์ (เท่ากับ date.weekday())
    start_time = Column(Time, nullable=False)          # เวลาไทย
    end_time = Column(Time, nullable=False)
    valid_from = Column(Date, nullable=False)          # วันเปิดเทอม
    valid_until = Column(Date, nullable=False)
    default_lab_image_id = Column(UUID(as_uuid=True), ForeignKey("lab_images.id"), nullable=True)
    expected_seats = Column(Integer, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    course = relationship("Course", back_populates="class_schedules", foreign_keys=[course_id])
    default_lab_image = relationship("LabImage", foreign_keys=[default_lab_image_id])
    slots = relationship("ClassSlot", back_populates="schedule")

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_class_schedules_weekday"),
        CheckConstraint("end_time > start_time", name="ck_class_schedules_time_order"),
        CheckConstraint("valid_until >= valid_from", name="ck_class_schedules_date_order"),
        CheckConstraint("expected_seats > 0", name="ck_class_schedules_seats"),
    )

    def __repr__(self):
        return (f"<ClassSchedule(id={self.id}, course_id={self.course_id}, weekday={self.weekday}, "
                f"{self.start_time}-{self.end_time})>")
