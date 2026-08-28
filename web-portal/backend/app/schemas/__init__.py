"""
Pydantic Schemas (Data Validation)
"""

from .example import ExampleBase, ExampleCreate, ExampleUpdate, ExampleResponse
from .auth_schema import LoginRequest, MeResponse, TokenResponse
from .lab_schema import (
    CourseBrief,
    LabCreateRequest,
    LabDetailResponse,
    LabResponse,
    LabUpdateRequest,
)
from .course_schema import CourseCreateRequest, CourseResponse, CourseUpdateRequest

__all__ = [
    "ExampleBase",
    "ExampleCreate",
    "ExampleUpdate",
    "ExampleResponse",
    "LoginRequest",
    "MeResponse",
    "TokenResponse",
    "CourseBrief",
    "LabCreateRequest",
    "LabDetailResponse",
    "LabResponse",
    "LabUpdateRequest",
    "CourseCreateRequest",
    "CourseResponse",
    "CourseUpdateRequest",
]
