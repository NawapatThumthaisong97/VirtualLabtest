"""
Local file storage adapter

เก็บไฟล์บน disk ของเครื่องที่รัน backend โดยใช้ "object key" หน้าตาเดียวกับ
ที่ S3/R2 จะใช้ (เช่น labs/{lab_id}/doc.pdf) วันที่ย้ายขึ้น bucket จริงจะได้
เปลี่ยนแค่ adapter ตัวนี้ตัวเดียว — DB, service และ frontend ไม่ต้องแก้เลย
"""
from pathlib import Path

from app.configs.settings import settings
from app.exceptions.domain import ValidationError


class LocalStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.STORAGE_ROOT).resolve()

    def resolve(self, key: str) -> Path:
        """
        แปลง object key -> path จริงบน disk

        key มาจาก DB ซึ่งคนกรอกเองได้ ถ้ามี ../ ปนมาจะไต่ออกไปอ่านไฟล์นอก
        โฟลเดอร์ storage ได้ (path traversal) เลยต้องเช็คทุกครั้งว่า path
        ที่ resolve แล้วยังอยู่ใต้ root จริง
        """
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValidationError(f"Invalid storage key: {key}")
        return target

    def exists(self, key: str) -> bool:
        return self.resolve(key).is_file()


local_storage = LocalStorage()
