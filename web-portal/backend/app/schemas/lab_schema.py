from datetime import datetime
from uuid import UUID
from pydantic import Field
from app.schemas.base import CamelModel

from app.models.lab import LabStatus
from app.schemas.base import CamelModel

#Fetch information GET methods
class LabResponse(CamelModel):
    id: UUID
    title: str
    description: str | None
    doc_url: str | None
    order_no: int
    due_at: datetime | None
    status: LabStatus

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
    title: str | None = Field(max_length=255)
    description: str | None = None
    doc_url: str | None = None
    order_no: int | None = Field(None, gt=0)
    due_at: datetime | None = None
    status: LabStatus | None = None

#Delete don't require schemas implementation