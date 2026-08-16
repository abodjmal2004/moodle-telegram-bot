from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.services.moodle_client import get_client, close_client
from bot.utils.emojis import (
    course_menu_msg, deadlines_msg, grades_msg, logout_msg,
    no_courses_msg, no_assignments_msg, no_announcements_msg,
    no_content_msg, no_grades_msg, no_deadlines_msg, no_grades_overall_msg,
    login_prompt_msg, session_expired_msg, error_msg, courses_list_msg
)
from bot.utils.telegram_helpers import safe_answer
from bot.utils.html_escape import esc
from database.models import User, CoursePref
import json
import re
import datetime

# خريطة الأيقونات لأنواع الأنشطة بمودل — مستخدمة بكل دوال العرض (المحتوى
# والأوامر) حتى ما يتكرر الكود أو ينكسر متغير محلي.
ICON_MAP = {
    "assign": "📝", "forum": "💬", "resource": "📄",
    "quiz": "❓", "page": "📃", "url": "🔗", "label": "🏷️",
    "folder": "📁", "book": "📚", "glossary": "📖",
    "choice": "📊", "data": "🗂️", "feedback": "💭",
    "lesson": "🎓", "lti": "🔗", "scorm": "📦",
    "survey": "📋", "wiki": "🌐", "workshop": "🔧",
    "bigbluebuttonbn": "📹", "h5pactivity": "🎮",
    "imscp": "📦", "chat": "💬"
}


async def _is_banned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    db_session = context.bot_data['db_session']
    db_user = db_session.query(User).filter_by(telegram_id=user_id).first()
    if db_user and db_user.is_banned:
        return True
    return False


async def _ensure_client_ready(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id

    if await _is_banned(update, context):
        text = "🚷 <b>أنت محظور</b> من استخدام البوت.\n📩 تواصل مع الإدارة للاستفسار."
        if update.callback_query:
            await safe_answer(update.callback_query)
            try:
                await update.callback_query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                await update.callback_query.delete_message()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        return False

    client = get_client(user_id)

    if client._is_logged_in:
        return True

    db_session = context.bot_data['db_session']
    db_user = db_session.query(User).filter_by(telegram_id=user_id).first()

    if db_user and db_user.web_username:
        from bot.services.web_session import session_manager
        username, password = session_manager.decrypt_credentials(
            db_user.web_username, db_user.web_password
        )
        if username is None:
            db_user.web_username = None
            db_user.web_password = None
            db_session.commit()
            text = session_expired_msg()
            if update.callback_query:
                try:
                    await update.callback_query.edit_message_text(text, parse_mode="HTML")
                except Exception:
                    await update.callback_query.delete_message()
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
            else:
                await update.message.reply_text(text, parse_mode="HTML")
            return False

        result = await client.login(username, password)
        if result['success']:
            db_user.last_activity = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db_session.commit()
            return True

    text = login_prompt_msg()
    if update.callback_query:
        await safe_answer(update.callback_query)
        try:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        except Exception:
            await update.callback_query.delete_message()
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")
    return False


async def show_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _is_banned(update, context):
        await update.message.reply_text(
            "🚷 <b>أنت محظور</b> من استخدام البوت.",
            parse_mode="HTML"
        )
        return
    if not await _ensure_client_ready(update, context):
        return

    user_id = update.effective_user.id
    client = get_client(user_id)

    try:
        courses = await client.get_courses()
        if not courses:
            await update.message.reply_text(
                no_courses_msg(),
                parse_mode="HTML"
            )
            return

        context.user_data['courses_cache'] = {c['id']: c['name'] for c in courses}

        keyboard = []
        for c in courses:
            btn_text = f"📘 {c['name'][:28]}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"course:{c['id']}")])

        await update.message.reply_text(
            courses_list_msg(),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    except RuntimeError as e:
        await update.message.reply_text(
            error_msg(str(e)),
            parse_mode="HTML"
        )


async def _block_if_banned_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """يتحقق من الحظر جوا الـ callback handlers (لأن المستخدم ممكن يستخدم
    أزرار قديمة محفوظة عنده حتى لو تحظر بعدها). يرجع True لو تم الحظر."""
    if not await _is_banned(update, context):
        return False
    query = update.callback_query
    await safe_answer(query, "🚷 أنت محظور من استخدام البوت.", show_alert=True)
    return True


async def show_course_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _block_if_banned_callback(update, context):
        return
    await safe_answer(query)

    parts = query.data.split(":")
    course_id = parts[1]

    course_name = context.user_data.get('courses_cache', {}).get(course_id, f"مادة {course_id}")

    keyboard = [
        [
            InlineKeyboardButton("📝 الواجبات", callback_data=f"assign:{course_id}"),
            InlineKeyboardButton("📢 الأخبار", callback_data=f"news:{course_id}"),
        ],
        [
            InlineKeyboardButton("📖 المحتوى", callback_data=f"content:{course_id}"),
            InlineKeyboardButton("📊 الدرجات", callback_data=f"grades:{course_id}"),
        ],
        [InlineKeyboardButton("🔙 رجوع للمواد", callback_data="menu:courses")],
    ]

    text = course_menu_msg(course_name)

    try:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except Exception:
        # Message is a photo, delete and send new
        chat_id = query.message.chat_id
        await query.delete_message()
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )


async def show_assignments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _block_if_banned_callback(update, context):
        return
    await safe_answer(query)
    course_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    client = get_client(user_id)

    course_name = context.user_data.get('courses_cache', {}).get(str(course_id), "المادة")

    try:
        assigns = await client.get_assignments(course_id)
        if not assigns:
            text = no_assignments_msg(course_name)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
            ]])
            try:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception:
                await query.delete_message()
                await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            return

        lines = [f"📝 <b>واجبات: {esc(course_name)}</b>\n"]
        for a in assigns:
            status_emoji = "✅" if a.get("status") == "تم التسليم" else "⏳"
            due = a.get('due_date_text') or 'بدون موعد'
            lines.append(
                f"{status_emoji} <b>{esc(a['name'])}</b>\n"
                f"📅 <code>{esc(due)}</code>\n"
            )

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n\n..."

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
        ]])

        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        text = error_msg(str(e))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
        ]])
        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")


async def show_announcements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _block_if_banned_callback(update, context):
        return
    await safe_answer(query)
    course_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    client = get_client(user_id)

    course_name = context.user_data.get('courses_cache', {}).get(str(course_id), "المادة")

    try:
        posts = await client.get_announcements(course_id)
        if not posts:
            text = no_announcements_msg(course_name)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
            ]])
            try:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception:
                await query.delete_message()
                await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            return

        text = f"📢 <b>أخبار: {esc(course_name)}</b>\n\n"
        for p in posts[:5]:
            text += f"📌 <b>{esc(p['title'])}</b>\n"
            if p.get("author"):
                text += f"👤 <i>{esc(p['author'])}</i>\n"
            if p.get("time"):
                text += f"🕐 <i>{esc(p['time'])}</i>\n"
            text += "\n"

        if len(text) > 4000:
            text = text[:4000] + "\n\n..."

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
        ]])

        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        text = error_msg(str(e))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
        ]])
        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")


async def show_course_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _block_if_banned_callback(update, context):
        return
    await safe_answer(query)
    course_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    client = get_client(user_id)

    course_name = context.user_data.get('courses_cache', {}).get(str(course_id), "المادة")

    try:
        items = await client.get_course_content(course_id)
        if not items:
            text = no_content_msg(course_name)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
            ]])
            try:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception:
                await query.delete_message()
                await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            return

        lines = [f"📖 <b>محتوى: {course_name}</b>\n"]
        current_section = None
        for item in items:
            # التحقق من وجود الحقول الأساسية حتى ما ينكسر البوت لو السكرابنج جاب داتا ناقصة
            sec = item.get('section', 'عام')
            name = item.get('name', 'بدون اسم')
            itype = item.get('type', '')

            if sec != current_section:
                current_section = sec
                lines.append(f"\n📂 <b>{esc(current_section)}</b>")

            icon = ICON_MAP.get(itype, "📌")
            # HTML escaping ضروري جداً لأن المحتوى ممكن يحوي وسم مثل < أو >
            lines.append(f"{icon} {esc(name)}")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n\n..."

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
        ]])

        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        text = error_msg(str(e))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
        ]])
        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")


async def show_course_grades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _block_if_banned_callback(update, context):
        return
    await safe_answer(query)
    course_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    client = get_client(user_id)

    course_name = context.user_data.get('courses_cache', {}).get(str(course_id), "المادة")

    try:
        grades = await client.get_grades(course_id)
        if not grades:
            text = no_grades_msg(course_name)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
            ]])
            try:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception:
                await query.delete_message()
                await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            return

        text = f"📊 <b>درجات: {esc(course_name)}</b>\n\n"
        for g in grades[:15]:
            rng = f" <code>({esc(g['range'])})</code>" if g['range'] else ""
            pct = f" — <b>{esc(g['percentage'])}</b>" if g['percentage'] else ""
            text += f"• {esc(g['item'])}: <code>{esc(g['grade'])}</code>{rng}{pct}\n"

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
        ]])

        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        text = error_msg(str(e))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"course:{course_id}")
        ]])
        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")


async def back_to_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _block_if_banned_callback(update, context):
        return
    await safe_answer(query)

    courses_cache = context.user_data.get('courses_cache', {})
    if courses_cache:
        keyboard = []
        for cid, name in courses_cache.items():
            keyboard.append([InlineKeyboardButton(f"📘 {name[:28]}", callback_data=f"course:{cid}")])
        text = courses_list_msg()
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            await query.delete_message()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        user_id = update.effective_user.id
        client = get_client(user_id)
        try:
            courses = await client.get_courses()
            context.user_data['courses_cache'] = {c['id']: c['name'] for c in courses}
            keyboard = []
            for c in courses:
                keyboard.append([InlineKeyboardButton(f"📘 {c['name'][:28]}", callback_data=f"course:{c['id']}")])
            text = courses_list_msg()
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            except Exception:
                await query.delete_message()
                await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception as e:
            text = error_msg(str(e))
            try:
                await query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                await query.delete_message()
                await context.bot.send_message(chat_id=query.message.chat_id, text=text, parse_mode="HTML")


# ═══════════════════════ Slash Commands ═══════════════════════
async def cmd_assignments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _is_banned(update, context):
        await update.message.reply_text(
            "🚷 <b>أنت محظور</b> من استخدام البوت.",
            parse_mode="HTML"
        )
        return
    if not await _ensure_client_ready(update, context):
        return

    if context.args:
        try:
            course_id = int(context.args[0])
            await _send_assignments_text(update, context, course_id)
            return
        except ValueError:
            await update.message.reply_text(
                "❌ <b>رقم المادة لازم يكون رقم.</b>",
                parse_mode="HTML"
            )
            return

    await show_courses(update, context)


async def _send_assignments_text(update, context, course_id):
    user_id = update.effective_user.id
    client = get_client(user_id)
    assigns = await client.get_assignments(course_id)

    if not assigns:
        await update.message.reply_text(
            "📭 <b>ما فيه واجبات لهذه المادة.</b>",
            parse_mode="HTML"
        )
        return

    lines = ["📝 <b>الواجبات:</b>\n"]
    for a in assigns:
        status_emoji = "✅" if a.get("status") == "تم التسليم" else "⏳"
        due = a.get('due_date_text') or 'بدون موعد'
        lines.append(
            f"{status_emoji} <b>{esc(a['name'])}</b>\n"
            f"📅 <code>{esc(due)}</code>\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_feature("content", update, context): return
    if await _is_banned(update, context):
        await update.message.reply_text(
            "🚷 <b>أنت محظور</b> من استخدام البوت.",
            parse_mode="HTML"
        )
        return
    if not await _ensure_client_ready(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "❓ <b>الاستخدام:</b> <code>/content &lt;رقم المادة&gt;</code>\n\n"
            "📚 جرب <code>/courses</code> لعرض الأرقام",
            parse_mode="HTML"
        )
        return
    try:
        course_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ <b>رقم المادة لازم يكون رقم.</b>",
            parse_mode="HTML"
        )
        return
    user_id = update.effective_user.id
    client = get_client(user_id)
    items = await client.get_course_content(course_id)
    if not items:
        await update.message.reply_text(
            "📭 <b>ما فيه محتوى.</b>",
            parse_mode="HTML"
        )
        return
    lines = ["📖 <b>محتوى المادة:</b>\n"]
    current_section = None
    for item in items:
        if item['section'] != current_section:
            current_section = item['section']
            lines.append(f"\n📂 <b>{esc(current_section)}</b>")
        icon = ICON_MAP.get(item.get("type", ""), "📌")
        lines.append(f"{icon} {esc(item['name'])}")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n..."
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_feature("content", update, context): return
    if await _is_banned(update, context):
        await update.message.reply_text(
            "🚷 <b>أنت محظور</b> من استخدام البوت.",
            parse_mode="HTML"
        )
        return
    if not await _ensure_client_ready(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "❓ <b>الاستخدام:</b> <code>/news &lt;رقم المادة&gt;</code>\n\n"
            "📚 جرب <code>/courses</code> لعرض الأرقام",
            parse_mode="HTML"
        )
        return
    try:
        course_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ <b>رقم المادة لازم يكون رقم.</b>",
            parse_mode="HTML"
        )
        return
    user_id = update.effective_user.id
    client = get_client(user_id)
    posts = await client.get_announcements(course_id)
    if not posts:
        await update.message.reply_text(
            "📭 <b>ما فيه إعلانات.</b>",
            parse_mode="HTML"
        )
        return
    text = "📢 <b>آخر الإعلانات:</b>\n\n"
    for p in posts[:5]:
        text += f"📌 <b>{esc(p['title'])}</b>\n"
        if p.get("author"): text += f"👤 <i>{esc(p['author'])}</i>\n"
        if p.get("time"): text += f"🕐 <i>{esc(p['time'])}</i>\n"
        text += "\n"
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _is_banned(update, context):
        text = "🚷 <b>أنت محظور</b> من استخدام البوت."
        if update.callback_query:
            await safe_answer(update.callback_query)
            try:
                await update.callback_query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                await update.callback_query.delete_message()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        return
    if not await _ensure_client_ready(update, context):
        return
    user_id = update.effective_user.id
    client = get_client(user_id)
    events = await client.get_upcoming_deadlines()
    if not events:
        text = no_deadlines_msg()
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                await update.callback_query.delete_message()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        return
    lines = [f"{deadlines_msg()}\n"]
    for e in events[:10]:
        course_name = e.get('course') or '-'
        time_str = e.get('time') or '-'
        lines.append(
            f"📌 <b>{esc(e['title'])}</b>\n"
            f"📚 <i>{esc(course_name)}</i>\n"
            f"🕐 <code>{esc(time_str)}</code>\n"
        )
    text = "\n".join(lines)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        except Exception:
            await update.callback_query.delete_message()
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")


async def show_grades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _is_banned(update, context):
        text = "🚷 <b>أنت محظور</b> من استخدام البوت."
        if update.callback_query:
            await safe_answer(update.callback_query)
            try:
                await update.callback_query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                await update.callback_query.delete_message()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        return
    if not await _ensure_client_ready(update, context):
        return
    user_id = update.effective_user.id
    client = get_client(user_id)
    try:
        grades = await client.get_grades()
        if not grades:
            text = no_grades_overall_msg()
            if update.callback_query:
                try:
                    await update.callback_query.edit_message_text(text, parse_mode="HTML")
                except Exception:
                    await update.callback_query.delete_message()
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
            else:
                await update.message.reply_text(text, parse_mode="HTML")
            return
        text = f"{grades_msg()}\n\n"
        for g in grades[:15]:
            rng = f" <code>({g['range']})</code>" if g['range'] else ""
            pct = f" — <b>{g['percentage']}</b>" if g['percentage'] else ""
            text += f"• {g['item']}: <code>{g['grade']}</code>{rng}{pct}\n"
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                await update.callback_query.delete_message()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")
    except RuntimeError:
        text = "🔐 <b>سجل دخول أولاً:</b> /login"
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                await update.callback_query.delete_message()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")


async def do_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await get_client(user_id).logout()
    await close_client(user_id)
    context.user_data.pop('courses_cache', None)

    # المشكلة الأساسية سابقاً: هون ما كان ينمسح شي من قاعدة البيانات،
    # فبقى البوت يعتبر المستخدم "مسجل دخول" (لأن /start بيتحقق من
    # db_user.web_username) حتى بعد ما يعمل /logout فعلياً.
    db_session = context.bot_data['db_session']
    db_user = db_session.query(User).filter_by(telegram_id=user_id).first()
    if db_user:
        db_user.web_username = None
        db_user.web_password = None
        db_session.commit()

    text = logout_msg()

    if update.callback_query:
        await safe_answer(update.callback_query)
        try:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        except Exception:
            await update.callback_query.delete_message()
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")