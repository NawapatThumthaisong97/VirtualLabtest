"""
API Routes
"""
from fastapi import APIRouter
from .example import router as example_router
from .kubernetes_route import router as k8s_router
from .lab_route import router as lab_router

# สร้าง main router
api_router = APIRouter()

# รวม routes ทั้งหมด
api_router.include_router(example_router, prefix="/example", tags=["Example"])
api_router.include_router(k8s_router, prefix="/kubernetes", tags=["Kubernetes"])
api_router.include_router(lab_router, prefix="/labs", tags=["Labs"])

__all__ = ["api_router"]
