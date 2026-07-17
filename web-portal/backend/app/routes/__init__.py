"""
API Routes
"""
from fastapi import APIRouter
from .example import router as example_router

# สร้าง main router
api_router = APIRouter()

# รวม routes ทั้งหมด
api_router.include_router(example_router, prefix="/example", tags=["Example"])

__all__ = ["api_router"]
