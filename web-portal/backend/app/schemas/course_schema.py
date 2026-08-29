from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelModel

BackgroundKey = Literal["blue1", "blue2", "blue3", "blue4"]
IconKey = Literal["layers", "database", "cloud"]


class AnnouncementResponse(CamelModel):
    id: UUID
    message: str
    created_at: datetime | None = None


class CourseResponse(CamelModel):
    id: UUID
    code: str
    name: str
    lecturer_name: str
    image_url: str | None
    background_key: BackgroundKey | None
    icon_key: IconKey | None
    announcement_ids: list[UUID] | None = None


class CourseDetailResponse(CourseResponse):
    announcements: list[AnnouncementResponse] = Field(default_factory=list)


class CourseCreateRequest(CamelModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    lecturer_name: str = Field(min_length=1, max_length=255)
    image_url: str | None = Field(None, max_length=2048)
    background_key: BackgroundKey | None = None
    icon_key: IconKey | None = None
    created_by: UUID


class CourseUpdateRequest(CamelModel):
    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=255)
    lecturer_name: str | None = Field(None, min_length=1, max_length=255)
    image_url: str | None = Field(None, max_length=2048)
    background_key: BackgroundKey | None = None
    icon_key: IconKey | None = None
    announcement_ids: list[UUID] | None = Field(None, min_length=1)
