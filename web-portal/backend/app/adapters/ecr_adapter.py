"""
ECR Adapter
ขอ token สำหรับ docker login เข้า ECR ใช้ตอน launch lab ไป AWS
SkyPilot login ECR ให้เองได้เฉพาะชื่อ registry แบบ <acct>.dkr.ecr.<region>.amazonaws.com
(sky/provision/docker_utils.py) แต่ private subnet ของเราออกได้แค่ IPv6 เลยต้อง pull จาก
ชื่อ dual-stack (...dkr-ecr.<region>.on.aws) ซึ่ง SkyPilot ไม่รู้จัก backend จึงขอ token เอง
แล้วส่งเข้า task ตอน launch
ใช้ credential chain ปกติของ boto3 (env / profile / IAM role) token ที่ได้ใช้สิทธิ์ของ
identity นี้ตอน pull ด้วย จึงต้องมีทั้ง ecr:GetAuthorizationToken และสิทธิ์ pull
(BatchGetImage, GetDownloadUrlForLayer, BatchCheckLayerAvailability) ของ repo lab

นอกจากนี้มี EcrAdapter.delete_image สำหรับลบ lab image ตอนอาจารย์กดลบ
"""
import base64
from functools import cached_property

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.configs.settings import settings
from app.exceptions.domain import InternalServerError


def get_ecr_token(region: str) -> str:
    """คืน password สำหรับ `docker login -u AWS` (อายุ 12 ชม. เท่ากับ get-login-password)"""
    auth = boto3.client("ecr", region_name=region).get_authorization_token()
    token = auth["authorizationData"][0]["authorizationToken"]
    # authorizationToken = base64("AWS:<password>")
    return base64.b64decode(token).decode().split(":", 1)[1]


class EcrDeleteError(InternalServerError):
    code = "ecr_delete_failed"


class EcrAdapter:
    @cached_property
    def client(self):
        # .env ถูกอ่านเข้า settings ไม่ได้ export เป็น os.environ จึงส่ง key เข้า client ตรง ๆ
        # (ว่าง = ใช้ credential chain ปกติ)
        return boto3.client(
            "ecr",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ECR_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_ECR_SECRET_ACCESS_KEY,
        )

    def delete_image(self, repository: str, tag: str) -> None:
        """ลบ tag ออกจาก ECR แล้วลบ repository ถ้าว่าง — ไม่มี repo/tag อยู่แล้วถือว่าสำเร็จ

        ต้องมีสิทธิ์ ecr:BatchDeleteImage, ecr:ListImages, ecr:DeleteRepository บน repository/vlab/*
        """
        try:
            self.client.batch_delete_image(repositoryName=repository, imageIds=[{"imageTag": tag}])
            remaining = self.client.list_images(repositoryName=repository, maxResults=1)["imageIds"]
            if not remaining:
                self.client.delete_repository(repositoryName=repository)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "RepositoryNotFoundException":
                return
            code = error.response.get("Error", {}).get("Code", "Unknown")
            raise EcrDeleteError(f"Failed to delete {repository}:{tag} from ECR ({code})") from error
        except BotoCoreError as error:
            # เช่น NoCredentialsError, EndpointConnectionError, ConnectTimeoutError
            raise EcrDeleteError(
                f"Failed to delete {repository}:{tag} from ECR ({type(error).__name__})"
            ) from error


ecr_adapter = EcrAdapter()
