"""
Base Schema
Base model สำหรับให้ทุก schema แปลง field เป็น camelCase ตอน serialize/validate
(ชื่อตัวแปรใน Python ยังคงเป็น snake_case ตาม PEP8)
"""
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """
    Base model ที่:
    - alias_generator=to_camel  -> gen alias เป็น camelCase (total_pages -> totalPages)
    - populate_by_name=True     -> ยังรับ input เป็นชื่อ snake_case เดิมได้ด้วย
    - from_attributes=True      -> สร้างจาก ORM object (SQLAlchemy) ได้โดยตรง
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
