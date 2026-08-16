from bot.services.moodle_scraper import MoodleClient

# مخزن الجلسات لكل مستخدم
_user_clients: dict[int, MoodleClient] = {}

def get_client(user_id: int) -> MoodleClient:
    """جلب أو إنشاء عميل Moodle للمستخدم."""
    if user_id not in _user_clients or _user_clients[user_id]._session is None:
        _user_clients[user_id] = MoodleClient()
    return _user_clients[user_id]

async def close_client(user_id: int):
    """إغلاق جلسة المستخدم."""
    if user_id in _user_clients:
        await _user_clients[user_id].close()
        del _user_clients[user_id]