"""
Email Notifications — عبر SMTP (Gmail) باستخدام smtplib المدمجة بـ Python.

ليش هاد الاختيار من بين الطرق يلي بحثت فيهم (SendGrid, Mailgun, SES...)؟
- مجاني بالكامل، ما بيحتاج مكتبة خارجية ولا API key لخدمة تالتة.
- Gmail بيسمح ~500 إيميل/يوم على حساب عادي — كافي جداً لعدد طلاب بوت جامعي.
- أبسط إعداد: فعّل 2-Step Verification على حساب Gmail، وولّد "App Password"
  من إعدادات الأمان (https://myaccount.google.com/apppasswords)، وحطه بـ
  SMTP_PASSWORD بـ .env (مش كلمة سر Gmail العادية — هاي ما بتشتغل).

smtplib مكتبة synchronous (blocking) — لو استدعيناها مباشرة جوا async
handler رح توقف كل البوت لحد ما الإيميل يتبعت. لهيك كل نداء بيصير جوا
asyncio.to_thread حتى يشتغل بخيط منفصل وما يعطل بقية المستخدمين.
"""
import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from email.header import Header

from bot.config import Config

logger = logging.getLogger(__name__)


def _send_sync(to_email: str, subject: str, body: str) -> None:
    msg = MIMEMultipart()
    msg["From"] = f"{Config.SMTP_FROM_NAME} <{Config.SMTP_USER}>"
    msg["To"] = to_email
    # Header(subject, 'utf-8') بيشفر الموضوع عربي (UTF-8) بشكل قياسي
    # (=?utf-8?Q?...?=) حتى يظهر صح بكل برامج الإيميل — الإسناد المباشر
    # لأسكي بيجيرم أحرف عربية كـ "=?unknown-8bit?..." بمكتبات كتيرة.
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15) as server:
        server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        server.send_message(msg)


async def send_email(to_email: str, subject: str, body: str) -> bool:
    """يرجع True لو انبعت، False لو فشل أو الإيميل مش مفعّل بالإعدادات."""
    if not Config.email_configured():
        logger.debug("SMTP not configured, skipping email to %s", to_email)
        return False
    try:
        await asyncio.to_thread(_send_sync, to_email, subject, body)
        return True
    except Exception as e:
        logger.error("Email send failed to %s: %s", to_email, e)
        return False
