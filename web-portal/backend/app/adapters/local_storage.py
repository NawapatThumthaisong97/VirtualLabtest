"""
Local file storage adapter

เก็บไฟล์บน disk ของเครื่องที่รัน backend โดยใช้ "object key" หน้าตาเดียวกับ
ที่ S3 ใช้ (เช่น labs/{lab_id}/doc.pdf) — ใช้ตอน dev / เทส ส่วน production ใช้ S3Storage
(เลือกด้วย STORAGE_BACKEND ดู app/adapters/storage.py) DB, service และ frontend ไม่ต้องแก้
"""
from pathlib import Path
from typing import BinaryIO

from fastapi.responses import FileResponse, Response

from app.configs.settings import settings
from app.exceptions.domain import ValidationError


class LocalStorage:
    def __init__(self, root: str | None = None):
        configured_root = Path(root or settings.STORAGE_ROOT)
        if not configured_root.is_absolute():
            configured_root = Path(__file__).resolve().parents[2] / configured_root
        self.root = configured_root.resolve()

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

    def save(self, key: str, source: BinaryIO, content_type: str | None = None) -> None:
        # content_type ไม่ได้ใช้บน disk (FileResponse เดาจากนามสกุล) รับไว้ให้ interface ตรงกับ S3Storage
        target = self.resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as destination:
            while chunk := source.read(1024 * 1024):
                destination.write(chunk)

    def delete(self, key: str) -> None:
        self.resolve(key).unlink(missing_ok=True)

    def presigned_url(self, key: str, *, media_type: str, disposition: str) -> str | None:
        """disk ไม่มี URL แยก — frontend ใช้ endpoint เดิมของ backend แทน"""
        return None

    def response(self, key: str, *, media_type: str, disposition: str) -> Response:
        return FileResponse(self.resolve(key), media_type=media_type, headers={"Content-Disposition": disposition})


local_storage = LocalStorage()
