from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CommandHandler, filters
import datetime
from bot.services.moodle_client import get_client, close_client
from bot.services.web_session import session_manager
from bot.utils.emojis import build_login_success_msg
from database.models import User

USERNAME, PASSWORD = range(2)


async def start_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 <b>تسجيل الدخول إلى Moodle</b>\n\n"
        "👤 أرسل رقمك الجامعي (Username):",
        parse_mode="HTML"
    )
    return USERNAME


async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['web_username'] = update.message.text.strip()
    await update.message.reply_text(
        "🔑 أرسل كلمة المرور:\n\n"
        "⚠️ <i>ملاحظة: الرسالة رح تمسح تلقائياً بعد الإرسال.</i>",
        parse_mode="HTML"
    )
    return PASSWORD


async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = context.user_data['web_username']
    password = update.message.text.strip()

    try:
        await update.message.delete()
    except Exception:
        pass

    msg = await update.message.reply_text("⏳ جاري تسجيل الدخول...")

    client = get_client(user.id)
    result = await client.login(username, password)

    if result['success']:
        enc_user, enc_pass = session_manager.encrypt_credentials(username, password)
        full_name = result.get('full_name')

        db_session = context.bot_data['db_session']
        db_user = db_session.query(User).filter_by(telegram_id=user.id).first()

        if not db_user:
            db_user = User(
                telegram_id=user.id,
                username=user.username,
                web_username=enc_user,
                web_password=enc_pass,
                full_name=full_name,
            )
            db_session.add(db_user)
        else:
            db_user.web_username = enc_user
            db_user.web_password = enc_pass
            db_user.is_banned = False
            db_user.full_name = full_name or db_user.full_name  # خلي القيمة القديمة لو الجلب فشل هالمرة
            db_user.last_activity = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        db_session.commit()

        # Send welcome with emojis — الاسم الكامل من البروفايل أولوية، وبعده
        # الاسم القصير من /my/، وبعدها fallback عام
        display_name = full_name or result.get('user_name') or 'مستخدم'
        text, entities = build_login_success_msg(display_name)

        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                entities=entities,
            )
            await msg.delete()
        except Exception:
            await msg.edit_text(text, entities=entities)
    else:
        await close_client(user.id)
        await msg.edit_text(
            f"❌ <b>فشل تسجيل الدخول</b>\n\n"
            f"{result['message']}\n\n"
            f"🔄 جرب مرة ثانية: /login",
            parse_mode="HTML"
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء.")
    return ConversationHandler.END


login_conv = ConversationHandler(
    entry_points=[CommandHandler('login', start_login)],
    states={
        USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_username)],
        PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)