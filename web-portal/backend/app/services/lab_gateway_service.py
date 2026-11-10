"""lab gateway: ลิงก์ public ของ lab บน AWS (docs/AWS_LAB_PUBLIC_ACCESS_RUNBOOK.md 1A.4)

นักศึกษาเปิด https://l-<token>-<port>.<LAB_GATEWAY_DOMAIN> → Cloudflare → cloudflared → Traefik บน vlab-ts-router
→ Traefik ส่งต่อไป upstream จริง http://10.10.2.x:<port> ตามตาราง route ที่ดึงจาก backend

ไฟล์นี้มีแต่ฟังก์ชันล้วน (ไม่ต่อ DB / SkyPilot) ส่วนตาราง route ที่อ่าน DB อยู่ใน build_routes (runbook 1A.4 / A5)
"""
import base64
import ipaddress
import secrets
from typing import Iterable
from urllib.parse import urlparse

from app.configs.settings import settings

# 10 byte = 80 bit → base32 ได้ 16 ตัวพอดี (ไม่มี "=" ต่อท้าย) ใส่ใน gateway_token String(32) ได้
_TOKEN_BYTES = 10
TOKEN_LENGTH = 16


def new_token() -> str:
    """token ใหม่สำหรับ hostname ของ lab: base32 ตัวเล็ก 16 ตัว (a-z, 2-7)

    ลิงก์ lab ยังไม่มี login (forward-auth คือเฟส 3) ใครรู้ลิงก์ก็เข้าได้ token จึงเป็นกุญแจ
    ต้องสุ่มด้วย secrets (ไม่ใช่ random) และใช้ตัวอักษรที่ DNS label รับได้ (ไม่มีตัวใหญ่ / + / =)
    """
    return base64.b32encode(secrets.token_bytes(_TOKEN_BYTES)).decode("ascii").lower()


def port_allowed(port) -> bool:
    """พอร์ตอยู่ในช่วง LAB_GATEWAY_PORT_MIN–MAX ไหม (รับ int หรือ str จาก key ของ JSONB)

    กันพอร์ตอย่าง 22 / 80 ออกอินเทอร์เน็ต และต้องตรงกับช่วงที่ SG ของ router เปิดไว้
    ค่าที่ไม่ใช่ตัวเลข (None, "abc", "-1", True) = ไม่อนุญาต
    """
    if isinstance(port, bool):
        return False
    text = str(port).strip()
    if not text.isdigit():
        return False
    return settings.LAB_GATEWAY_PORT_MIN <= int(text) <= settings.LAB_GATEWAY_PORT_MAX


def public_host(token: str, port) -> str:
    """hostname ของ lab หนึ่งพอร์ต: l-<token>-<port>.<domain>

    ขึ้นต้น "l-" ให้ Cache Rule / Configuration Rule ของ Cloudflare จับได้ (runbook 1D ข้อ 7–8)
    และไม่ชนกับ record ที่มีชื่อชัดเจน เช่น skypilot / vlab
    """
    return f"l-{token}-{int(port)}.{settings.LAB_GATEWAY_DOMAIN}"


def public_endpoints(token: str, ports: Iterable) -> dict[str, str]:
    """ลิงก์ที่นักศึกษาเห็น {"8443": "https://l-<token>-8443.<domain>"} — พอร์ตนอกช่วงถูกตัดทิ้ง

    key เป็น str เสมอให้ตรงกับ endpoints เดิม (JSONB เก็บ key เป็น str)
    """
    return {str(int(p)): f"https://{public_host(token, p)}" for p in ports if port_allowed(p)}


def gateway_envs(token: str, ports: Iterable) -> dict[str, str]:
    """env ที่ส่งเข้า container ของ lab บน AWS (docker run -e) เมื่อ session นั้นผ่าน gateway

    - __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS: Vite (music-lab) ปฏิเสธ Host ที่ไม่รู้จัก ต้องอนุญาต .<domain>
      (Vite บางรุ่นอาจไม่อ่าน env นี้ — เช็กใน runbook 1F.0 ก่อนเปิด flag)
    - VLAB_PUBLIC_URL_<port>: URL public ของพอร์ตนั้น ให้ lab ที่ต้องรู้ URL ตัวเองเอาไปใช้
    """
    envs = {"__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS": f".{settings.LAB_GATEWAY_DOMAIN}"}
    envs.update({f"VLAB_PUBLIC_URL_{p}": url for p, url in public_endpoints(token, ports).items()})
    return envs


def upstream_ok(url: str) -> bool:
    """upstream ที่ Traefik จะส่งต่อปลอดภัยไหม: http, host เป็น IP ใน LAB_GATEWAY_UPSTREAM_CIDRS, พอร์ตในช่วง

    ด่านสุดท้ายก่อนใส่ตาราง route: ถ้าค่าใน DB เพี้ยน / ถูกแก้ router ต้องไม่กลายเป็นทางเข้าเครื่องอื่น
    ชื่อ host (ไม่ใช่ IP), ไม่มีพอร์ต, https, URL พัง = ไม่ผ่าน
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.port is None:
            return False
        ip = ipaddress.ip_address(parsed.hostname)
    except (ValueError, TypeError, AttributeError):
        return False
    if not port_allowed(parsed.port):
        return False
    return any(ip in net for net in settings.lab_gateway_upstream_cidrs)
