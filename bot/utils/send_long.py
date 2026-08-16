"""
Long Message Splitter — تقسيم الرسائل اللي بتتجاوز 4096 حرف (حد تليجرام).
─────────────────────────────────────────────────────────────────────────
تليجرام بيرفض الرسائل > 4096 حرف بخطأ Message is too long. هاد الموديل
بيقسم الرسالة على أسطر كاملة (ما بيكسر سطر نصفي) ويرسلها كقطع متتالية.
"""
MAX_LEN = 4000  # هامش أمان تحت 4096


async def send_long_message(context, chat_id, text: str, **kwargs):
    """يرسل text على chat_id مقسمة إذا لزمت. kwargs زي parse_mode/entities.
    أول قطعة بتستخدم kwargs كاملة؛ باقي القطع بتنزل بدون reply_markup
    (الردود على الزر لازم تكون بالرسالة الأولى بس)."""
    if len(text) <= MAX_LEN:
        await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return

    chunks = _split(text, MAX_LEN)
    for i, chunk in enumerate(chunks):
        part_kwargs = dict(kwargs)
        if i > 0:
            part_kwargs.pop("reply_markup", None)
        await context.bot.send_message(chat_id=chat_id, text=chunk, **part_kwargs)


async def edit_long_message(context, message, text: str, **kwargs):
    """نفس المنطق للـ edit_message_text."""
    if len(text) <= MAX_LEN:
        await message.edit_message_text(text=text, **kwargs)
        return
    for i, chunk in enumerate(_split(text, MAX_LEN)):
        part_kwargs = dict(kwargs)
        if i > 0:
            part_kwargs.pop("reply_markup", None)
        await message.edit_message_text(text=chunk, **part_kwargs)


def _split(text: str, max_len: int):
    """يقسم على \n boundaries. لو سطر واحد أطول من max_len بينكسر حرفياً."""
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            while len(line) > max_len:
                chunks.append(line[:max_len])
                line = line[max_len:]
            current = line
        else:
            current = (current + "\n" + line).lstrip("\n")
    if current:
        chunks.append(current)
    return chunks or [""]
