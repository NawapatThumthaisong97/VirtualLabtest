"""
Thammasat University Active Directory Verify API Adapter
Handles authentication against https://restapi.tu.ac.th/api/v1/auth/Ad/verify
"""
from dataclasses import dataclass
from typing import Optional
import requests

from app.configs.settings import settings
from app.utils.logger import logger


@dataclass
class TUUserInfo:
    username: str
    type: str  # "student" | "employee"
    displayname_th: Optional[str]
    displayname_en: Optional[str]
    email: str
    department: Optional[str] = None
    faculty: Optional[str] = None
    organization: Optional[str] = None

    @property
    def display_name(self) -> str:
        return (
            (self.displayname_th or "").strip()
            or (self.displayname_en or "").strip()
            or self.username
        )

    @property
    def is_student(self) -> bool:
        return self.type.lower() == "student"


class TUAuthAdapter:
    def __init__(self, api_url: Optional[str] = None, app_key: Optional[str] = None):
        self.api_url = api_url or settings.TU_API_URL
        self.app_key = app_key or settings.TU_API_APP_KEY

    def _call_tu_api(self, login_id: str, password: str) -> tuple[bool, dict]:
        headers = {
            "Content-Type": "application/json",
            "Application-Key": self.app_key or "",
        }
        payload = {
            "UserName": login_id.strip(),
            "PassWord": password,
        }

        try:
            print(f"[TU Auth API] Requesting verification for: {login_id}", flush=True)
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=10,
            )
            data = response.json() if response.content else {}
            print(f"[TU Auth API] Response: {response.status_code} - {data}", flush=True)
            return (data.get("status") is True, data)
        except Exception as e:
            print(f"[TU Auth API] Request error: {e}", flush=True)
            logger.error(f"Failed to connect to TU AD verify API: {e}")
            return (False, {"message": str(e)})

    def verify_credentials(self, username: str, password: str) -> Optional[TUUserInfo]:
        """
        ส่งคำขอไปตรวจสอบรหัสผ่านกับระบบ Active Directory ของมหาวิทยาลัยธรรมศาสตร์
        รองรับทั้ง:
        - เลขทะเบียนนักศึกษา เช่น 66xxxxxxxx
        - Username เช่น first.l
        - Email เช่น first.l@dome.tu.ac.th (จะลองทั้งแบบมีและไม่มีโดเมน)
        """
        if not self.app_key:
            print("[TU Auth API] TU_API_APP_KEY is not configured!", flush=True)
            logger.warning("TU_API_APP_KEY is not configured; skipping TU AD verify.")
            return None

        clean_user = username.strip()
        candidates = [clean_user]

        # ถ้าส่งมาเป็น email ให้เพิ่ม version ที่ตัด domain ออกด้วย
        if "@" in clean_user:
            prefix = clean_user.split("@")[0].strip()
            if prefix and prefix not in candidates:
                candidates.append(prefix)
        else:
            # ถ้าส่งมาเป็น username ธรรมดาที่ไม่มี @ และไม่ใช่เลขล้วน ลองเพิ่ม @dome.tu.ac.th เป็นทางเลือกสำรอง
            if not clean_user.isdigit():
                candidates.append(f"{clean_user}@dome.tu.ac.th")

        for cand in candidates:
            success, data = self._call_tu_api(cand, password)
            if success:
                logger.info(f"TU AD authentication successful for: {cand}")
                resolved_user = str(data.get("username", cand)).strip()
                email = data.get("email")
                if not email:
                    email = (
                        f"{resolved_user}@dome.tu.ac.th"
                        if str(data.get("type")).lower() == "student"
                        else f"{resolved_user}@tu.ac.th"
                    )

                return TUUserInfo(
                    username=resolved_user,
                    type=str(data.get("type", "student")).lower(),
                    displayname_th=data.get("displayname_th"),
                    displayname_en=data.get("displayname_en"),
                    email=email,
                    department=data.get("department"),
                    faculty=data.get("faculty"),
                    organization=data.get("organization"),
                )

        print(f"[TU Auth API] All candidates failed for user input: {username}", flush=True)
        return None


tu_auth_adapter = TUAuthAdapter()
