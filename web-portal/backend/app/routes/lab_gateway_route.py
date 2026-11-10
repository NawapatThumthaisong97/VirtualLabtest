"""lab gateway: ตาราง route ให้ Traefik บน vlab-ts-router (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md 1A.5)

Traefik (HTTP provider) ดึง GET /api/internal/v1/gateway/routes ทุก 5 วิ ผ่าน Tailscale พร้อม header X-Gateway-Token
backend ไม่เคยเรียก router — router เป็นฝ่ายมาถาม (pull)
"""
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.configs.settings import settings
from app.services.lab_gateway_service import build_routes

# ไม่อยู่ใน OpenAPI / ไม่ใช้ JWT (Traefik ไม่มี user) ใช้ token ร่วมอย่างเดียว
router = APIRouter(prefix="/internal/v1/gateway", include_in_schema=False)


def _token_ok(given: Optional[str]) -> bool:
    expected = settings.LAB_GATEWAY_TOKEN
    if not settings.LAB_GATEWAY_ENABLED or not expected or not given:
        return False
    # compare_digest: เวลาเทียบไม่ขึ้นกับว่าตรงกี่ตัวแรก (กันเดา token ทีละตัวจากเวลาตอบ)
    return hmac.compare_digest(given.encode(), expected.encode())


@router.get("/routes")
def gateway_routes(
    x_gateway_token: Optional[str] = Header(None, alias="X-Gateway-Token"),
    db: Session = Depends(get_db),
):
    """dynamic config ของ Traefik — คืน dict ตรง ๆ ไม่ห่อ ApiResponse (Traefik อ่านรูปแบบของมันเอง)

    flag ปิด / ไม่มี token / token ผิด = 404 เหมือนไม่มี endpoint นี้ (ไม่บอกว่ามีอยู่แต่ token ผิด)
    """
    if not _token_ok(x_gateway_token):
        raise HTTPException(status_code=404, detail="Not Found")
    return build_routes(db)
