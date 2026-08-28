"""
API Routes
"""

from fastapi import APIRouter
from .auth_route import router as auth_router
from .example import router as example_router
from .kubernetes_route import router as k8s_router
from .lab_route import router as lab_router
from .courses_route import router as courses_router

# สร้าง main router
api_router = APIRouter()

# รวม routes ทั้งหมด
api_router.include_router(auth_router, tags=["Auth"])
api_router.include_router(example_router, prefix="/example", tags=["Example"])
api_router.include_router(k8s_router, prefix="/kubernetes", tags=["Kubernetes"])
api_router.include_router(lab_router, prefix="/labs", tags=["Labs"])
api_router.include_router(courses_router, prefix="/courses", tags=["Courses"])
__all__ = ["api_router"]
