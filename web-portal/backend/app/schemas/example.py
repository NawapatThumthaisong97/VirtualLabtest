"""
Example Schemas
Pydantic models สำหรับ validation และ serialization
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class ExampleBase(BaseModel):
    """Base schema สำหรับ Example"""
    title: str = Field(..., min_length=1, max_length=255, description="ชื่อหัวข้อ")
    description: Optional[str] = Field(None, description="คำอธิบาย")
    is_active: bool = Field(True, description="สถานะการใช้งาน")


class ExampleCreate(ExampleBase):
    """Schema สำหรับสร้าง Example ใหม่"""
    pass


class ExampleUpdate(BaseModel):
    """Schema สำหรับอัพเดท Example"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ExampleResponse(ExampleBase):
    """Schema สำหรับ response (รวม fields จาก database)"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
