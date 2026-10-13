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
"""
import base64

import boto3


def get_ecr_token(region: str) -> str:
    """คืน password สำหรับ `docker login -u AWS` (อายุ 12 ชม. เท่ากับ get-login-password)"""
    auth = boto3.client("ecr", region_name=region).get_authorization_token()
    token = auth["authorizationData"][0]["authorizationToken"]
    # authorizationToken = base64("AWS:<password>")
    return base64.b64decode(token).decode().split(":", 1)[1]
