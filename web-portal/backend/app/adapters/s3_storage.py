"""
S3 storage adapter — bucket เดียว (terraform/storage) แยกด้วย prefix ตาม key ที่ DB เก็บ
(courses/... / labs/... / course-docs/...) ไม่ต้องแปลง key ตอนย้ายจาก disk

เปิดไฟล์: backend เช็กสิทธิ์เองแล้วออก presigned GET อายุสั้น (STORAGE_PRESIGN_SECONDS)
- ลิงก์ <a> / <img> → endpoint เดิมตอบ 307 ไปที่ presigned URL (ไม่ต้องใช้ CORS)
- fetch ในหน้าเว็บ (react-pdf) → endpoint .../doc-url คืน URL แล้ว fetch ตรง (bucket มี CORS GET)
credential: default chain ของ boto3 (AWS_PROFILE=skypilot ใน container) ไม่เก็บ key ในโค้ด
"""
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi.responses import RedirectResponse, Response

from app.configs.settings import settings
from app.exceptions.domain import ValidationError

_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


def _check_key(key: str) -> str:
    # key มาจาก DB ที่คนกรอกได้ — S3 ไม่มี path traversal แต่กัน key แปลก ๆ ไว้แบบเดียวกับ LocalStorage
    if not key or key.startswith("/") or ".." in key.split("/"):
        raise ValidationError(f"Invalid storage key: {key}")
    return key


class S3Storage:
    def __init__(self, bucket: str, region: str, client=None, presign_seconds: int = 300):
        self.bucket = bucket
        self.presign_seconds = presign_seconds
        # endpoint ของ region ตรง ๆ + SigV4: ถ้าปล่อยให้ boto3 ใช้ s3.amazonaws.com (ส่วนกลาง) presigned URL ของ bucket
        # นอก us-east-1 (โดยเฉพาะที่เพิ่งสร้าง) ถูก S3 ตอบ 307 ไป host ของ region แล้วลายเซ็นที่ผูก host เดิมใช้ไม่ได้
        self.client = client or boto3.client(
            "s3",
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=_check_key(key))
            return True
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in _NOT_FOUND:
                return False
            raise

    def save(self, key: str, source: BinaryIO, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        # upload_fileobj แบ่งไฟล์ใหญ่เป็น multipart เอง ไม่ต้องอ่านทั้งไฟล์เข้า memory
        self.client.upload_fileobj(source, self.bucket, _check_key(key), ExtraArgs=extra)

    def delete(self, key: str) -> None:
        # bucket เปิด versioning: ลบ = ใส่ delete marker กู้ได้ภายใน noncurrent_days
        self.client.delete_object(Bucket=self.bucket, Key=_check_key(key))

    def presigned_url(self, key: str, *, media_type: str, disposition: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": _check_key(key),
                # ให้ S3 ตอบ header เดียวกับที่ backend เคยตอบ (เปิดใน browser / ชื่อไฟล์ตอนดาวน์โหลด)
                "ResponseContentType": media_type,
                "ResponseContentDisposition": disposition,
            },
            ExpiresIn=self.presign_seconds,
        )

    def response(self, key: str, *, media_type: str, disposition: str) -> Response:
        # 307 คง method เดิม (GET) และ browser ไม่ cache ทั้งที่ URL หมดอายุ
        return RedirectResponse(
            self.presigned_url(key, media_type=media_type, disposition=disposition),
            status_code=307,
            headers={"Cache-Control": "no-store"},
        )


def build_s3_storage() -> S3Storage:
    if not settings.STORAGE_S3_BUCKET:
        raise RuntimeError("STORAGE_BACKEND=s3 ต้องตั้ง STORAGE_S3_BUCKET")
    return S3Storage(
        bucket=settings.STORAGE_S3_BUCKET,
        region=settings.STORAGE_S3_REGION or settings.AWS_REGION,
        presign_seconds=settings.STORAGE_PRESIGN_SECONDS,
    )
