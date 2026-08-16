"""
تفضيلات الإشعارات لكل مادة على حدة — /prefs و /togglecourse
─────────────────────────────────────────────────────────────────
الإشعارات الدورية بتفحص واجبات/إعلانات جديدة بكل المواد — بس أحياناً
المستخدم بدو يوقف إشعارات مادة معينة (مثلاً مادة ما فيها واجبات كتير
أو مادة اختيارية) بدون ما يوقف إشعارات باقي المواد.

المستخدم قادر يشوف كل المواد اللي عنده مع حالة الإشعارات على كل وحدة،
ويعكس حالة أي مادة بأمر واحد (/togglecourse <رقم>). التفضيلات بتنحفظ
بجدول course_prefs بالداتابيز وبتتطبق فوراً على جوب الإشعارات.
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import Config
from bot.services.moodle_client import get_client
from bot.utils.emojis import prefs_msg, toggle_ok_msg
from bot.utils.html_escape import esc
from bot.utils.telegram_helpers import safe_answer
from database.models import User, CoursePref

logger = logging.getLogger(__name__)


async def _get_course_prefs(db_session, user_id: int):
    """جلب تفضيلات المستخدم من الداتابيز كـ dict {course_id: enabled}."""
    prefs = db_session.query(CoursePref).filter_by(user_id=user_id).all()
    return {p.course_id: p.notif_enabled for p in prefs}


def _is_course_notif_enabled(db_session, user_id: int, course_id: str) -> bool:
    """هل إشعارات هالمادة مفعلّة للمستخدم؟ (غياب السطر = مفعل افتراضياً)"""
    pref = (
        db_session.query(CoursePref)
        .filter_by(user_id=user_id, course_id=course_id)
        .first()
    )
    return pref.notif_enabled if pref else True


def is_user_feature_enabled(user: User, feature: str) -> bool:
    """هل الميزة مفعّلة لهذا المستخدم؟ بتدمج:
    1)FEATURES_* العامة (.env) — لو المعطّلة عالمياً، ما في استخدام أصلاً
    2)الأدمن عبر /tune — بتخزن disabled_features كـ JSON list
    3)إعدادات المستخدم نفسه (notifications_enabled...)"""
    if not Config.feature_enabled(feature):
        return False
    if user and user.disabled_features:
        import json
        try:
            disabled = json.loads(user.disabled_features) or []
        except (TypeError, ValueError):
            disabled = []
        if feature in disabled:
            return False
    return True


async def cmd_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/prefs — عرض مواد المستخدم مع حالة الإشعارات على كل مادة.
    الأرقام المعروضة بتستخدم بـ /togglecourse <رقم>."""
    if not is_user_feature_enabled(None, "per_course_notif"):
        await update.message.reply_text("⛔ هالميزة معطّلة بالإعدادات العامة للبوت.")
        return

    if not Config.feature_enabled("notifications"):
        await update.message.reply_text(
            "ℹ️ الإشعارات الدورية معطّلة بالبوت — فعّل FEATURES_NOTIFICATIONS=1 "
            "حتى تشتغل تفضيلات المواد."
        )
        return

    user_id = update.effective_user.id
    db_session = context.bot_data['db_session']
    db_user = db_session.query(User).filter_by(telegram_id=user_id).first()

    if not db_user or not db_user.web_username:
        await update.message.reply_text("🔐 <b>سجّل دخول أولاً:</b> /login", parse_mode="HTML")
        return

    # جلب مواد المستخدم (من الكاش لو موجود — نفس مصادر show_courses)
    courses = context.user_data.get('courses_cache')
    if not courses:
        client = get_client(user_id)
        courses = await client.get_courses()
        if courses:
            context.user_data['courses_cache'] = courses
    if not courses:
        await update.message.reply_text("📭 ما لقيتش مواد عندك.", parse_mode="HTML")
        return

    prefs = await _get_course_prefs(db_session, user_id)

    lines = [f"{prefs_msg()}\n"]
    for i, c in enumerate(courses, start=1):
        cid = str(c.get("id") or c.get("course_id") or "")
        enabled = prefs.get(cid, True)
        icon = "🔔" if enabled else "🔕"
        lines.append(f"{i}. {icon} <b>{esc(c['name'])}</b>")
    lines.append("\n💡 غيّر حالة مادة: /togglecourse <رقم>")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n…"
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_toggle_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/togglecourse <رقم> — يعكس حالة إشعارات المادة بالترتيب اللي ظهر بـ /prefs.
    المادة 3 مثلاً: /togglecourse 3 — لو مفعلّة بتصير معطّلة والعكس."""
    if not Config.feature_enabled("notifications"):
        await update.message.reply_text("ℹ️ الإشعارات معطّلة بالبوت.")
        return

    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "الاستخدام: /togglecourse <رقم>\n"
            "شوف أرقام المواد بـ /prefs قبل."
        )
        return

    db_session = context.bot_data['db_session']
    courses = context.user_data.get('courses_cache')
    if not courses:
        await update.message.reply_text("📋 شوف المواد أول عبر /prefs.")
        return

    try:
        index = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("❌ <b>رقم المادة لازم يكون رقم.</b>", parse_mode="HTML")
        return

    if not (0 <= index < len(courses)):
        await update.message.reply_text(
            f"❌ <b>رقم غير صالح</b> — عندك {len(courses)} مادة."
        )
        return

    course = courses[index]
    cid = str(course.get("id") or course.get("course_id") or "")
    prefs = await _get_course_prefs(db_session, user_id)
    currently = prefs.get(cid, True)
    new_state = not currently

    # upsert — لو السطر موجود نعدّله، وإلا نضيف سطر جديد
    pref = (
        db_session.query(CoursePref)
        .filter_by(user_id=user_id, course_id=cid)
        .first()
    )
    if pref is None:
        pref = CoursePref(user_id=user_id, course_id=cid)
        db_session.add(pref)
    pref.notif_enabled = new_state
    pref.course_name = course["name"]
    db_session.commit()

    await update.message.reply_text(
        toggle_ok_msg(course["name"], new_state),
        parse_mode="HTML",
    )
    logger.info(
        "user %d toggled course %s notif -> %s",
        user_id, cid, "on" if new_state else "off",
    )
