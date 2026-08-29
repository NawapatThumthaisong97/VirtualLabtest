from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelModel


class CourseResponse(CamelModel):
    id: UUID
    code: str
    name: str
    lecturer_name: str
    image_url: str | None


class CourseCreateRequest(CamelModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    lecturer_name: str = Field(min_length=1, max_length=255)
    image_url: str | None = Field(None, max_length=2048)
    created_by: UUID


class CourseUpdateRequest(CamelModel):
    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=255)
    lecturer_name: str | None = Field(None, min_length=1, max_length=255)
    image_url: str | None = Field(None, max_length=2048)