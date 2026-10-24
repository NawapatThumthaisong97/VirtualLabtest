"""
Booking Schemas — จองห้องแลป / ปฏิทินคาบ (หน้า /admin/scheduler, docs/ADMIN_MONITOR.md PR 6) ส่งออก camelCase
"""
from datetime import date, datetime, time
from datetime import date as Date   # field ชื่อ date ใน CalendarEvent ชนกับชื่อ type
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelModel

BookingStatus = Literal["pending", "approved", "rejected", "cancelled"]


class BookingCreate(CamelModel):
    """อาจารย์ขอจอง: ทุกสัปดาห์วัน weekday เวลา start–end ตั้งแต่ valid_from ถึง valid_until"""
    course_id: UUID
    lab_id: UUID
    weekday: int = Field(..., ge=0, le=6, description="0 = จันทร์ … 6 = อาทิตย์")
    start_time: time = Field(..., description="เวลาไทย HH:MM")
    end_time: time
    valid_from: date
    valid_until: date
    machines: int = Field(..., gt=0)
    room: Optional[str] = Field(None, max_length=64, description="ห้องที่อยากได้ (ไม่บังคับ)")
    note: Optional[str] = Field(None, max_length=1000)


class ScheduleForm(CamelModel):
    """ฟอร์ม Class Scheduler (admin): คาบแรก first_date + เวลา, ทำซ้ำทุกสัปดาห์ถึง until"""
    lab_id: UUID
    room: str = Field(..., min_length=1, max_length=64)
    machines: int = Field(..., gt=0)
    first_date: date
    start_time: time
    end_time: time
    until: date = Field(..., description="ทุกสัปดาห์ถึงวันที่ (รวมวันนั้น)")
    note: Optional[str] = Field(None, max_length=1000)


class ScheduleCreate(ScheduleForm):
    """Create new event (admin สร้างเอง ไม่มีคำขอ)"""
    course_id: UUID


class RejectBody(CamelModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class BookingItem(CamelModel):
    id: UUID
    status: BookingStatus
    requester_name: str
    requester_email: str
    course_id: UUID
    course_name: str
    lab_id: UUID
    lab_title: str
    weekday: int
    start_time: time
    end_time: time
    valid_from: date
    valid_until: date
    machines: int
    room: Optional[str]
    note: Optional[str]
    decision_note: Optional[str]
    class_schedule_id: Optional[UUID]
    slots_created: Optional[int] = None
    mail_status: Optional[str]
    created_at: datetime


class BookingListResponse(CamelModel):
    items: list[BookingItem]
    pending_count: int = Field(..., description="badge ที่ปุ่ม Class Request")


class CalendarEvent(CamelModel):
    id: UUID
    title: str
    date: Date = Field(..., description="วันที่ (เวลาไทย)")
    start: str = Field(..., description="HH:MM เวลาไทย")
    end: str
    room: Optional[str]
    course_id: UUID
    course_name: str
    machines: int
    status: str


class CalendarResponse(CamelModel):
    month: str
    events: list[CalendarEvent]


class OptionCourse(CamelModel):
    id: UUID
    code: str
    name: str
    instructors: list[str]


class OptionLab(CamelModel):
    id: UUID
    course_id: UUID
    title: str
    has_image: bool = Field(..., description="มี image (อนุมัติแล้ว) — ไม่มี = pre-warm ไม่ได้ จองไม่ได้")


class OptionRoom(CamelModel):
    room: str
    pcs_total: int


class SchedulerOptions(CamelModel):
    courses: list[OptionCourse]
    labs: list[OptionLab]
    rooms: list[OptionRoom]
