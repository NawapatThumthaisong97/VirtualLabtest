"""
Example Model
ตัวอย่าง SQLAlchemy model
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.configs.db import Base


class Example(Base):
    """ตัวอย่าง Model สำหรับ database"""
    
    __tablename__ = "examples"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Example(id={self.id}, title='{self.title}')>"
