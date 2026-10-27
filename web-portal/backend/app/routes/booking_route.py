"""
Booking Routes — จองห้องแลป (หน้า /admin/scheduler, docs/ADMIN_MONITOR.md PR 6)
อาจารย์: ส่งคำขอ / ดูคำขอของตัวเอง (ยังไม่มีหน้า ใช้ API) — admin: ดู / approve / reject / สร้างเอง / ปฏิทิน
"""
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status as http_status
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.middlewares.auth import get_current_user
from app.middlewares.rbac import verify_permission
from app.models.user import User
from app.schemas.booking_schema import (
    BookingCreate,
    BookingItem,
    BookingListResponse,
    CalendarResponse,
    RejectBody,
    ScheduleCreate,
    ScheduleForm,
    SchedulerOptions,
)
from app.schemas.response import ApiResponse
from app.services import booking_service
from app.services.admin_monitor_service import AdminMonitorService
from app.services.kubernetes_service import get_kubernetes_service
from app.utils.logger import logger

router = APIRouter()
admin_router = APIRouter(dependencies=[Depends(verify_permission("courses:manage:global"))])


def room_capacity(db: Session = Depends(get_db)) -> Optional[dict[str, int]]:
    """ห้อง → จำนวนเครื่องจาก K3s (label vlab/room) ต่อไม่ได้ = None (ข้ามการเช็กจำนวนเครื่อง)"""
    try:
        return AdminMonitorService(db, get_kubernetes_service()).room_capacities()
    except Exception as e:
        logger.warning(f"[booking] cannot read rooms: {e}")
        return None


def ok(message: str, data) -> dict:
    return {"success": True, "message": message, "data": data}


# ---------- อาจารย์ ----------

@router.post("/v1/bookings", response_model=ApiResponse[BookingItem], response_model_by_alias=True,
             status_code=http_status.HTTP_201_CREATED)
def create_booking(body: BookingCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """อาจารย์ของวิชาขอจองห้องทุกสัปดาห์ (weekday + เวลา + ช่วงวันที่) → pending รอ admin"""
    return ok("Booking request created", booking_service.create_request(db, user, body))


@router.get("/v1/bookings/mine", response_model=ApiResponse[list[BookingItem]], response_model_by_alias=True)
def my_bookings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """คำขอของฉัน + สถานะ"""
    return ok("Booking requests retrieved", booking_service.my_requests(db, user))


# ---------- admin ----------

@admin_router.get("/bookings", response_model=ApiResponse[BookingListResponse], response_model_by_alias=True)
def list_bookings(status: Optional[str] = Query("pending", pattern="^(pending|approved|rejected|cancelled)$"),
                  db: Session = Depends(get_db)):
    """ตาราง Class Request + pendingCount (badge)"""
    return ok("Booking requests retrieved", booking_service.list_requests(db, status))


@admin_router.post("/bookings/{booking_id}/approve", response_model=ApiResponse[BookingItem],
                   response_model_by_alias=True)
def approve_booking(booking_id: UUID, form: ScheduleForm, background: BackgroundTasks,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user),
                    rooms: Optional[dict[str, int]] = Depends(room_capacity)):
    """อนุมัติ: สร้างคาบทุกสัปดาห์ถึง until ในห้องที่เลือก (ชนห้อง / วิชา = 409) แล้วส่งเมลแจ้งอาจารย์"""
    item = booking_service.approve(db, booking_id, user, form, rooms)
    background.add_task(booking_service.send_decision_mail, item.id)
    return ok("Booking approved", item)


@admin_router.post("/bookings/{booking_id}/reject", response_model=ApiResponse[BookingItem],
                   response_model_by_alias=True)
def reject_booking(booking_id: UUID, body: RejectBody, background: BackgroundTasks,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ไม่อนุมัติ + เหตุผล (ส่งในเมลถึงอาจารย์)"""
    item = booking_service.reject(db, booking_id, user, body.reason)
    background.add_task(booking_service.send_decision_mail, item.id)
    return ok("Booking rejected", item)


@admin_router.post("/bookings/{booking_id}/resend-mail", response_model=ApiResponse[dict])
def resend_mail(booking_id: UUID, background: BackgroundTasks):
    """ส่งเมลแจ้งผลซ้ำ (เช่นครั้งแรกส่งไม่ผ่าน)"""
    background.add_task(booking_service.send_decision_mail, booking_id)
    return ok("Mail queued", {"bookingId": str(booking_id)})


@admin_router.post("/schedules", response_model=ApiResponse[BookingItem], response_model_by_alias=True,
                   status_code=http_status.HTTP_201_CREATED)
def create_schedule(form: ScheduleCreate, background: BackgroundTasks, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user),
                    rooms: Optional[dict[str, int]] = Depends(room_capacity)):
    """Create new event: admin จองเองไม่ผ่านคำขอ (อนุมัติทันที + เมลถึงอาจารย์ของวิชา)"""
    item = booking_service.create_direct(db, user, form, rooms)
    background.add_task(booking_service.send_decision_mail, item.id)
    return ok("Schedule created", item)


@admin_router.get("/calendar", response_model=ApiResponse[CalendarResponse], response_model_by_alias=True)
def get_calendar(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"), db: Session = Depends(get_db)):
    """คาบทั้งเดือน (เวลาไทย) ไม่ใส่ = เดือนนี้"""
    first = date(int(month[:4]), int(month[5:]), 1) if month else date.today().replace(day=1)
    return ok("Calendar retrieved", booking_service.get_calendar(db, first))


@admin_router.get("/scheduler/options", response_model=ApiResponse[SchedulerOptions], response_model_by_alias=True)
def get_options(db: Session = Depends(get_db), rooms: Optional[dict[str, int]] = Depends(room_capacity)):
    """dropdown ของฟอร์ม: วิชา (+ อาจารย์), lab (+ มี image ไหม), ห้อง (+ จำนวนเครื่อง)"""
    return ok("Scheduler options retrieved", booking_service.get_options(db, rooms))
