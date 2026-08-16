import logging

from telegram.error import BadRequest

logger = logging.getLogger(__name__)


async def safe_answer(query, text: str = None, show_alert: bool = False) -> None:
    """بديل آمن لـ query.answer().

    تليجرام بيسمح بجواب واحد بس لكل callback query — أي محاولة ثانية
    بترجع BadRequest ("Query is too old..."). بما إنه أكتر من دالة بالكود
    ممكن توصل لنفس الـ callback query (مثلاً: handler عام بيوجّه لدالة
    تانية بتحاول ترد هي كمان)، أسهل وأضمن حل هو نلف كل نداءات answer()
    بهاي الدالة بدل ما نلاحق كل تسلسل استدعاءات يدوياً ونخاطر ننسى حالة."""
    try:
        await query.answer(text=text, show_alert=show_alert)
    except BadRequest as e:
        logger.debug("callback query already answered (ignored): %s", e)
