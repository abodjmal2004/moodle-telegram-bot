"""
Notification Job — يفحص دورياً كل المستخدمين المفعّلين للإشعارات، وبيبعت
تنبيه (تليجرام + إيميل اختياري) لو طلع واجب أو إعلان جديد بأي مادة عندهم.

يشتغل عن طريق PTB's JobQueue (مبني فوق APScheduler، اللي أصلاً موجود
بـ requirements.txt).
"""
import asyncio
import logging

from telegram.ext import ContextTypes

from bot.config import Config
from bot.utils.html_escape import esc
from bot.services.email_service import send_email
from bot.services.moodle_client import get_client, close_client
from bot.services.web_session import session_manager
from database.models import User, SeenItem, CoursePref
import json

logger = logging.getLogger(__name__)

# يحدد أقصى عدد جلسات Moodle شغالة بنفس اللحظة أثناء فحص الإشعارات، حتى
# ما نحمّل موقع الجامعة (أو البوت) بطلبات كتير مرة وحدة لو المستخدمين
# المفعّلين للإشعارات كتار.
_semaphore = asyncio.Semaphore(Config.NOTIFICATION_CONCURRENCY)


async def check_new_items_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """نقطة الدخول اللي بتستدعيها JobQueue كل فترة (NOTIFICATION_CHECK_INTERVAL_MINUTES)."""
    db_session = context.bot_data['db_session']
    try:
        users = (
            db_session.query(User)
            .filter(User.notifications_enabled.is_(True))
            .filter(User.is_banned.is_(False))
            .filter(User.web_username.isnot(None))
            .all()
        )
        # نسحب كل البيانات اللازمة هون وإحنا لسا داخل نفس الـ session المفتوحة
        user_snapshots = [
            (u.id, u.telegram_id, u.web_username, u.web_password, u.full_name,
             u.email, u.email_notifications_enabled)
            for u in users
        ]
    finally:
        db_session.remove()

    if not user_snapshots:
        return

    logger.info("Notification check: %d user(s) to scan", len(user_snapshots))
    tasks = [_check_user(context, snap) for snap in user_snapshots]
    await asyncio.gather(*tasks, return_exceptions=True)
    # تنظيف الـ session بس بالنهاية — كل الـ coroutines هون بتشترك بنفس
    # الـ asyncio task (asyncio.gather ما بانشئ مهام منفصلة)، فالـ scoped
    # session بيرجع نفس الـ session لكلهم. إزالة الـ session جوا كل coroutine
    # كان بيرمي خطأ "Session is no longer valid" للـ coroutines التالية.


async def _check_user(context: ContextTypes.DEFAULT_TYPE, snapshot: tuple) -> None:
    (db_user_id, telegram_id, enc_user, enc_pass, full_name,
     email, email_notify) = snapshot

    # تحميل تفضيلات المواد لهذا المستخدم (اللي عطّلها بـ /togglecourse)
    db_session_snap = context.bot_data['db_session']
    try:
        prefs = {p.course_id: p.notif_enabled for p in db_session_snap.query(CoursePref).filter_by(user_id=db_user_id).all()}
    finally:
        pass  # ما بنشيل الـ session — انظر الشرح أعلى (shared task)
    # الميزات المعطّلة لهالمستخدم تحديدًا (ضبطها الأدمن بـ /tune)
    user = db_session_snap.query(User).filter_by(id=db_user_id).first()
    disabled = []
    if user and user.disabled_features:
        try:
            disabled = json.loads(user.disabled_features) or []
        except (TypeError, ValueError):
            disabled = []

    async with _semaphore:
        username, password = session_manager.decrypt_credentials(enc_user, enc_pass)
        if not username:
            return  # مفتاح التشفير تغير أو البيانات تلفت — تجاهل بهدوء
        if "notifications" in disabled:
            return  # الإدارة عطّلت الإشعارات لهالمستخدم بـ /tune — ما في شغل

        await close_client(telegram_id)  # نضمن جلسة نظيفة بدون تعارض مع استخدام المستخدم الحالي للبوت
        client = get_client(telegram_id)
        db_session = context.bot_data['db_session']

        try:
            login_result = await client.login(username, password)
            if not login_result.get("success"):
                return

            courses = await client.get_courses()
            new_items = []

            # أول فحص لهاد المستخدم (ما عنده أي SeenItem مسجل قبل هيك)؟
            # لو هيك، منسجل كل شي كـ"مشاف" بصمت بدون ما نبعت إشعارات —
            # وإلا رح يوصله إشعار عن كل واجب/إعلان موجود أصلاً بالمقررات
            # (عشرات الإشعارات دفعة وحدة أول ما يفعّل الخاصية). من ثاني
            # فحص وطالع، أي شي جديد فعلاً رح يبعتله إشعار عنه.
            has_baseline = (
                db_session.query(SeenItem).filter_by(user_id=db_user_id).first() is not None
            )

            for course in courses:
                course_id = course["id"]

                # تفضيل المستخدم: إشعارات هالمادة ممكن تكون معطّلة
                if not prefs.get(str(course_id), True):
                    continue

                try:
                    assignments = await client.get_assignments(int(course_id))
                except Exception as e:
                    logger.debug("assignments check failed (course %s): %s", course_id, e)
                    assignments = []

                for a in assignments:
                    key = str(a.get("assignment_id") or a.get("url") or "")
                    if not key:
                        continue
                    is_new = _mark_if_new(db_session, db_user_id, course_id, "assignment", key)
                    if is_new and has_baseline:
                        new_items.append({
                            "kind": "assignment", "course": course["name"],
                            "name": a.get("name", ""),
                            "due": a.get("due_date_text") or "غير محدد",
                        })

                try:
                    posts = await client.get_announcements(int(course_id))
                except Exception as e:
                    logger.debug("announcements check failed (course %s): %s", course_id, e)
                    posts = []

                for p in posts:
                    key = p.get("url") or p.get("title") or ""
                    if not key:
                        continue
                    is_new = _mark_if_new(db_session, db_user_id, course_id, "announcement", key)
                    if is_new and has_baseline:
                        new_items.append({
                            "kind": "announcement", "course": course["name"],
                            "name": p.get("title", ""), "due": None,
                        })

            db_session.commit()

            if new_items:
                await _send_notifications(
                    context, telegram_id, full_name, email, email_notify, new_items
                )

        except Exception as e:
            logger.error("notification check failed for telegram_id=%s: %s", telegram_id, e)
            db_session.rollback()
        finally:
            await close_client(telegram_id)
            # لا db_session.remove() هنا — انظر الشرح أعلى (shared task)

    # ما بنبعت إشعارات أصلاً لو الإدارة عطّلت ميزة الإشعارات لهالمستخدم
    # (هون بالمرة الأخيرة حتى نخلي cleanup شغّال فوق، وبنرجع من دون
    # إشعار حتى لو كل الفحص مر بسلام)


def _mark_if_new(db_session, user_id: int, course_id: str, item_type: str, item_key: str) -> bool:
    """يرجع True ويسجل العنصر لو ما كان مشاف قبل هيك، False لو مشاف أصلاً."""
    exists = (
        db_session.query(SeenItem)
        .filter_by(user_id=user_id, item_type=item_type, item_key=item_key)
        .first()
    )
    if exists:
        return False
    db_session.add(SeenItem(user_id=user_id, course_id=str(course_id),
                             item_type=item_type, item_key=item_key))
    return True


async def _send_notifications(context, telegram_id, full_name, email, email_notify, new_items):
    display_name = full_name or "عزيزي الطالب"
    lines = []
    for it in new_items[:10]:  # حد أقصى حتى ما تطول رسالة تليجرام كتير
        # esc() لأن نصوص مودل الخام (أسماء المواد والواجبات) ممكن تحتوي
        # على < أو & بتكسر parse_mode="HTML" (اسم المادة «برمجة <3» مثال)
        if it["kind"] == "assignment":
            lines.append(
                f"📝 <b>واجب جديد</b> بمادة <b>{esc(it['course'])}</b>\n"
                f"   {esc(it['name'])}\n"
                f"   ⏰ الموعد النهائي: {esc(it['due'])}"
            )
        else:
            lines.append(
                f"📢 <b>إعلان جديد</b> بمادة <b>{esc(it['course'])}</b>\n"
                f"   {esc(it['name'])}"
            )
    extra = f"\n\n…وفي {len(new_items) - 10} تحديث إضافي." if len(new_items) > 10 else ""
    text = f"🔔 عزيزي <b>{esc(display_name)}</b>، عندك تحديثات جديدة:\n\n" + "\n\n".join(lines) + extra

    try:
        await context.bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.warning("failed to Telegram-notify %s: %s", telegram_id, e)

    if email_notify and email:
        plain_lines = [
            f"- {'واجب' if it['kind'] == 'assignment' else 'إعلان'}: {it['name']} "
            f"({it['course']})" + (f" — الموعد: {it['due']}" if it.get('due') else "")
            for it in new_items
        ]
        body = f"عزيزي {display_name}،\n\nعندك تحديثات جديدة على مقرراتك:\n\n" + "\n".join(plain_lines)
        await send_email(email, "🔔 تحديثات جديدة على مقرراتك", body)
