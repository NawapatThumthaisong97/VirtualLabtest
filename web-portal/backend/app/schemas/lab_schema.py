from datetime import datetime
from uuid import UUID
from pydantic import Field
from app.schemas.base import CamelModel

from app.models.lab import LabStatus


#Fetch information GET methods
class LabResponse(CamelModel):
    id: UUID
    title: str
    description: str | None
    doc_url: str | None
    order_no: int
    due_at: datetime | None
    status: LabStatus


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


#Sending information POST
class LabCreateRequest(CamelModel):
    course_id: UUID
    title: str = Field(max_length=255)
    order_no: int = Field(gt=0)
    description: str | None = None
    doc_url: str | None = None
    image_id: UUID | None = None
    due_at: datetime | None = None
    status: LabStatus = LabStatus.DRAFT

#Alter information PATCH
class LabUpdateRequest(CamelModel):
    #No use to write course_id cause we use only lab_id
    #ทุก field ต้องมี default None ไม่งั้นกลายเป็น required -> PATCH แก้ field เดียวไม่ได้
    title: str | None = Field(None, max_length=255)
    description: str | None = None
    doc_url: str | None = None
    order_no: int | None = Field(None, gt=0)
    due_at: datetime | None = None
    status: LabStatus | None = None

#Delete don't require schemas implementation
