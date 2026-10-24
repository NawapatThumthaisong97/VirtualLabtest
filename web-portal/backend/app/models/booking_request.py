import uuid

from sqlalchemy import Column, Integer, String, Text, Time, Date, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db import Base


class BookingRequest(Base):
    """คำขอจองห้องแลปรายสัปดาห์จากอาจารย์ (หน้า /admin/scheduler, docs/ADMIN_MONITOR.md PR 6)

    pending → approved (สร้าง class_schedule + class_slots) / rejected / cancelled
    admin สร้างเอง (Create new event) = แถวที่ approved ทันที requested_by = admin
    """
    __tablename__ = "booking_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    lab_id = Column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=False)
    weekday = Column(Integer, nullable=False)              # 0 = จันทร์ … 6 = อาทิตย์
    start_time = Column(Time, nullable=False)              # เวลาไทย
    end_time = Column(Time, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)             # "ทุกสัปดาห์ถึงวันที่"
    machines = Column(Integer, nullable=False)
    room = Column(String(64), nullable=True)               # ห้องที่อยากได้ / ห้องที่ admin ให้
    note = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="pending", server_default="pending")
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(Text, nullable=True)            # เหตุผลตอน reject / หมายเหตุตอน approve
    class_schedule_id = Column(UUID(as_uuid=True), ForeignKey("class_schedules.id"), nullable=True)
    mail_status = Column(String(16), nullable=True)        # pending / sent / failed / skipped
    mail_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    course = relationship("Course", foreign_keys=[course_id])
    lab = relationship("Lab", foreign_keys=[lab_id])
    requester = relationship("User", foreign_keys=[requested_by])

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_booking_requests_weekday"),
        CheckConstraint("end_time > start_time", name="ck_booking_requests_time_order"),
        CheckConstraint("valid_until >= valid_from", name="ck_booking_requests_date_order"),
        CheckConstraint("machines > 0", name="ck_booking_requests_machines"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_booking_requests_status"),
        Index("ix_booking_requests_status", "status"),
    )
