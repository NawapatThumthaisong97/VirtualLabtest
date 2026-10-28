"""
จุดเดียวที่เลือกว่าไฟล์ของเว็บอยู่ที่ไหน — STORAGE_BACKEND=local (disk) / s3 (bucket ของ terraform/storage)

service / route เรียก get_storage() ตอนใช้งาน (ไม่ import object ตรง) เทสสลับเป็น storage ปลอมได้ที่เดียว:
    monkeypatch.setattr("app.adapters.storage._storage", LocalStorage(tmp_path))

ทั้งสองตัวมี method เดียวกัน: exists / save / delete / presigned_url / response
"""
from pathlib import PurePosixPath
from urllib.parse import quote

from app.configs.settings import settings

_storage = None


def get_storage():
    global _storage
    if _storage is None:
        if settings.STORAGE_BACKEND == "s3":
            from app.adapters.s3_storage import build_s3_storage

            _storage = build_s3_storage()
        else:
            from app.adapters.local_storage import local_storage

            _storage = local_storage
    return _storage


def content_disposition(filename: str, inline: bool = True) -> str:
    """header Content-Disposition ที่รองรับชื่อภาษาไทย (RFC 6266: filename ASCII + filename* UTF-8)"""
    name = PurePosixPath(filename).name or "file"
    ascii_name = "".join(ch for ch in name if ch.isascii() and ch not in '"\\\r\n') or "file"
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
