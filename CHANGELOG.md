# CHANGELOG

## 2026-08-11 — النسخة النهائية المستقرة

### Removed
- **حذف ميزة `/tracker` (فحص الأداء الدراسي)** نهائياً من المشروع بالكامل:
  - أُزيل الأمر من `main.py` + كل الدوال ذات الصلة (`cmd_tracker`, `show_tracker_menu`, ...) من `bot/handlers/tasks.py`.
  - أُزيلت كل الرسائل والأيقونات والإيموجيات الخاصة بالـ tracker من `bot/utils/emojis.py`.
  - أُزيلت الميزة من قائمة Feature Flags في `bot/config.py` و `features` في `.env.example`.
  - النتيجة: 0 `NameError` على الإقلاع (كان `cmd_tracker` هو سبب الكراش الأخير).

### Fixed — إقلاع عالمي متوافق مع أي نسخة PTB (بدون pip upgrade)
- **جذر المشكلة**: `application.run_until_disconnected()` موجودة فقط في PTB >= 20. سيرفر المستخدم يملك نسخة أقدم، فكان البوت ينكسر بـ `AttributeError` ثم `RuntimeWarning` عند محاولة الـ fallback اليدوي (استدعاء كوروتين بدون `await`).
- **الحل**: دالة `_run_bot_24_7()` في `main.py` تفحص عند الإقلاع:
  - `hasattr(application, "run_until_disconnected")` == True → تستخدم `run_until_disconnected()` (PTB حديث).
  - == False → تستخدم `application.run_polling(poll_interval=2)` المتزامنة القديمة (PTB قديم).
- لا `await` خارج دالة `async`، ولا `initialize()`/`start()` يدوي — لا تحذيرات `RuntimeWarning` نهائياً.

### Fixed — استقرار 24/7
- حلقة حماية دائرية: أي استثناء غير متوقع → `time.sleep(5)` ثم إعادة الاتصال تلقائياً.
- `drop_pending_updates=False` (افتراضي) — الرسائل اللي وصلت قبل الإقلاع ما بتنمسح.

### Verified
- فحص كامل: `py_compile` على كل الملفات = OK، كل الـ imports = OK، 0 `RuntimeWarning` على النمطين (قديم/حديث) — مثبت عبر `tests/test_boot_logic.py`.

## إصدارات سابقة
- إضافة نظام إشعارات دوري (Telegram + Email) عبر APScheduler.
- أوامر أدمن متقدمة: `/userfind`, `/tune`, `/health`, `/broadcast`.
- تفضيلات إشعارات لكل مادة (`/prefs`, `/togglecourse`) + قاعدة بيانات SQLite بوضع WAL.
- إصلاح روابط صورة الترحيب + تنظيف HTML للغة العربية RTL.
- حل سباق الـ `scoped_session` في المهام الخلفية.
- scraper يعتمد على `aiohttp`/BS4 مع AJAX re-login وفحص صحة متكرر.
