"""
FastAPI Main Application
Entry point for the FastAPI backend
"""
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.configs import settings, check_db_connection
from app.routes import api_router
from app.utils.logger import logger


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


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
