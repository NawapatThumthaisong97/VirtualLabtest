"""
LogMaskerService
ทำหน้าที่ทำ Data Masking สำหรับ logs และ security events:
- ตัดข้อมูล Source Code ภายใน Pod และ stdout
- ลบฟิลด์ PII (ชื่อ, อีเมล, รหัสนักศึกษา) ทั้งหมด
- แปลง user_id (UUID) เป็นรหัสแฝงแบบทางเดียว (HMAC-SHA256 Pseudonymized ID เช่น anon_8f92a1)
- จัดรูปแบบ Payload ให้อยู่ในรูป CamelCase เสมอ
"""

import hashlib
import hmac
import re
from typing import Any, Optional
from uuid import UUID

from app.configs.settings import settings


class LogMaskerService:
    """Service สำหรับทำ Data Masking และ Pseudonymization ให้พร้อมสำหรับ SIEM"""

    EMAIL_REGEX = re.compile(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        re.IGNORECASE,
    )
    STUDENT_ID_REGEX = re.compile(r"\b\d{10}\b")
    # ตรวจจับ code blocks ใน markdown หรือ stack traces
    CODE_BLOCK_REGEX = re.compile(r"```[\s\S]*?```", re.MULTILINE)
    INLINE_CODE_REGEX = re.compile(r"`[^`\n]{4,}`")
    PYTHON_TRACE_REGEX = re.compile(
        r'(File\s+["\'][^"\']+["\'],\s+line\s+\d+[\s\S]*?)(?=\n\S|\Z)',
        re.MULTILINE,
    )
    # ตรวจจับ Shell prompt หรือ interactive stdout
    SHELL_PROMPT_REGEX = re.compile(
        r"^(bash|sh|\$|>>>|\.\.\.)\s+.*$",
        re.MULTILINE,
    )

    PII_FIELD_NAMES = {
        "email",
        "user_email",
        "name",
        "user_name",
        "fullname",
        "full_name",
        "first_name",
        "last_name",
        "student_id",
        "phone",
        "phone_number",
        "password",
        "password_hash",
        "secret",
        "token",
    }

    def __init__(self, secret_key: Optional[str] = None):
        # ใช้ SECRET_KEY ของระบบเป็น HMAC key
        self.secret_key = (
            secret_key or getattr(settings, "SECRET_KEY", "virtual-lab-pseudonym-salt")
        ).encode("utf-8")

    def pseudonymize_user_id(self, user_id: UUID | str | None) -> Optional[str]:
        """
        แปลง user_id (UUID) เป็นรหัสแฝงแบบทางเดียว (HMAC-SHA256 Pseudonymized ID)
        เช่น anon_8f92a1
        - Deterministic: user_id เดิมจะได้ anon_id เดิมเสมอ เพื่อใช้ correlation ใน SIEM
        - One-way: ไม่สามารถถอดกลับเป็น user_id จริงได้โดยไม่มี secret key
        """
        if not user_id:
            return None

        clean_user_id = str(user_id).strip().lower()
        if not clean_user_id:
            return None

        digest = hmac.new(
            self.secret_key, clean_user_id.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # ตัด slice 8 ตัวอักษรเพื่อความกระชับ เช่น anon_8f92a10b
        return f"anon_{digest[:8]}"

    def mask_text(self, text: str | None) -> str:
        """
        ตัดข้อมูล Source Code, PII (อีเมล, รหัสนักศึกษา) ออกจากข้อความ text
        """
        if not text:
            return ""

        sanitized = text

        # 1. Mask code blocks
        sanitized = self.CODE_BLOCK_REGEX.sub("[REDACTED_SOURCE_CODE]", sanitized)
        sanitized = self.INLINE_CODE_REGEX.sub("[REDACTED_CODE]", sanitized)
        sanitized = self.PYTHON_TRACE_REGEX.sub("[REDACTED_TRACE]", sanitized)
        sanitized = self.SHELL_PROMPT_REGEX.sub("[REDACTED_INPUT]", sanitized)

        # 2. Mask PII
        sanitized = self.EMAIL_REGEX.sub("[REDACTED_EMAIL]", sanitized)
        sanitized = self.STUDENT_ID_REGEX.sub("[REDACTED_STUDENT_ID]", sanitized)

        return sanitized

    def mask_log_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """
        ประมวลผลข้อมูล Log หรือ Event ทั้งก้อน:
        - ลบฟิลด์ PII (email, name, student_id)
        - แปลง user_id เป็น anon_id
        - ทำความสะอาด source code และ PII ใน text fields
        """
        masked: dict[str, Any] = {}

        # ตรวจสอบ user_id เพื่อสร้าง anon_id
        user_id_val = record.get("user_id") or record.get("userId")
        anon_id = self.pseudonymize_user_id(user_id_val)
        if anon_id:
            masked["anon_id"] = anon_id

        for key, value in record.items():
            lower_key = key.lower().replace("-", "_")

            # ข้ามฟิลด์ที่เป็น PII
            if lower_key in self.PII_FIELD_NAMES or lower_key in ("user_id", "userid"):
                continue

            # ถ้าเป็น string ให้ทำ mask_text
            if isinstance(value, str):
                masked[key] = self.mask_text(value)
            elif isinstance(value, dict):
                masked[key] = self.mask_log_record(value)
            elif isinstance(value, list):
                masked[key] = [
                    self.mask_log_record(item)
                    if isinstance(item, dict)
                    else (self.mask_text(item) if isinstance(item, str) else item)
                    for item in value
                ]
            else:
                masked[key] = value

        return masked
