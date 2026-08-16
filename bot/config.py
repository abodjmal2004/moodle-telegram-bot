import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()


class Config:
    # ─── Telegram ───
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
    
    # ─── Database ───
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")
    
    # ─── Moodle ───
    BASE_URL = os.getenv("BASE_URL", "https://moodle.alaqsa.edu.ps")
    REQUEST_TIMEOUT = 30
    
    # ─── Security ───
    MAX_REQUESTS_PER_MINUTE = 20

    # ─── Feature Toggles ───
    # كل ميزة بالبوت (بما فيها لوحة الأدمن والإشعارات) تقدر تتعطل من .env
    # بدون ما نعدل الكود: 1 = مفعّلة، 0 = معطّلة.
    # مثال: FEATURES_NOTIFICATIONS=0 عشان تعطل جوب الإشعارات الدورية.
    _DEFAULT_FEATURES = {
        "courses": True,
        "content": True,
        "news": True,
        "assignments": True,
        "deadlines": True,
        "grades": True,
        "notifications": True,     # جوب فحص الواجبات/الإعلانات الجديدة
        "per_course_notif": True,  # إشعارات لكل مادة على حدة (إيقاف/تفعيل مادة)
        "email_notifications": True,
        "auto_relogin": True,      # إعادة تسجيل دخول تلقائي عند انتهاء الجلسة
        "rate_limit": True,
        "admin_panel": True,       # أوامر الأدمن (/stats, /ban, /broadcast...)
    }

    @classmethod
    def feature_enabled(cls, name: str) -> bool:
        env_val = os.getenv(f"FEATURES_{name.upper()}")
        if env_val is not None:
            return env_val.strip().lower() in ("1", "true", "yes", "on")
        return cls._DEFAULT_FEATURES.get(name, False)

    @classmethod
    def feature_summary(cls) -> str:
        """ملخص حالة الميزات عند إقلاع البوت (للـ logs)."""
        lines = [f"  {n}: {'✅' if cls.feature_enabled(n) else '⛔'}"
                 for n in cls._DEFAULT_FEATURES]
        return "📋 Feature flags:\n" + "\n".join(lines)
    
    # ─── Encryption ───
    # Fernet key لازم يكون 32 بايت base64-encoded url-safe
    _raw_key = os.getenv("ENCRYPTION_KEY", "").strip()
    
    if not _raw_key:
        # ولو فاضي — نولّد واحد جديد
        _raw_key = Fernet.generate_key().decode()
        print(f"\n{'='*60}")
        print("[WARNING] ENCRYPTION_KEY not set in .env!")
        print(f"[WARNING] Generated temporary key: {_raw_key}")
        print("[WARNING] Add this line to your .env file:")
        print(f"ENCRYPTION_KEY={_raw_key}")
        print(f"{'='*60}\n")
    else:
        # نتحقق إنه مفتاح Fernet صحيح
        try:
            Fernet(_raw_key.encode())
        except ValueError:
            # لو مش صحيح — نولّد واحد جديد
            print(f"\n{'='*60}")
            print(f"[WARNING] Invalid ENCRYPTION_KEY: '{_raw_key[:20]}...'")
            print("[WARNING] Fernet key must be 32 url-safe base64-encoded bytes.")
            _raw_key = Fernet.generate_key().decode()
            print(f"[WARNING] Generated new key: {_raw_key}")
            print("[WARNING] Add this line to your .env file:")
            print(f"ENCRYPTION_KEY={_raw_key}")
            print(f"{'='*60}\n")
    
    ENCRYPTION_KEY = _raw_key
    
    # ─── Admin Panel ───
    ADMIN_PANEL_PORT = int(os.getenv("ADMIN_PANEL_PORT", "5000"))
    ADMIN_PANEL_SECRET = os.getenv("ADMIN_PANEL_SECRET", "change-me-in-production")

    # ─── Email (SMTP) ───
    # جرّبنا كذا طريقة (SendGrid، Mailgun، AWS SES...)، بس SMTP المدمج
    # بـ Python (smtplib) + Gmail هو الأنسب هون: مجاني بالكامل، ما بيحتاج
    # مكتبة خارجية، وكافي لعدد الطلاب المتوقع (Gmail بيسمح ~500 إيميل/يوم
    # على الحساب العادي، وهاد أكتر من كافي لبوت جامعي).
    # ملاحظة: لازم "App Password" مش كلمة سر Gmail العادية (لازم تفعّل
    # 2-Step Verification بحسابك، وبعدين تولّد App Password من إعدادات Google).
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "SoNs Bot")

    # ─── Notifications job ───
    NOTIFICATION_CHECK_INTERVAL_MINUTES = int(os.getenv("NOTIFICATION_CHECK_INTERVAL_MINUTES", "20"))
    NOTIFICATION_CONCURRENCY = int(os.getenv("NOTIFICATION_CONCURRENCY", "3"))  # عدد جلسات Moodle المتوازية أثناء الفحص

    @classmethod
    def email_configured(cls) -> bool:
        return bool(cls.SMTP_USER and cls.SMTP_PASSWORD)

    @classmethod
    def validate(cls):
        """التحقق من الإعدادات الضرورية."""
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is missing!")
        if errors:
            raise RuntimeError("\n".join(errors))
        if not cls.email_configured():
            print("[INFO] SMTP not configured — email notifications disabled "
                  "(set SMTP_USER/SMTP_PASSWORD in .env to enable).")
        print(cls.feature_summary())