import time
from telegram import Update
from telegram.ext import ContextTypes

class RateLimiter:
    def __init__(self):
        self.requests = {}
    async def check(self, user_id: int) -> bool:
        """يرجع True إذا تم حظر المستخدم (تجاوز الحد)، و False إذا كان مسموحاً له."""
        now = time.time()
        
        # تنظيف دوري للذاكرة من المستخدمين القدامى (كل 1000 طلب)
        if not hasattr(self, '_counter'): self._counter = 0
        self._counter += 1
        if self._counter % 1000 == 0:
            expired = [uid for uid, ts in self.requests.items() if not ts or now - ts[-1] > 60]
            for uid in expired: self.requests.pop(uid, None)

        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # إبقاء فقط الطلبات في آخر 60 ثانية
        self.requests[user_id] = [t for t in self.requests[user_id] if now - t < 60]
        
        # زيادة الحد ليكون 30 طلب في الدقيقة (كافٍ جداً للاستخدام الطبيعي)
        if len(self.requests[user_id]) >= 30:
            return True # محظور
            
        self.requests[user_id].append(now)
        return False # مسموح

rate_limiter = RateLimiter()

# ملاحظة: منطق تطبيق الحد فعلياً (rate_limit_gate) موجود بـ main.py
# كـ TypeHandler بـ group=-1، وهو يستخدم rate_limiter.check() من هون.