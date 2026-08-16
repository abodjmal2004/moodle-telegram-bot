"""
Rich Text Builder — لبناء رسائل فيها Bold/Italic + Premium Custom Emoji سوا.

ليش هاد الملف؟
────────────────
تليجرام ما بيسمح تستخدم parse_mode (HTML/Markdown) و entities بنفس الرسالة
بنفس الوقت — لازم توحد الطريقة. وكمان الـ offset/length لازم يكونوا بوحدة
UTF-16 code units مش عدد الأحرف العادي (Python len()) — أي إيموجي أو حرف
خارج نطاق BMP بياخد وحدتين مش وحدة، والعد اليدوي بينكسر بسهولة.

هاد الملف بيبني النص والـ entities (bold/italic/custom_emoji) مع بعض من
قائمة "قطع" (Segment)، وبيحسب الـ offsets تلقائياً — ما في عد يدوي إطلاقاً.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from telegram import MessageEntity


def _utf16_len(text: str) -> int:
    """طول النص بوحدة UTF-16 code units (اللي تليجرام بيحسب فيها offset/length)."""
    return len(text.encode("utf-16-le")) // 2


@dataclass
class Segment:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    # لو حاب تحط إيموجي بريميوم: خلي الـ text حرف إيموجي عادي (placeholder)
    # زي "⭐" أو "💎"، وحط الـ custom_emoji_id هون. تليجرام بيعرض الإيموجي
    # البريميوم بدل الـ placeholder لعنده Premium، وبيعرض الـ placeholder
    # العادي لعنده ما عندوش Premium (fallback تلقائي، مش لازم تعمل إشي إضافي).
    custom_emoji_id: Optional[str] = None


def build_rich_message(segments: List[Segment]) -> Tuple[str, List[MessageEntity]]:
    """يرجع (text, entities) جاهزين للإرسال بـ entities= أو caption_entities=
    (بدون parse_mode أبداً — الاثنين ما بينحطوا سوا)."""
    full_text = ""
    entities: List[MessageEntity] = []

    for seg in segments:
        offset = _utf16_len(full_text)
        length = _utf16_len(seg.text)

        if length > 0:
            if seg.bold:
                entities.append(MessageEntity(type=MessageEntity.BOLD, offset=offset, length=length))
            if seg.italic:
                entities.append(MessageEntity(type=MessageEntity.ITALIC, offset=offset, length=length))
            if seg.code:
                entities.append(MessageEntity(type=MessageEntity.CODE, offset=offset, length=length))
            if seg.custom_emoji_id:
                entities.append(MessageEntity(
                    type=MessageEntity.CUSTOM_EMOJI,
                    offset=offset,
                    length=length,
                    custom_emoji_id=seg.custom_emoji_id,
                ))

        full_text += seg.text

    return full_text, entities
