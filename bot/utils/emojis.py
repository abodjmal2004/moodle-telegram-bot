"""
Message Helpers — HTML Formatting + Regular Emojis
"""
from bot.utils.rich_text import Segment, build_rich_message

# ═══════════════════════════════════════════════════════════════
# Premium Custom Emoji IDs
# (لازم يكون عندك حساب Premium وقت الإنشاء، بس البوت نفسه ما بيحتاج
#  Premium حتى يرسلهم — أي بوت يقدر يرسل custom_emoji entities)
# ═══════════════════════════════════════════════════════════════
PREMIUM_EMOJI = {
    "star": "5453969572354878595",       # ⭐ نجمة
    "diamond": "4956719506027185156",    # 💎 ماسة
    "name_star": "5472427507842032538",  # ⭐ جنب الاسم بالترحيب
    "sticker": "5244710038320221456",    # ملصق لطيف
}


def build_premium_welcome_msg(name: str):
    """رسالة ترحيب فيها إيموجيات بريميوم + Bold، جاهزة للإرسال بـ
    entities= (مش parse_mode). يرجع (text, entities)."""
    segments = [
        Segment("⭐", custom_emoji_id=PREMIUM_EMOJI["name_star"]),
        Segment(f" Welcome {name} ", bold=True),
        Segment("⭐", custom_emoji_id=PREMIUM_EMOJI["name_star"]),
        Segment("\n\n"),
        Segment("📌 "),
        Segment("البوت بيقدملك:\n", bold=True),
        Segment("  📚 عرض موادك الدراسية\n"),
        Segment("  📝 الواجبات والمواعيد\n"),
        Segment("  📢 آخر الإعلانات\n"),
        Segment("  📊 الدرجات "),
        Segment("💎", custom_emoji_id=PREMIUM_EMOJI["diamond"]),
        Segment("\n\n"),
        Segment("👇 ", italic=True),
        Segment("اضغط للبدء:", italic=True),
        Segment("\n"),
        Segment("✨", custom_emoji_id=PREMIUM_EMOJI["sticker"]),
    ]
    return build_rich_message(segments)


def build_welcome_back_msg(name: str):
    """رسالة لوحة التحكم (مستخدم مسجل دخول) بإيموجيات بريميوم.
    يرجع (text, entities) — للإرسال بـ entities= بدون parse_mode."""
    segments = [
        Segment("👋 "),
        Segment(f"أهلاً بك يا {name}! ", bold=True),
        Segment("⭐", custom_emoji_id=PREMIUM_EMOJI["star"]),
        Segment("\n\n"),
        Segment("✅ أنت مسجل دخول حالياً.\n\n"),
        Segment("💎", custom_emoji_id=PREMIUM_EMOJI["diamond"]),
        Segment(" لوحة التحكم:", bold=True),
    ]
    return build_rich_message(segments)


def build_login_success_msg(name: str):
    """رسالة نجاح تسجيل الدخول بإيموجيات بريميوم.
    يرجع (text, entities) — للإرسال بـ entities= بدون parse_mode."""
    segments = [
        Segment("✨", custom_emoji_id=PREMIUM_EMOJI["sticker"]),
        Segment(f" أهلاً بك يا {name}! ", bold=True),
        Segment("💎", custom_emoji_id=PREMIUM_EMOJI["diamond"]),
        Segment("\n\n"),
        Segment("✅ تم تسجيل الدخول بنجاح.\n\n"),
        Segment("📚 /courses — عرض المواد\n"),
        Segment("⏰ /deadlines — المواعيد القادمة\n"),
        Segment("📊 /grades — الدرجات\n"),
        Segment("🚪 /logout — تسجيل الخروج"),
    ]
    return build_rich_message(segments)


# ═══════════════════════════════════════════════════════════════
# Regular Emojis (works with any bot, no Premium needed)
# ═══════════════════════════════════════════════════════════════
EMOJIS = {
    "welcome": "🌟",
    "diamond": "💎",
    "star": "⭐",
    "sparkle": "✨",
    "fire": "🔥",
    "rocket": "🚀",
    "crown": "👑",
    "medal": "🏅",
    "trophy": "🏆",
    "bell": "🔔",
    "book": "📚",
    "pencil": "📝",
    "megaphone": "📢",
    "chart": "📊",
    "clock": "⏰",
    "door": "🚪",
    "lock": "🔐",
    "key": "🔑",
    "check": "✅",
    "cross": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "arrow": "👇",
    "back": "🔙",
    "user": "👤",
    "calendar": "📅",
    "folder": "📂",
    "pin": "📌",
    "link": "🔗",
    "file": "📄",
    "question": "❓",
    "page": "📃",
    "label": "🏷️",
    "graduation": "🎓",
    "globe": "🌐",
    "video": "📹",
    "game": "🎮",
    "package": "📦",
    "clipboard": "📋",
    "gear": "🔧",
    "chat": "💬",
    "ban": "🚷",
    "mail": "📩",
    "wave": "👋",
    "smile": "😌",
    "party": "🎉",
    "sad": "😢",
}


def welcome_msg(name: str) -> str:
    """نسخة بديلة بسيطة (HTML، بدون إيموجي بريميوم) — للرجوع لها لو حبيت
    تشيل الاعتماد على premium emoji لاحقاً. مش مستخدمة حالياً بـ main.py."""
    return (
        f"{EMOJIS['welcome']} <b>Welcome {name}!</b> {EMOJIS['welcome']}\n\n"
        f"📌 <b>البوت بيقدملك:</b>\n"
        f"  {EMOJIS['book']} عرض موادك الدراسية\n"
        f"  {EMOJIS['pencil']} الواجبات والمواعيد\n"
        f"  {EMOJIS['megaphone']} آخر الإعلانات\n"
        f"  {EMOJIS['chart']} الدرجات\n\n"
        f"{EMOJIS['arrow']} <i>اضغط للبدء:</i>"
    )


def welcome_back_msg(name: str) -> str:
    """رسالة الترحيب للمستخدم المسجل دخول"""
    return (
        f"{EMOJIS['wave']} <b>أهلاً بك يا {name}!</b> {EMOJIS['star']}\n\n"
        f"{EMOJIS['check']} أنت مسجل دخول حالياً.\n\n"
        f"{EMOJIS['diamond']} <b>لوحة التحكم:</b>"
    )


def login_success_msg(name: str) -> str:
    """رسالة نجاح تسجيل الدخول"""
    return (
        f"{EMOJIS['sparkle']} <b>أهلاً بك يا {name}!</b> {EMOJIS['diamond']}\n\n"
        f"{EMOJIS['check']} تم تسجيل الدخول بنجاح.\n\n"
        f"{EMOJIS['book']} /courses — عرض المواد\n"
        f"{EMOJIS['clock']} /deadlines — المواعيد القادمة\n"
        f"{EMOJIS['chart']} /grades — الدرجات\n"
        f"{EMOJIS['door']} /logout — تسجيل الخروج"
    )


def banned_msg() -> str:
    """رسالة الحظر"""
    return f"{EMOJIS['ban']} <b>أنت محظور</b> من استخدام البوت."


def logout_msg() -> str:
    """رسالة تسجيل الخروج"""
    return (
        f"{EMOJIS['wave']} <b>تم تسجيل الخروج!</b> {EMOJIS['sparkle']}\n\n"
        f"🙏 شكراً لاستخدامك البوت.\n"
        f"{EMOJIS['lock']} /login — للدخول مرة ثانية"
    )


def course_menu_msg(course_name: str) -> str:
    """رسالة قائمة المادة"""
    return (
        f"{EMOJIS['book']} <b>{course_name}</b>\n\n"
        f"{EMOJIS['diamond']} <b>اختر اللي بدك إياه:</b>"
    )


def deadlines_msg() -> str:
    """رسالة المواعيد القادمة"""
    return f"{EMOJIS['clock']} <b>المواعيد القادمة</b> {EMOJIS['calendar']}"


def grades_msg() -> str:
    """رسالة الدرجات"""
    return f"{EMOJIS['chart']} <b>الدرجات</b> {EMOJIS['diamond']}"


def courses_list_msg() -> str:
    """رسالة قائمة المواد"""
    return (
        f"{EMOJIS['book']} <b>اختر المادة:</b> {EMOJIS['diamond']}\n\n"
        f"{EMOJIS['arrow']} <i>اضغط على المادة اللي بدك إياها:</i>"
    )


def no_courses_msg() -> str:
    return f"{EMOJIS['info']} <b>ما فيه مواد مسجلة حالياً.</b>"


def no_assignments_msg(course_name: str) -> str:
    return (
        f"{EMOJIS['book']} <b>{course_name}</b>\n\n"
        f"{EMOJIS['pencil']} <b>ما فيه واجبات حالياً.</b> {EMOJIS['sparkle']}"
    )


def no_announcements_msg(course_name: str) -> str:
    return (
        f"{EMOJIS['book']} <b>{course_name}</b>\n\n"
        f"{EMOJIS['megaphone']} <b>ما فيه إعلانات حالياً.</b> {EMOJIS['star']}"
    )


def no_content_msg(course_name: str) -> str:
    return (
        f"{EMOJIS['book']} <b>{course_name}</b>\n\n"
        f"{EMOJIS['folder']} <b>ما فيه محتوى متاح.</b> {EMOJIS['diamond']}"
    )


def no_grades_msg(course_name: str) -> str:
    return (
        f"{EMOJIS['book']} <b>{course_name}</b>\n\n"
        f"{EMOJIS['chart']} <b>ما فيه درجات متاحة.</b> {EMOJIS['star']}"
    )


def error_msg(error: str) -> str:
    return f"{EMOJIS['cross']} <b>خطأ:</b> {error}"


def login_prompt_msg() -> str:
    return (
        f"{EMOJIS['lock']} <b>أنت غير مسجل دخول!</b>\n\n"
        f"{EMOJIS['arrow']} اضغط هنا للدخول:\n"
        f"/login"
    )


def session_expired_msg() -> str:
    return (
        f"{EMOJIS['lock']} <b>انتهت صلاحية الجلسة!</b>\n\n"
        f"{EMOJIS['pencil']} الرجاء تسجيل الدخول من جديد:\n"
        f"/login"
    )


def no_deadlines_msg() -> str:
    return (
        f"{EMOJIS['party']} <b>ما فيه مواعيد قريبة!</b>\n\n"
        f"{EMOJIS['smile']} استمتع بوقتك الحر."
    )


def no_grades_overall_msg() -> str:
    return f"{EMOJIS['info']} <b>ما فيه درجات متاحة.</b>"


def prefs_msg() -> str:
    """رسالة تفضيلات الإشعارات لكل مادة"""
    return (
        f"{EMOJIS['gear']} <b>إشعارات المواد</b>\n"
        f"🔔 = مفعّلة | 🔕 = معطّلة"
    )


def toggle_ok_msg(course_name: str, now_enabled: bool) -> str:
    """رسالة تأكيد تغيير حالة إشعارات مادة."""
    state = "مفعّلة 🔔" if now_enabled else "معطّلة 🔕"
    return (
        f"{EMOJIS['book']} <b>{course_name}</b>\n"
        f"{EMOJIS['check']} إشعارات المادة صارت: {state}"
    )

