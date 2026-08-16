import asyncio
import datetime
import os
import json
try:
    import psutil
except ImportError:
    psutil = None
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.config import Config
from database.models import User, AdminAction, BotAdmin, BotSetting
from bot.utils.html_escape import esc

# --- Helpers ---

async def is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """يتحقق إذا كان المستخدم أدمن (من .env أو من قاعدة البيانات)."""
    if user_id in Config.ADMIN_IDS:
        return True
    db_session = context.bot_data['db_session']
    admin = db_session.query(BotAdmin).filter_by(telegram_id=user_id).first()
    return admin is not None

async def get_setting(key: str, default: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    db_session = context.bot_data['db_session']
    s = db_session.query(BotSetting).filter_by(key=key).first()
    return s.value if s else default

async def set_setting(key: str, value: str, context: ContextTypes.DEFAULT_TYPE):
    db_session = context.bot_data['db_session']
    s = db_session.query(BotSetting).filter_by(key=key).first()
    if s:
        s.value = value
    else:
        db_session.add(BotSetting(key=key, value=value))
    db_session.commit()

async def log_admin_action(admin_id: int, action: str, target_id: int = None, details: str = "", context: ContextTypes.DEFAULT_TYPE = None):
    if not context: return
    db_session = context.bot_data['db_session']
    db_session.add(AdminAction(
        admin_id=admin_id, action=action,
        target_user_id=target_id, details=details
    ))
    db_session.commit()

# --- Admin UI Handlers ---

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر الرئيسي /admin لفتح لوحة التحكم."""
    if not await is_admin(update.effective_user.id, context):
        await update.message.reply_text("⛔ <b>غير مصرح لك</b> بالدخول للوحة التحكم.", parse_mode="HTML")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats"),
         InlineKeyboardButton("🖥️ المراقبة", callback_data="adm:health")],
        [InlineKeyboardButton("⚙️ الميزات", callback_data="adm:features"),
         InlineKeyboardButton("🛠️ الصيانة", callback_data="adm:maint")],
        [InlineKeyboardButton("👥 المستخدمين", callback_data="adm:users"),
         InlineKeyboardButton("🛡️ الأدمنية", callback_data="adm:admins")],
        [InlineKeyboardButton("💾 نسخة احتياطية", callback_data="adm:backup"),
         InlineKeyboardButton("📋 السجلات", callback_data="adm:logs")],
        [InlineKeyboardButton("📢 بث رسالة", callback_data="adm:broadcast_menu")]
    ]
    
    text = (
        "⚡ <b>لوحة تحكم الإدارة المتقدمة</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "مرحباً بك في مركز التحكم. اختر قسماً من الأزرار أدناه لإدارة البوت."
    )
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار الخاصة بلوحة الأدمن."""
    query = update.callback_query
    if not await is_admin(query.from_user.id, context):
        await query.answer("⛔ غير مصرح!", show_alert=True)
        return

    data = query.data.split(":")
    action = data[1]

    if action == "menu":
        await query.edit_message_text(
            "⚡ <b>لوحة تحكم الإدارة المتقدمة</b>\n━━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats"),
                 InlineKeyboardButton("🖥️ المراقبة", callback_data="adm:health")],
                [InlineKeyboardButton("⚙️ الميزات", callback_data="adm:features"),
                 InlineKeyboardButton("🛠️ الصيانة", callback_data="adm:maint")],
                [InlineKeyboardButton("👥 المستخدمين", callback_data="adm:users"),
                 InlineKeyboardButton("🛡️ الأدمنية", callback_data="adm:admins")],
                [InlineKeyboardButton("💾 نسخة احتياطية", callback_data="adm:backup"),
                 InlineKeyboardButton("📋 السجلات", callback_data="adm:logs")],
                [InlineKeyboardButton("📢 بث رسالة", callback_data="adm:broadcast_menu")]
            ]), parse_mode="HTML"
        )
    
    elif action == "stats":
        await show_stats(query, context)
    elif action == "health":
        await show_health(query, context)
    elif action == "maint":
        await show_maintenance(query, context)
    elif action == "toggle_maint":
        current = await get_setting("maintenance_mode", "0", context)
        new_val = "1" if current == "0" else "0"
        await set_setting("maintenance_mode", new_val, context)
        await log_admin_action(query.from_user.id, "toggle_maintenance", details=f"New state: {new_val}", context=context)
        await show_maintenance(query, context)
    elif action == "features":
        await show_features(query, context)
    elif action == "toggle_feat":
        feat = data[2]
        current = await get_setting(f"feat_{feat}", "1", context)
        new_val = "0" if current == "1" else "1"
        await set_setting(f"feat_{feat}", new_val, context)
        await log_admin_action(query.from_user.id, "toggle_feature", details=f"Feature {feat} set to {new_val}", context=context)
        await show_features(query, context)
    elif action == "backup":
        await run_backup(query, context)
    elif action == "logs":
        await show_logs(query, context)
    elif action == "admins":
        await show_admins(query, context)
    elif action == "users":
        await query.edit_message_text(
            "👥 <b>إدارة المستخدمين</b>\n\nاستخدم الأوامر التالية للبحث أو التحكم:\n"
            "• <code>/userfind &lt;نص&gt;</code> - بحث عن طالب\n"
            "• <code>/user &lt;id&gt;</code> - معلومات كاملة\n"
            "• <code>/ban &lt;id&gt;</code> - حظر\n"
            "• <code>/unban &lt;id&gt;</code> - فك حظر\n"
            "• <code>/tune &lt;id&gt; &lt;feature&gt; &lt;0|1&gt;</code> - ضبط ميزات",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="adm:menu")]]),
            parse_mode="HTML"
        )
    elif action == "broadcast_menu":
        await query.edit_message_text(
            "📢 <b>بث رسالة</b>\n\nاستخدم الأمر:\n"
            "<code>/broadcast all &lt;الرسالة&gt;</code> للكل\n"
            "<code>/broadcast &lt;id&gt; &lt;الرسالة&gt;</code> لفرد",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="adm:menu")]]),
            parse_mode="HTML"
        )

# --- Sub-Handlers ---

async def show_stats(query, context):
    db_session = context.bot_data['db_session']
    total = db_session.query(User).count()
    active = db_session.query(User).filter_by(is_active=True).count()
    banned = db_session.query(User).filter_by(is_banned=True).count()
    notif = db_session.query(User).filter_by(notifications_enabled=True).count()
    
    text = (
        "📊 <b>إحصائيات النظام</b>\n━━━━━━━━━━━━\n"
        f"👥 إجمالي الطلاب: {total}\n"
        f"✅ الطلاب النشطين: {active}\n"
        f"🚷 الطلاب المحظورين: {banned}\n"
        f"🔔 مفعلي الإشعارات: {notif}"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="adm:menu")]]), parse_mode="HTML")

async def show_health(query, context):
    # Server Stats
    if psutil:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        uptime_dt = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - uptime_dt
        stats_text = (
            f"⚙️ استهلاك المعالج: {cpu}%\n"
            f"🧠 استهلاك الذاكرة: {ram}%\n"
            f"⏱️ تشغيل السيرفر: {str(uptime).split('.')[0]}\n"
        )
    else:
        stats_text = "⚠️ <i>إحصائيات المعالج والذاكرة غير متاحة (psutil غير مثبت)</i>\n"
    
    # Check Moodle
    import aiohttp
    moodle_status = "🔴 أوفلاين"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(Config.BASE_URL, timeout=5) as r:
                if r.status == 200: moodle_status = "🟢 أونلاين"
    except: pass

    text = (
        "🖥️ <b>مراقبة النظام</b>\n━━━━━━━━━━━━\n"
        f"{stats_text}"
        f"🏫 موقع الجامعة: {moodle_status}"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="adm:menu")]]), parse_mode="HTML")

async def show_maintenance(query, context):
    m_mode = await get_setting("maintenance_mode", "0", context)
    status = "⚠️ <b>مفعّل</b> (البوت مغلق للمستخدمين)" if m_mode == "1" else "🟢 <b>معطّل</b> (البوت متاح للجميع)"
    btn_text = "🔓 فتح البوت" if m_mode == "1" else "🔒 إغلاق للصيانة"
    
    text = (
        "🛠️ <b>وضع الصيانة</b>\n━━━━━━━━━━━━\n"
        f"الحالة الحالية: {status}\n\n"
        "عند تفعيل وضع الصيانة، سيرد البوت على المستخدمين برسالة اعتذار ولن ينفذ أي أوامر، باستثناء الأدمنية."
    )
    kb = [
        [InlineKeyboardButton(btn_text, callback_data="adm:toggle_maint")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm:menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def show_features(query, context):
    feats = ["notifications", "email_notifications", "grades", "assignments", "content"]
    kb = []
    text = "⚙️ <b>التحكم بالميزات (عالمياً)</b>\n━━━━━━━━━━━━\n"
    
    for f in feats:
        val = await get_setting(f"feat_{f}", "1", context)
        status = "✅" if val == "1" else "❌"
        kb.append([InlineKeyboardButton(f"{status} {f}", callback_data=f"adm:toggle_feat:{f}")])
    
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm:menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def run_backup(query, context):
    db_path = "bot.db"
    if not os.path.exists(db_path):
        # نحاول نجيب المسار من DATABASE_URL
        db_path = Config.DATABASE_URL.replace("sqlite:///", "")
    
    if os.path.exists(db_path):
        backup_name = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(db_path, backup_name)
        
        try:
            with open(backup_name, 'rb') as f:
                await context.bot.send_document(
                    chat_id=query.from_user.id,
                    document=f,
                    filename=backup_name,
                    caption=f"💾 نسخة احتياطية لقاعدة البيانات\n📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
            await query.answer("✅ تم إرسال النسخة الاحتياطية بنجاح!")
            await log_admin_action(query.from_user.id, "backup_created", details=backup_name, context=context)
        except Exception as e:
            await query.answer(f"❌ فشل الإرسال: {e}", show_alert=True)
        finally:
            if os.path.exists(backup_name): os.remove(backup_name)
    else:
        await query.answer("❌ لم يتم العثور على ملف قاعدة البيانات!", show_alert=True)

async def show_logs(query, context):
    db_session = context.bot_data['db_session']
    logs = db_session.query(AdminAction).order_by(AdminAction.created_at.desc()).limit(10).all()
    
    if not logs:
        text = "📋 سجل العمليات فارغ."
    else:
        text = "📋 <b>آخر 10 عمليات إدارية:</b>\n\n"
        for l in logs:
            text += f"• <code>{l.action}</code> by <code>{l.admin_id}</code>\n"
            text += f"  └ {l.created_at.strftime('%m/%d %H:%M')} | {esc(l.details or '')}\n"
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="adm:menu")]]), parse_mode="HTML")

async def show_admins(query, context):
    db_session = context.bot_data['db_session']
    admins = db_session.query(BotAdmin).all()
    text = "🛡️ <b>قائمة الإداريين</b>\n━━━━━━━━━━━━\n"
    for a in admins:
        text += f"• <code>{a.telegram_id}</code> (أضيف بتاريخ {a.created_at.strftime('%Y-%m-%d')})\n"
    
    text += "\nلإضافة أدمن جديد:\n<code>/addadmin &lt;id&gt;</code>\nلإزالة أدمن:\n<code>/deladmin &lt;id&gt;</code>"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="adm:menu")]]), parse_mode="HTML")

# --- Command Handlers ---

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if not context.args:
        await update.message.reply_text("الاستخدام: /addadmin <id>")
        return
    try:
        new_id = int(context.args[0])
        db_session = context.bot_data['db_session']
        if not db_session.query(BotAdmin).filter_by(telegram_id=new_id).first():
            db_session.add(BotAdmin(telegram_id=new_id, added_by=update.effective_user.id))
            db_session.commit()
            await update.message.reply_text(f"✅ تم إضافة الأدمن {new_id}")
            await log_admin_action(update.effective_user.id, "add_admin", target_id=new_id, context=context)
        else:
            await update.message.reply_text("❌ هذا المستخدم أدمن بالفعل.")
    except:
        await update.message.reply_text("❌ معرف غير صالح.")

async def del_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if not context.args:
        await update.message.reply_text("الاستخدام: /deladmin <id>")
        return
    try:
        target_id = int(context.args[0])
        if target_id in Config.ADMIN_IDS:
            await update.message.reply_text("❌ لا يمكن إزالة أدمن أساسي من .env")
            return
        db_session = context.bot_data['db_session']
        admin = db_session.query(BotAdmin).filter_by(telegram_id=target_id).first()
        if admin:
            db_session.delete(admin)
            db_session.commit()
            await update.message.reply_text(f"✅ تم إزالة الأدمن {target_id}")
            await log_admin_action(update.effective_user.id, "del_admin", target_id=target_id, context=context)
        else:
            await update.message.reply_text("❌ المستخدم ليس أدمن.")
    except:
        await update.message.reply_text("❌ معرف غير صالح.")

# --- Compatibility Wrappers for existing commands ---
# (نفس الدوال السابقة لكن تم تعديل is_admin لتستخدم الدالة الجديدة)

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    # نستخدم show_stats لكن لرسالة نصية
    db_session = context.bot_data['db_session']
    total = db_session.query(User).count()
    active = db_session.query(User).filter_by(is_active=True).count()
    banned = db_session.query(User).filter_by(is_banned=True).count()
    await update.message.reply_text(f"📊 الكل: {total} | ✅ نشط: {active} | 🚷 محظور: {banned}")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if not context.args: return
    try:
        target_id = int(context.args[0])
        db_session = context.bot_data['db_session']
        user = db_session.query(User).filter_by(telegram_id=target_id).first()
        if user:
            user.is_banned = True
            await log_admin_action(update.effective_user.id, "ban_user", target_id=target_id, details="Manual ban", context=context)
            await update.message.reply_text(f"🚷 تم حظر {target_id}")
            try: await context.bot.send_message(chat_id=target_id, text="🚷 <b>تم حظرك من استخدام البوت.</b>", parse_mode="HTML")
            except: pass
    except: pass

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if not context.args: return
    try:
        target_id = int(context.args[0])
        db_session = context.bot_data['db_session']
        user = db_session.query(User).filter_by(telegram_id=target_id).first()
        if user:
            user.is_banned = False
            await log_admin_action(update.effective_user.id, "unban_user", target_id=target_id, details="Manual unban", context=context)
            await update.message.reply_text(f"✅ تم فك حظر {target_id}")
    except: pass

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if not context.args: return
    try:
        target_id = int(context.args[0])
        db_session = context.bot_data['db_session']
        user = db_session.query(User).filter_by(telegram_id=target_id).first()
        if not user: return
        status = "🚷 محظور" if user.is_banned else "✅ نشط"
        text = f"👤 <b>معلومات المستخدم</b>\nID: <code>{user.telegram_id}</code>\nالحالة: {status}\nالتسجيل: {user.created_at}"
        await update.message.reply_text(text, parse_mode="HTML")
    except: pass

async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    db_session = context.bot_data['db_session']
    logs = db_session.query(AdminAction).order_by(AdminAction.created_at.desc()).limit(15).all()
    text = "📋 <b>السجلات:</b>\n" + "\n".join([f"• {l.action} -> {l.target_user_id}" for l in logs])
    await update.message.reply_text(text, parse_mode="HTML")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if len(context.args) < 2: return
    target = context.args[0]
    msg = " ".join(context.args[1:])
    db_session = context.bot_data['db_session']
    
    if target.lower() == "all":
        users = db_session.query(User).filter_by(is_banned=False).all()
        for u in users:
            try:
                await context.bot.send_message(chat_id=u.telegram_id, text=f"📢 <b>إشعار إداري</b>\n\n{esc(msg)}", parse_mode="HTML")
                await asyncio.sleep(0.05)
            except: pass
        await update.message.reply_text("✅ تم البث للجميع.")
    else:
        try:
            await context.bot.send_message(chat_id=int(target), text=f"📢 <b>إشعار إداري</b>\n\n{esc(msg)}", parse_mode="HTML")
            await update.message.reply_text("✅ تم الإرسال.")
        except: pass

async def user_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if not context.args: return
    q = f"%{' '.join(context.args)}%"
    db_session = context.bot_data['db_session']
    results = db_session.query(User).filter((User.full_name.like(q)) | (User.username.like(q))).limit(10).all()
    text = "🔍 <b>النتائج:</b>\n" + "\n".join([f"• <code>{u.telegram_id}</code> - {u.full_name}" for u in results])
    await update.message.reply_text(text, parse_mode="HTML")

async def tune_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if len(context.args) != 3: return
    try:
        tid, feat, val = int(context.args[0]), context.args[1], context.args[2] == "1"
        db_session = context.bot_data['db_session']
        user = db_session.query(User).filter_by(telegram_id=tid).first()
        if user:
            if feat == "notifications": user.notifications_enabled = val
            elif feat == "email": user.email_notifications_enabled = val
            db_session.commit()
            await update.message.reply_text(f"✅ تم ضبط {feat} إلى {val}")
    except: pass

async def bot_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context): return
    if psutil:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        await update.message.reply_text(f"🖥️ حالة السيرفر: CPU {cpu}% | RAM {ram}%")
    else:
        await update.message.reply_text("🖥️ البوت يعمل، لكن إحصائيات السيرفر (psutil) غير متاحة.")
