"""
FastAPI Main Application
Entry point for the FastAPI backend
"""
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
from sqladmin import Admin, ModelView

from app.configs import settings, check_db_connection
from app.configs.db import engine
from app.models import (
    User, Course, CourseImage, Enrollment, Lab, LabImage,
    LabProgress, Session, UsageRecord, Quota, Announcement
)
from app.exceptions.domain import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.routes import api_router
from app.utils.logger import logger


from sqladmin import Admin, ModelView
from sqlalchemy import inspect

# SQLAdmin Model Views - Dynamic column_list from model
def get_model_columns(model, exclude=None):
    """
    Extract column names from SQLAlchemy model
    exclude: list of column names to exclude
    """
    if exclude is None:
        exclude = []
    
    mapper = inspect(model)
    columns = []
    for column in mapper.columns:
        if column.name not in exclude:
            columns.append(getattr(model, column.name))
    return columns


class UserAdmin(ModelView, model=User):
    name = "User"
    icon = "fa-solid fa-user"
    column_list = get_model_columns(User)


class CourseAdmin(ModelView, model=Course):
    name = "Course"
    icon = "fa-solid fa-book"
    column_list = get_model_columns(Course)


class CourseImageAdmin(ModelView, model=CourseImage):
    name = "Course Image"
    icon = "fa-solid fa-image"
    column_list = get_model_columns(CourseImage)


class EnrollmentAdmin(ModelView, model=Enrollment):
    name = "Enrollment"
    icon = "fa-solid fa-graduation-cap"
    column_list = get_model_columns(Enrollment)


class LabAdmin(ModelView, model=Lab):
    name = "Lab"
    icon = "fa-solid fa-flask"
    column_list = get_model_columns(Lab)


class LabImageAdmin(ModelView, model=LabImage):
    name = "Lab Image"
    icon = "fa-solid fa-image"
    column_list = get_model_columns(LabImage)


class LabProgressAdmin(ModelView, model=LabProgress):
    name = "Lab Progress"
    icon = "fa-solid fa-chart-line"
    column_list = get_model_columns(LabProgress)


class SessionAdmin(ModelView, model=Session):
    name = "Session"
    icon = "fa-solid fa-terminal"
    column_list = get_model_columns(Session, exclude=['endpoints'])  # ซ่อน JSON ที่ซับซ้อน


class UsageRecordAdmin(ModelView, model=UsageRecord):
    name = "Usage Record"
    icon = "fa-solid fa-chart-bar"
    column_list = get_model_columns(UsageRecord)


class QuotaAdmin(ModelView, model=Quota):
    name = "Quota"
    icon = "fa-solid fa-pie-chart"
    column_list = get_model_columns(Quota)


class AnnouncementAdmin(ModelView, model=Announcement):
    name = "Announcement"
    icon = "fa-solid fa-bullhorn"
    column_list = get_model_columns(Announcement)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan events
    - startup: เช็คการเชื่อมต่อ database ก่อนเปิด server
    - shutdown: cleanup resources
    """
    # Startup
    logger.info("Starting FastAPI application...")
    logger.info(f"App: {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    
    # เช็คการเชื่อมต่อ database
    logger.info("Checking database connection...")
    if not check_db_connection():
        logger.error("Cannot connect to database. Server will not start.")
        sys.exit(1)  # ออกจากโปรแกรมถ้าเชื่อมต่อ DB ไม่สำเร็จ
    
    logger.info("Application started successfully!")
    
    yield  # Server กำลังทำงาน
    
    # Shutdown
    logger.info("Shutting down application...")


# สร้าง FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="FastAPI Backend with PostgreSQL, Cloudflare R2, and more",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip Compression Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Global Exception Handlers

# map กลุ่มของ domain exception -> HTTP status
# เรียงจากเจาะจงไปกว้าง เพราะ isinstance() จะ match ตัวแรกที่เจอ
STATUS_MAP = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    ForbiddenError: status.HTTP_403_FORBIDDEN,
    ValidationError: status.HTTP_400_BAD_REQUEST,
}


@app.exception_handler(DomainError)
async def domain_exception_handler(request, exc: DomainError):
    """
    แปลง domain exception (ภาษา business) -> HTTP response (ภาษา HTTP)

    service layer โยน LabNotFoundError / DuplicateOrderNoError ออกมา
    โดยไม่ต้องรู้จัก HTTP เลย -> handler ตัวนี้เป็นคนแปลให้

    เพิ่ม exception ใหม่ที่สืบทอดจากกลุ่มใน STATUS_MAP
    จะได้ status ถูกต้องอัตโนมัติ ไม่ต้องแก้ไฟล์นี้
    """
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    for error_type, code in STATUS_MAP.items():
        if isinstance(exc, error_type):
            status_code = code
            break

    logger.warning(f"[{exc.code}] {exc.message}")

    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": exc.message,
            "error": {"code": exc.code, "message": exc.message},
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request, exc):
    """จับ database errors"""
    logger.error(f"Database error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Database error occurred"}
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """จับ validation errors"""
    logger.warning(f"Validation error: {str(exc)}")
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """จับ unexpected errors"""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Health Check Endpoint
@app.get("/", tags=["Health"])
def health_check():
    """
    Health check endpoint
    """
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


@app.get("/health", tags=["Health"])
def health():
    """
    Detailed health check
    """
    db_status = check_db_connection()
    return {
        "status": "healthy" if db_status else "unhealthy",
        "database": "connected" if db_status else "disconnected",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


# Include API routes
app.include_router(api_router, prefix=settings.API_PREFIX)


# Setup SQLAdmin
admin = Admin(app, engine, authentication_backend=None)

# Add model views to admin
admin.add_view(UserAdmin)
admin.add_view(CourseAdmin)
admin.add_view(CourseImageAdmin)
admin.add_view(EnrollmentAdmin)
admin.add_view(LabAdmin)
admin.add_view(LabImageAdmin)
admin.add_view(LabProgressAdmin)
admin.add_view(SessionAdmin)
admin.add_view(UsageRecordAdmin)
admin.add_view(QuotaAdmin)
admin.add_view(AnnouncementAdmin)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )