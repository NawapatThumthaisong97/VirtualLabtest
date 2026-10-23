"""
Cloudflare R2 Adapter (S3-compatible API ผ่าน boto3)

ใช้ออก presigned URL ให้ client อัปโหลดไฟล์ตรงเข้า bucket โดยไฟล์ไม่ผ่าน backend
การสร้าง presigned URL เป็นการเซ็นในเครื่อง (SigV4) ไม่ได้ยิง request ไป R2

credential ใช้ R2 API token (Access Key ID / Secret Access Key) จาก settings เท่านั้น
ไม่ใช้ credential chain ของ AWS (env / profile) กันไปหยิบ key ของ AWS ที่ใช้กับ ECR มาโดยไม่ตั้งใจ
"""
from functools import cached_property

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.configs.settings import settings
from app.exceptions.domain import InternalServerError


class R2NotConfiguredError(InternalServerError):
    code = "r2_not_configured"


class R2DeleteError(InternalServerError):
    code = "r2_delete_failed"


class R2Adapter:
    @cached_property
    def client(self):
        """boto3 S3 client ชี้ไป R2 (สร้างครั้งแรกที่ใช้ ไม่ใช่ตอน import กันแอปล่มถ้ายังไม่ตั้งค่า)"""
        endpoint_url = settings.r2_endpoint_url
        if not (
            endpoint_url
            and settings.R2_ACCESS_KEY_ID
            and settings.R2_SECRET_ACCESS_KEY
            and settings.R2_BUCKET_NAME
        ):
            raise R2NotConfiguredError(
                "R2 is not configured (R2_ACCOUNT_ID / R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME)"
            )

        return boto3.client(
            service_name="s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            # R2 ไม่ใช้ region แต่ SigV4 ต้องมี — Cloudflare กำหนดให้ใช้ "auto"
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                # path-style: https://<account>.r2.cloudflarestorage.com/<bucket>/<key>
                # ไม่ขึ้นกับว่าชื่อ bucket เป็น DNS label ที่ใช้ได้หรือไม่
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
            ),
            # NOTE: boto3 >= 1.36 ใส่ checksum header (CRC32) ให้เองทุก PUT ซึ่ง R2 / presigned URL
            # อาจไม่รับ ถ้าอัปเกรดจาก 1.35.x ให้เพิ่ม request_checksum_calculation="when_required"
            # ใน Config ด้วย (option นี้ไม่มีในเวอร์ชันที่ pin อยู่)
        )

    @property
    def bucket(self) -> str:
        return settings.R2_BUCKET_NAME or ""

    def generate_presigned_put_url(
        self,
        key: str,
        content_type: str,
        expires_in: int | None = None,
    ) -> str:
        """presigned URL สำหรับ PUT object 1 ไฟล์

        content_type ถูกรวมใน signature: client ต้องส่ง header Content-Type ค่าเดียวกันเป๊ะ
        ไม่งั้น R2 ตอบ 403 SignatureDoesNotMatch
        """
        return self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in or settings.R2_PRESIGN_EXPIRES_SECONDS,
            HttpMethod="PUT",
        )


    def delete_object(self, key: str) -> None:
        """ลบ object ออกจาก bucket — key ที่ไม่มีอยู่แล้วถือว่าสำเร็จ (S3/R2 ตอบ 204 เหมือนกัน)

        ลบไม่สำเร็จ (network / credential / สิทธิ์) -> R2DeleteError เพื่อให้ผู้เรียกไม่ไปลบข้อมูลฝั่ง DB ต่อ
        """
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as error:
            raise R2DeleteError(f"Failed to delete {key} from R2") from error


r2_adapter = R2Adapter()
