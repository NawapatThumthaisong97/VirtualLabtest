"""
Database Configuration
SQLAlchemy setup and database connection management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from app.utils.logger import logger
from .settings import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # เช็คการเชื่อมต่อก่อนใช้งาน
    pool_size=10,
    max_overflow=20,
    echo=True
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency สำหรับ FastAPI routes
    ใช้สำหรับ inject database session
    
    Usage:
        @router.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """
    ตรวจสอบการเชื่อมต่อกับ Database
    
    Returns:
        bool: True ถ้าเชื่อมต่อสำเร็จ, False ถ้าเชื่อมต่อไม่สำเร็จ
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        
        logger.info("Database connection successful")
        return True
        
    except OperationalError as e:
        logger.error(f"Database connection failed: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while connecting to database: {str(e)}")
        return False


# Database schema changes are managed exclusively through Alembic migrations.

__all__ = ["Base", "engine", "SessionLocal", "get_db", "check_db_connection"]
