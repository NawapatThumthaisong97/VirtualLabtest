"""
Response Schema
Standard API response format
"""
from typing import Generic, TypeVar, Optional
from pydantic import Field

from app.schemas.base import CamelModel

T = TypeVar('T')


class PaginationMeta(CamelModel):
    """
    ข้อมูล pagination (serialize เป็น camelCase: totalPages)
    """
    page: int = Field(examples=[1])
    limit: int = Field(examples=[10])
    total: int = Field(examples=[100])
    total_pages: int = Field(examples=[10])


class ErrorDetail(CamelModel):
    """
    รายละเอียด error
    - code: machine-readable เช่น "quota_exceeded"
    - message: human-readable
    """
    code: str = Field(examples=["quota_exceeded"])
    message: str = Field(examples=["Quota exceeded, please try again later"])


class ApiResponse(CamelModel, Generic[T]):
    """
    Standard API Response Format
    """
    success: bool = Field(examples=[True])
    message: str = Field(examples=["Request successful"])
    data: Optional[T] = Field(default=None, examples=[{}])
    error: Optional[ErrorDetail] = None


class PaginatedResponse(CamelModel, Generic[T]):
    """
    Paginated API Response Format
    """
    success: bool = Field(examples=[True])
    message: str = Field(examples=["Request successful"])
    data: list[T] = Field(examples=[[]])
    pagination: Optional[PaginationMeta] = None
    error: Optional[ErrorDetail] = None
