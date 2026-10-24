"""
Mail Service — ส่งเมลผ่าน SMTP (Gmail App Password) ใช้แจ้งผลจองห้อง (docs/ADMIN_MONITOR.md PR 6)

ไม่ตั้ง SMTP_USER = ไม่ส่ง (คืน False ให้คนเรียกบันทึก skipped)
MAIL_REDIRECT_TO (ช่วงเทส) = ส่งทุกฉบับไปที่อยู่นี้ บอกผู้รับตัวจริงไว้บนสุดของเนื้อเมล
MAIL_ALLOWED_RECIPIENTS = ส่งได้เฉพาะในรายการ (ว่าง = ไม่มีใคร, "*" = ทุกคน) กันส่งหาคนจริงโดยไม่ตั้งใจ
แม้ลืมตั้ง redirect — ที่อยู่ใน MAIL_REDIRECT_TO ส่งได้เสมอ (ตั้งเองชัด ๆ)
"""
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.configs.settings import settings
from app.utils.logger import logger


def allowed(address: str) -> bool:
    """ผู้รับนี้อยู่ใน MAIL_ALLOWED_RECIPIENTS ไหม (เมลเต็ม / @โดเมน / *)"""
    address = address.strip().lower()
    if settings.MAIL_REDIRECT_TO and address == settings.MAIL_REDIRECT_TO.strip().lower():
        return True
    rules = [r.strip().lower() for r in settings.MAIL_ALLOWED_RECIPIENTS.split(",") if r.strip()]
    return any(r == "*" or r == address or (r.startswith("@") and address.endswith(r)) for r in rules)


def mail_enabled() -> bool:
    return bool(settings.SMTP_USER and settings.SMTP_PASSWORD)


def send_mail(to: list[str], subject: str, body: str) -> bool:
    """ส่งเมล plain text คืน False ถ้าไม่ได้ตั้ง SMTP (ไม่ส่ง) — ส่งไม่ผ่าน raise ให้คนเรียกบันทึก failed"""
    if not mail_enabled():
        logger.info(f"[mail] SMTP not configured, skip: {subject}")
        return False
    recipients = [a for a in to if a]
    if settings.MAIL_REDIRECT_TO:
        body = f"[ทดสอบ — ผู้รับจริง: {', '.join(recipients) or '-'}]\n\n{body}"
        recipients = [settings.MAIL_REDIRECT_TO]
    blocked = [a for a in recipients if not allowed(a)]
    if blocked:
        logger.warning(f"[mail] not in MAIL_ALLOWED_RECIPIENTS, dropped: {blocked}")
    recipients = [a for a in recipients if allowed(a)]
    if not recipients:
        raise ValueError(f"no allowed recipient (blocked: {', '.join(blocked) or '-'})")

    msg = EmailMessage()
    msg["From"] = formataddr((settings.MAIL_FROM_NAME, settings.SMTP_USER))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    logger.info(f"[mail] sent '{subject}' to {recipients}")
    return True
