import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import Config
from bot.utils.emojis import build_welcome_back_msg
from bot.utils.telegram_helpers import safe_answer
from database.models import User

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def build_dashboard_keyboard(db_user: User) -> InlineKeyboardMarkup:
    notif_label = "🔕 إيقاف إشعارات الواجبات" if db_user.notifications_enabled else "🔔 تفعيل إشعارات الواجبات"
    rows = [
        [InlineKeyboardButton("📚 عرض المواد", callback_data="menu:courses")],
        [InlineKeyboardButton("⏰ المواعيد القادمة", callback_data="cmd:deadlines")],
        [InlineKeyboardButton("📊 الدرجات", callback_data="cmd:grades")],
        [InlineKeyboardButton(notif_label, callback_data="cmd:toggle_notify")],
    ]
    if Config.email_configured():
        email_label = "🔕 إيقاف إشعار الإيميل" if db_user.email_notifications_enabled else "📧 تفعيل إشعار الإيميل"
        rows.append([InlineKeyboardButton(email_label, callback_data="cmd:toggle_email_notify")])
    rows.append([InlineKeyboardButton("🚪 تسجيل الخروج", callback_data="cmd:logout")])
    return InlineKeyboardMarkup(rows)


async def _get_logged_in_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_session = context.bot_data['db_session']
    db_user = db_session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not db_user or not db_user.web_username:
        return None
    return db_user


async def toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    db_user = await _get_logged_in_user(update, context)
    if not db_user:
        await safe_answer(query, "🔐 لازم تسجل دخول أول.", show_alert=True)
        return

    db_user.notifications_enabled = not db_user.notifications_enabled
    context.bot_data['db_session'].commit()

    status = "✅ تفعّلت إشعارات الواجبات والإعلانات الجديدة." if db_user.notifications_enabled \
        else "🔕 اتوقفت إشعارات الواجبات والإعلانات."
    await safe_answer(query, status, show_alert=True)
    await _refresh_dashboard(update, context, db_user)


async def toggle_email_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    db_user = await _get_logged_in_user(update, context)
    if not db_user:
        await safe_answer(query, "🔐 لازم تسجل دخول أول.", show_alert=True)
        return
    if not db_user.email:
        await safe_answer(query, 
            "📧 لازم تضبط إيميلك أول:\nاكتب /email ثم إيميلك\n"
            "مثال: /email you@example.com",
            show_alert=True,
        )
        return

    db_user.email_notifications_enabled = not db_user.email_notifications_enabled
    context.bot_data['db_session'].commit()

    status = "✅ تفعّل الإشعار عبر الإيميل." if db_user.email_notifications_enabled \
        else "🔕 اتوقف الإشعار عبر الإيميل."
    await safe_answer(query, status, show_alert=True)
    await _refresh_dashboard(update, context, db_user)


async def set_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.email_configured():
        await update.message.reply_text(
            "⚠️ ميزة الإيميل مش مفعّلة على السيرفر حالياً (SMTP مش مضبوط)."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "✉️ استخدم الأمر هيك:\n<code>/email your@email.com</code>",
            parse_mode="HTML",
        )
        return

    email = context.args[0].strip()
    if not EMAIL_RE.match(email):
        await update.message.reply_text("❌ صيغة الإيميل مش صحيحة، تأكد وحاول كمان مرة.")
        return

    db_session = context.bot_data['db_session']
    db_user = db_session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not db_user or not db_user.web_username:
        await update.message.reply_text("🔐 لازم تسجل دخول أول بـ /start.")
        return

    db_user.email = email
    db_user.email_notifications_enabled = True
    db_session.commit()

    await update.message.reply_text(
        f"✅ تم ضبط إيميلك: <code>{email}</code>\n"
        f"رح توصلك نسخة من إشعارات الواجبات والإعلانات عليه كمان "
        f"(بجانب تليجرام). تقدر توقفها أي وقت من لوحة التحكم.",
        parse_mode="HTML",
    )


async def _refresh_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User):
    text, entities = build_welcome_back_msg(db_user.full_name or update.effective_user.first_name or "مستخدم")
    try:
        await update.callback_query.edit_message_text(
            text, entities=entities, reply_markup=build_dashboard_keyboard(db_user)
        )
    except Exception:
        pass  # الرسالة ممكن تكون نفسها بدون تغيير — تجاهل بهدوء
