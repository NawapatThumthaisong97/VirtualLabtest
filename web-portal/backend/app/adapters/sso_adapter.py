"""
SSO Adapter (Google OAuth2 / OIDC)
เชื่อมต่อกับระบบ SSO ของมหาวิทยาลัย (เช่น Google OAuth2) เพื่อสร้าง URL ล็อกอิน,
แลก authorization code เป็น token และดึงข้อมูลโปรไฟล์ของผู้ใช้ที่ยืนยันตัวตนแล้ว
"""
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.configs.settings import settings
from app.exceptions.domain import SSOAuthenticationError


@dataclass
class SSOUserInfo:
    """ข้อมูลผู้ใช้ที่ได้จากระบบ SSO หลังล็อกอินสำเร็จ"""

    email: str
    name: str
    email_verified: bool = True
    student_id: str | None = None
    hd: str | None = None


class GoogleSSOAdapter:
    """Adapter สำหรับติดต่อ Google OAuth2 / OIDC ของมหาวิทยาลัย"""

    def build_authorization_url(
        self,
        state: str | None = None,
        redirect_uri: str | None = None,
    ) -> str:
        if not settings.GOOGLE_CLIENT_ID:
            raise SSOAuthenticationError("ยังไม่ได้ตั้งค่า GOOGLE_CLIENT_ID สำหรับระบบ SSO")

        params: dict[str, str] = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
        }
        domains = settings.allowed_email_domains
        if domains:
            params["hd"] = domains[0]
        if state:
            params["state"] = state

        return f"{settings.GOOGLE_AUTH_URI}?{urlencode(params)}"

    def exchange_code(
        self,
        code: str,
        redirect_uri: str | None = None,
    ) -> SSOUserInfo:
        """แลก OAuth2 authorization code เป็น access_token / id_token แล้วดึงข้อมูลผู้ใช้"""
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise SSOAuthenticationError(
                "ยังไม่ได้ตั้งค่า GOOGLE_CLIENT_ID หรือ GOOGLE_CLIENT_SECRET สำหรับระบบ SSO"
            )

        token_payload = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                token_resp = client.post(settings.GOOGLE_TOKEN_URI, data=token_payload)
        except httpx.HTTPError as exc:
            raise SSOAuthenticationError("ไม่สามารถเชื่อมต่อกับระบบ SSO ได้") from exc

        if token_resp.status_code != 200:
            raise SSOAuthenticationError("รหัสยืนยันตัวตน (authorization code) จาก SSO ไม่ถูกต้องหรือหมดอายุ")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")

        if access_token:
            return self.fetch_user_info(access_token)
        if id_token:
            return self.verify_id_token(id_token)

        raise SSOAuthenticationError("ไม่ได้รับ token จากระบบ SSO")

    def verify_id_token(self, id_token: str) -> SSOUserInfo:
        """ตรวจสอบ Google ID Token ผ่าน endpoint tokeninfo"""
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    settings.GOOGLE_TOKENINFO_URI,
                    params={"id_token": id_token},
                )
        except httpx.HTTPError as exc:
            raise SSOAuthenticationError("ไม่สามารถเชื่อมต่อกับระบบ SSO เพื่อตรวจสอบ id_token ได้") from exc

        if resp.status_code != 200:
            raise SSOAuthenticationError("id_token จากระบบ SSO ไม่ถูกต้องหรือหมดอายุ")

        data = resp.json()
        if settings.GOOGLE_CLIENT_ID and data.get("aud") != settings.GOOGLE_CLIENT_ID:
            raise SSOAuthenticationError("id_token ไม่ได้ออกให้กับแอปพลิเคชันนี้ (invalid audience)")

        return self._parse_profile(data)

    def fetch_user_info(self, access_token: str) -> SSOUserInfo:
        """ดึงข้อมูลผู้ใช้จาก Google OIDC userinfo endpoint ด้วย access_token"""
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    settings.GOOGLE_USERINFO_URI,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            raise SSOAuthenticationError("ไม่สามารถดึงข้อมูลผู้ใช้จากระบบ SSO ได้") from exc

        if resp.status_code != 200:
            raise SSOAuthenticationError("access_token จากระบบ SSO ไม่ถูกต้องหรือหมดอายุ")

        return self._parse_profile(resp.json())

    @staticmethod
    def _parse_profile(data: dict) -> SSOUserInfo:
        email = str(data.get("email") or "").strip()
        if not email:
            raise SSOAuthenticationError("ไม่พบข้อมูลอีเมลจากระบบ SSO")

        raw_verified = data.get("email_verified", True)
        if isinstance(raw_verified, str):
            email_verified = raw_verified.lower() == "true"
        else:
            email_verified = bool(raw_verified)

        name = str(data.get("name") or data.get("given_name") or "").strip()
        if not name:
            name = email.split("@", 1)[0]

        hd = data.get("hd")
        return SSOUserInfo(
            email=email,
            name=name,
            email_verified=email_verified,
            hd=str(hd) if hd else None,
        )


sso_adapter = GoogleSSOAdapter()
