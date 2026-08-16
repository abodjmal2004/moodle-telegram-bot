import asyncio
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import scoped_session

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    TypeHandler, ApplicationHandlerStop,
)

from bot.config import Config
from bot.handlers.auth import login_conv
from bot.handlers.tasks import (
    show_courses, show_course_menu, back_to_courses,
    show_assignments, show_announcements, show_course_content, show_course_grades,
    cmd_assignments, cmd_content, cmd_news, cmd_deadlines,
    show_grades, do_logout
)
from bot.handlers.admin import (
    admin_stats, ban_user, unban_user, user_info, admin_logs, broadcast,
    user_find, tune_user, bot_health,
    cmd_admin, admin_callback_handler, add_admin, del_admin,
    is_admin as check_admin_permission, get_setting
)
from bot.handlers.preferences import (
    cmd_prefs, cmd_toggle_course,
)
from bot.handlers.notifications import (
    build_dashboard_keyboard, toggle_notifications, toggle_email_notifications, set_email,
)
from bot.middlewares.rate_limit import rate_limiter
from bot.services.notifier import check_new_items_job
from bot.utils.emojis import (
    banned_msg, logout_msg,
    build_premium_welcome_msg, build_welcome_back_msg,
)
from bot.utils.telegram_helpers import safe_answer
from database.models import init_db, User

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Welcome Image
# ملاحظة مهمة: الرابط اللي قبله (https://ibb.co/wZDH6bHC) كان رابط
# صفحة HTML مش صورة مباشرة — send_photo بيرفضه بخطأ 400. الرابط
# الصحيح هو i.ibb.co المباشر، ومع fallback محلي لو السيرفر ما اشتغل.
# ═══════════════════════════════════════════════════════════════
WELCOME_IMAGE = "https://i.ibb.co/SDqTv1T0/photo-2026-08-09-22-51-05.jpg"
WELCOME_IMAGE_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welcome.jpg")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_session = context.bot_data['db_session']
    db_user = db_session.query(User).filter_by(telegram_id=user.id).first()

    # Check if banned
    if db_user and db_user.is_banned:
        text = banned_msg() + "\n\n📩 تواصل مع الإدارة للاستفسار."
        await update.message.reply_text(text, parse_mode="HTML")
        return

    # Check if logged in
    if db_user and db_user.web_username:
        # Logged in - show dashboard
        display_name = db_user.full_name or user.first_name or "مستخدم"
        text, entities = build_welcome_back_msg(display_name)

        await update.message.reply_text(
            text,
            reply_markup=build_dashboard_keyboard(db_user),
            entities=entities,
        )
    else:
        # Not logged in - photo + caption + buttons TOGETHER
        text, entities = build_premium_welcome_msg(user.first_name or "زائر")

        keyboard = [
            [InlineKeyboardButton("🔐 تسجيل الدخول", callback_data="cmd:login")],
        ]

        await _send_welcome_photo(
            context, update.effective_chat.id, text, entities,
            InlineKeyboardMarkup(keyboard),
        )


async def global_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بوابة الحماية العالمية (group=-1): تعالج وضع الصيانة، تفعيل الميزات، والـ Rate Limiting."""
    user = update.effective_user
    if user is None:
        return

    # 1. التحقق من رتبة المستخدم (أدمن أم لا)
    is_admin = await check_admin_permission(user.id, context)

    # 2. وضع الصيانة (Maintenance Mode)
    m_mode = await get_setting("maintenance_mode", "0", context)
    if m_mode == "1" and not is_admin:
        text = "🛠️ <b>عذراً، البوت في وضع الصيانة حالياً.</b>\nنحن نقوم ببعض التحديثات وسنعود قريباً جداً."
        if update.callback_query:
            await safe_answer(update.callback_query, "🛠️ البوت في وضع الصيانة حالياً.", show_alert=True)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML")
        raise ApplicationHandlerStop

    # 3. الـ Rate Limiting (فقط لغير الأدمنية)
    if Config.feature_enabled("rate_limit") and not is_admin:
        if await rate_limiter.check(user.id):
            if update.callback_query:
                await safe_answer(update.callback_query, "⏳ كثرت الطلبات! انتظر شوي.", show_alert=True)
            elif update.message:
                await update.message.reply_text("⏳ <b>كثرت الطلبات!</b> انتظر دقيقة وحاول مرة ثانية.", parse_mode="HTML")
            raise ApplicationHandlerStop

    # 4. فحص الميزات العالمية (مثلاً لو الأدمن عطل ميزة الواجبات للكل)
    # ملاحظة: هذا الفحص يتم داخل كل handler لاحقاً بناءً على نوع الطلب.
    pass


async def cleanup_db_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يشتغل بعد كل التحديثات (group=999) لتحرير الـ session المرتبطة بهذا الـ task."""
    context.bot_data['db_session'].remove()


# Handle dashboard buttons
async def handle_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data.split(":")[1]
    chat_id = query.message.chat_id

    if action == "login":
        await safe_answer(query)
        # Delete photo message and send new text
        try:
            await query.delete_message()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text="🔐 <b>تسجيل الدخول</b>\n\n"
                 "👤 أرسل الأمر:\n"
                 "/login",
            parse_mode="HTML"
        )
        return
    if action == "deadlines":
        await safe_answer(query)
        await cmd_deadlines(update, context)
    elif action == "grades":
        await safe_answer(query)
        await show_grades(update, context)
    elif action == "logout":
        await safe_answer(query)
        await do_logout(update, context)
    elif action == "toggle_notify":
        await toggle_notifications(update, context)
    elif action == "toggle_email_notify":
        await toggle_email_notifications(update, context)


async def _setup_application():
    """تجهيز الـ application بالكامل مع كل الـ handlers والـ jobs."""
    Config.validate()

    SessionFactory = init_db(Config.DATABASE_URL)
    # scoped_session تعطي كل update (asyncio task) نسخة session معزولة.
    db_session = scoped_session(SessionFactory, scopefunc=asyncio.current_task)

    application = Application.builder().token(Config.BOT_TOKEN).build()
    application.bot_data['db_session'] = db_session

    # Middleware & Handlers
    application.add_handler(TypeHandler(Update, global_gate), group=-1)
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(login_conv)
    application.add_handler(CommandHandler('logout', do_logout))
    application.add_handler(CommandHandler('email', set_email))
    application.add_handler(CommandHandler('courses', show_courses))
    application.add_handler(CommandHandler('content', cmd_content))
    application.add_handler(CommandHandler('news', cmd_news))
    application.add_handler(CommandHandler('assignments', cmd_assignments))
    application.add_handler(CommandHandler('deadlines', cmd_deadlines))
    application.add_handler(CommandHandler('grades', show_grades))
    application.add_handler(CommandHandler('prefs', cmd_prefs))
    application.add_handler(CommandHandler('togglecourse', cmd_toggle_course))

    if Config.feature_enabled("admin_panel"):
        application.add_handler(CommandHandler('admin', cmd_admin))
        application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^adm:"))
        application.add_handler(CommandHandler('addadmin', add_admin))
        application.add_handler(CommandHandler('deladmin', del_admin))
        # Keep legacy commands for compatibility
        application.add_handler(CommandHandler('stats', admin_stats))
        application.add_handler(CommandHandler('ban', ban_user))
        application.add_handler(CommandHandler('unban', unban_user))
        application.add_handler(CommandHandler('user', user_info))
        application.add_handler(CommandHandler('logs', admin_logs))
        application.add_handler(CommandHandler('broadcast', broadcast))
        application.add_handler(CommandHandler('userfind', user_find))
        application.add_handler(CommandHandler('tune', tune_user))
        application.add_handler(CommandHandler('health', bot_health))

    application.add_handler(CallbackQueryHandler(show_course_menu, pattern="^course:"))
    application.add_handler(CallbackQueryHandler(show_assignments, pattern="^assign:"))
    application.add_handler(CallbackQueryHandler(show_announcements, pattern="^news:"))
    application.add_handler(CallbackQueryHandler(show_course_content, pattern="^content:"))
    application.add_handler(CallbackQueryHandler(show_course_grades, pattern="^grades:"))
    application.add_handler(CallbackQueryHandler(back_to_courses, pattern="^menu:courses"))
    application.add_handler(CallbackQueryHandler(handle_dashboard, pattern="^cmd:"))

    application.add_handler(TypeHandler(Update, cleanup_db_session), group=999)

    # JobQueue setup
    if application.job_queue is not None and Config.feature_enabled("notifications"):
        interval_seconds = Config.NOTIFICATION_CHECK_INTERVAL_MINUTES * 60
        application.job_queue.run_repeating(
            check_new_items_job,
            interval=interval_seconds,
            first=60,
            name="check_new_items",
        )
        logger.info("🔔 فحص الإشعارات مفعّل — كل %d دقيقة", Config.NOTIFICATION_CHECK_INTERVAL_MINUTES)
    
    await _validate_welcome_image()
    return application


def main():
    """نقطة الإقلاع الأساسية — تدير الـ event loop بشكل آمن للنسخ القديمة والحديثة."""
    # نتحقق إذا النسخة حديثة (v20+) أو قديمة
    is_modern = hasattr(Application, "run_until_disconnected")

    if is_modern:
        # النسخة الحديثة (v20+): نستخدم المسار الرسمي والمستقر
        try:
            # ننشئ loop جديد لو كان الحالي مغلق (بسبب كراش سابق)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # نجهز الـ application داخل الـ loop
            application = loop.run_until_complete(_setup_application())
            
            logger.info("🚀 البوت يعمل بنظام PTB v20+ المستقر...")
            # run_polling في v20+ هي blocking وتدير الـ loop داخلياً
            application.run_polling(drop_pending_updates=False)
        except Exception as e:
            logger.error("خطأ في تشغيل البوت (v20+): %s — إعادة التشغيل بعد 5 ثوانٍ", e)
            time.sleep(5)
            main() # إعادة محاولة
    else:
        # النسخة القديمة (< v20): نستخدم المسار المتزامن القديم
        # (هذا المسار اللي بيحتاجه سيرفر المستخدم لتجنب Event loop is closed)
        logger.info("📡 نسخة PTB قديمة مكتشفة — استخدام المسار المتزامن الآمن")
        while True:
            try:
                # في النسخ القديمة، Application.builder() مش موجود أو مختلف،
                # لكن بما إن الكود أصلاً مكتوب بستايل v20، فرح نحاول نشغله
                # بأقل قدر من الـ async في الـ main thread.
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                application = loop.run_until_complete(_setup_application())
                
                logger.info("🚀 البوت يعمل بنظام التوافق مع النسخ القديمة...")
                # في النسخ القديمة، run_polling متزامنة تماماً
                application.run_polling(poll_interval=2.0)
            except Exception as e:
                logger.error("توقف البوت (نسخة قديمة): %s — إعادة التشغيل بعد 5 ثوانٍ", e)
                # إغلاق الـ loop قبل إعادة المحاولة لمنع تضارب الموارد
                try:
                    loop.close()
                except:
                    pass
                time.sleep(5)


async def _validate_welcome_image():
    """يتأكد إن رابط الصورة شغال (200) — وإلا بيستخدم fallback محلي."""
    global WELCOME_IMAGE
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.head(WELCOME_IMAGE, timeout=10) as resp:
                if resp.status == 200:
                    return
    except Exception:
        pass
    if os.path.isfile(WELCOME_IMAGE_LOCAL):
        logger.warning("⚠️ رابط صورة الترحيب ما اشتغل — بنستخدم النسخة المحلية: %s", WELCOME_IMAGE_LOCAL)
        WELCOME_IMAGE = WELCOME_IMAGE_LOCAL
    else:
        logger.warning("⚠️ صورة الترحيب ما انجابت (الرابط مات ولا في نسخة محلية) "
                       "— /start برسل النص بدون صورة.")
        WELCOME_IMAGE = None


async def _send_welcome_photo(context, chat_id, text, entities, keyboard):
    """يرسل صورة الترحيب مع caption — لو الصورة مفقودة بيرسل النص بس."""
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=WELCOME_IMAGE,
            caption=text,
            caption_entities=entities,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning("فشل إرسال صورة الترحيب: %s — إرسال النص فقط", e)
        await context.bot.send_message(
            chat_id=chat_id, text=text, entities=entities, reply_markup=keyboard,
        )


# دالة _run_bot_24_7 تم دمجها داخل main() لضمان إدارة الـ event loop بشكل أفضل
# ومنع خطأ "Event loop is closed" المتكرر على السيرفرات المقيدة.


if __name__ == '__main__':
    main()