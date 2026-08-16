"""
HTML Escaping — حماية parse_mode="HTML" من نصوص مودل/مستخدم الخام.
────────────────────────────────────────────────────────────────────
كل النصوص اللي جاية من موقع الجامعة (أسماء المواد، أسماء الواجبات،
الإعلانات، الأخطاء) أو من المستخدم بتُنحط جوا parse_mode="HTML" —
لو فيها < أو > أو & بتكسر الرسالة كلها أو بتنتج أوسمة تالفة.
هاد الموديل بيوفّر esc() اللي بتفريم الحروف الخاصة وترجع <b> آمن.
"""
import html as _html


def esc(text: str) -> str:
    """تفريم HTML الآمن لنص خام. quote=False لأننا بنستخدم HTML مش attributes.
    ملاحظة: <b> في نصوصنا ثابتة بالواجهة (مش من الإدخال) فمش بتتفريم."""
    if text is None:
        return ""
    return _html.escape(str(text), quote=False)


def safe(text: str) -> str:
    """نفس esc — اسم أوضح للاستخدام جوا رسائل parse_mode=HTML."""
    return esc(text)
