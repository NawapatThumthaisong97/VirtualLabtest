from datetime import datetime
from uuid import UUID
from pydantic import Field
from app.schemas.base import CamelModel

from app.models.lab import LabStatus, RunTarget
from app.models.lab_progress import ProgressStatus


# Fetch information GET methods
class LabResponse(CamelModel):
    id: UUID
    title: str
    description: str | None
    doc_url: str | None
    order_no: int
    due_at: datetime | None
    status: LabStatus
    # lab image ที่ผูกไว้ (None = lab แบบอ่านเอกสารอย่างเดียว) หน้าอาจารย์ใช้ตั้งค่า dropdown ตอนแก้ไข
    image_id: UUID | None = None
    # kubernetes / aws / auto (auto = เลือกตามเครื่องที่กด Start ดู RunTarget)
    run_target: RunTarget | None = None
    # ความคืบหน้าของ "คนที่เรียก API" ไม่ใช่ของ lab — คนละคนเรียกได้คนละค่า
    # None = ยังไม่มีแถวใน lab_progress (ยังไม่เคยเปิดทำ)
    progress_status: ProgressStatus | None = None


class CourseBrief(CamelModel):
    """
    ข้อมูล course เท่าที่หน้า lab detail ต้องใช้ทำหัวเรื่อง — ไม่ยัดทั้งก้อนมา

    หัวเรื่องคือ "รหัสวิชา : ชื่อวิชา" เท่านั้น ไม่มีชื่ออาจารย์
    ถ้าหน้าไหนต้องการข้อมูล course มากกว่านี้ ให้ไปเรียก endpoint ของ course เอง
    """

    id: UUID
    code: str
    name: str


class LabDetailResponse(LabResponse):
    """
    ใช้กับ GET /labs/{lab_id} เท่านั้น

    แยกจาก LabResponse เพราะ list ไม่ควรต้อง join course ทุกแถว
    ส่วน doc_url ที่ติดมาจาก parent เป็น object key ภายใน (เช่น labs/{id}/doc.pdf)
    ไม่ใช่ URL ที่เบราว์เซอร์เปิดได้ -> ให้เรียก GET /labs/{lab_id}/doc แทน
    """

    course: CourseBrief


# Sending information POST
class LabCreateRequest(CamelModel):
    course_id: UUID
    title: str = Field(max_length=255)
    # ไม่ส่ง = ต่อท้าย (เลขสูงสุดในวิชา + 1) ฟอร์มอาจารย์ไม่ต้องมีช่องนี้
    order_no: int | None = Field(None, gt=0)
    description: str | None = None
    doc_url: str | None = None
    image_id: UUID | None = None
    due_at: datetime | None = None
    status: LabStatus = LabStatus.DRAFT
    # ค่าเริ่มต้นเท่ากับของเดิม (column server_default) ส่ง None ไม่ได้ เพราะ column เป็น NOT NULL
    run_target: RunTarget = RunTarget.KUBERNETES


# Alter information PATCH
class LabUpdateRequest(CamelModel):
    # No use to write course_id cause we use only lab_id
    # ทุก field ต้องมี default None ไม่งั้นกลายเป็น required -> PATCH แก้ field เดียวไม่ได้
    title: str | None = Field(None, max_length=255)
    description: str | None = None
    doc_url: str | None = None
    order_no: int | None = Field(None, gt=0)
    due_at: datetime | None = None
    status: LabStatus | None = None
    run_target: RunTarget | None = None
    # ส่ง null = ถอด image ออกจาก lab, ไม่ส่ง = ไม่แก้
    image_id: UUID | None = None


# Delete don't require schemas implementation


class LabDocUrlResponse(CamelModel):
    """URL ไว้ fetch เอกสาร — null = storage เป็น disk ให้ใช้ GET /labs/{id}/doc"""
    url: str | None = None
