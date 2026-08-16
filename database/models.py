from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text,
    Index, event,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from datetime import datetime, timezone

# datetime.utcnow() اتعمل deprecated بـ Python 3.12 — UTC صريحة بدلها.
# SQLAlchemy بتعامل datetime بأزمنة مختلفة صح، وهاد يخلي التحليلات
# (أوقات النشاط، أوقات الإشعارات) متسقة بدون غموض.

def _utcnow():
    return datetime.now(timezone.utc)


def _legacy_utcnow():
    """للسجلات القديمة اللي بتستثني timezone — ناخد UTC بدون timezone
    object حتى تبقى الأنواع متطابقة في عمود DateTime واحد."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100))
    web_username = Column(Text)
    web_password = Column(Text)
    full_name = Column(String(200))  # الاسم الكامل الرسمي من صفحة البروفايل بـ Moodle
    email = Column(String(200))
    notifications_enabled = Column(Boolean, default=False)        # إشعارات تليجرام للواجبات/الإعلانات الجديدة
    email_notifications_enabled = Column(Boolean, default=False)  # نفس الإشعارات كمان عالإيميل
    disabled_features = Column(Text)  # ميزات معطّلة لهذا المستخدم فقط — JSON list،
                                      # مثال: "[\"notifications\",\"email_notifications\"]" —
                                      # الأدمن بيضبطها عبر /tune بدون ما يعطّل الميزة
                                      # للبوت كامل.
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_legacy_utcnow)
    last_activity = Column(DateTime, default=_legacy_utcnow)

class TaskLog(Base):
    __tablename__ = "task_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    task_type = Column(String(50))
    status = Column(String(20))
    result = Column(Text)
    created_at = Column(DateTime, default=_legacy_utcnow)

class AdminAction(Base):
    __tablename__ = "admin_actions"
    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, nullable=False)
    action = Column(String(100))
    target_user_id = Column(Integer)
    details = Column(Text)
    created_at = Column(DateTime, default=_legacy_utcnow)

class SeenItem(Base):
    """يسجل كل واجب/إعلان اتبعت إشعار عنه لمستخدم معين، حتى ما نكرر نفس
    الإشعار مرتين. المفتاح (user_id, item_type, item_key) فريد."""
    __tablename__ = "seen_items"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)          # FK منطقي على users.id
    course_id = Column(String(50))
    item_type = Column(String(20), nullable=False)     # 'assignment' أو 'announcement'
    item_key = Column(String(500), nullable=False)      # assignment_id أو رابط الإعلان
    notified_at = Column(DateTime, default=_legacy_utcnow)

    __table_args__ = (
        Index("ix_seen_items_lookup", "user_id", "item_type", "item_key", unique=True),
    )

class CoursePref(Base):
    """تفضيلات الإشعارات لكل مادة على حدة — المستخدم قادر يوقف إشعارات مادة
    معينة (مثلاً مادة ما فيها واجبات كتير) بدون ما يوقف إشعارات باقي المواد.
    المفتاح (user_id, course_id) فريد: سطر واحد لكل مادة لكل مستخدم."""
    __tablename__ = "course_prefs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)            # FK منطقي على users.id
    course_id = Column(String(50), nullable=False)        # course_id من /course/view.php?id=XX
    course_name = Column(String(300))                     # cached — حتى ما نرجع لمودل لكل عرض
    notif_enabled = Column(Boolean, default=True)         # الإشعارات على هالمادة مفعلّة؟
    updated_at = Column(DateTime, default=_legacy_utcnow)

    __table_args__ = (
        Index("ix_course_prefs_lookup", "user_id", "course_id", unique=True),
    )

class BotAdmin(Base):
    """قائمة الإداريين للبوت — يتيح إضافة/إزالة أدمنية برمجياً بدل تعديل .env."""
    __tablename__ = "bot_admins"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    added_by = Column(Integer)  # telegram_id للأدمن اللي أضافه
    created_at = Column(DateTime, default=_legacy_utcnow)

class BotSetting(Base):
    """إعدادات البوت العالمية (مثل وضع الصيانة، تفعيل ميزات معينة عالمياً)."""
    __tablename__ = "bot_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text)  # JSON أو نص عادي
    updated_at = Column(DateTime, default=_legacy_utcnow, onupdate=_legacy_utcnow)


def init_db(database_url: str):
    is_sqlite = database_url.startswith("sqlite")

    if is_sqlite:
        # SQLite: pool_size/max_overflow مش منطقيين هون (ملف واحد، مش
        # سيرفر شبكة)، فبنفعّل WAL mode بدلاً منها — بيسمح بقراءة وكتابة
        # متزامنين بدون ما يقفل الجدول بالكامل، وده أهم تحسين أداء ممكن
        # لـ SQLite تحت حمل مستخدمين متعددين.
        engine = create_engine(database_url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        # Postgres/MySQL: connection pooling حقيقي لتحمل عدد أكبر من
        # المستخدمين المتزامنين بدون ما نفتح اتصال جديد كل مرة.
        engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,   # يتجنب استخدام اتصالات ماتت (connection dropped)
            pool_recycle=1800,
        )

    Base.metadata.create_all(engine)

    if is_sqlite:
        # SQLite ما بيعمل ALTER TABLE ADD COLUMN للـ DEFAULT بسهولة مع
        # create_all، فبنضيف الأعمدة الجديدة يدويًا لو مش موجودة — يخلي
        # الترقية من قاعدة بيانات قديمة تشتغل بدون ما نمسح bot.db.
        with engine.connect() as conn:
            for col_sql in (
                "ALTER TABLE users ADD COLUMN disabled_features TEXT",
            ):
                try:
                    conn.execute(_sql(col_sql))
                    conn.commit()
                except Exception:
                    conn.rollback()  # العمود موجود فعلًا (أو خطأ آخر)
    
    # التأكد من وجود أدمن أولي لو كان .env معرف
    from bot.config import Config
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        for admin_id in Config.ADMIN_IDS:
            existing = session.query(BotAdmin).filter_by(telegram_id=admin_id).first()
            if not existing:
                session.add(BotAdmin(telegram_id=admin_id))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()

    return sessionmaker(bind=engine)


def _sql(text: str):
    from sqlalchemy import text as _t
    return _t(text)