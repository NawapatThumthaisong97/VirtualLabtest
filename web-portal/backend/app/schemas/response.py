"""
Response Schema
Standard API response format
"""
from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, ConfigDict

T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """
    Standard API Response Format
    """
    success: bool
    message: str
    data: Optional[T] = None
    error: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "Request successful",
            "data": {},
            "error": None
        }
    })


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Paginated API Response Format
    """
    success: bool
    message: str
    data: list[T]
    pagination: Optional[dict[str, int]] = None
    error: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "Request successful",
            "data": [],
            "pagination": {
                "page": 1,
                "limit": 10,
                "total": 100,
                "total_pages": 10
            },
            "error": None
        }
    })
