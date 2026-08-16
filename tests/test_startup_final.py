# -*- coding: utf-8 -*-
import asyncio
import time
import unittest
from unittest.mock import MagicMock, patch

# نحاكي الـ modules المطلوبة لـ main.py
import sys
from types import ModuleType

# Mocking modules to avoid actual network/db calls
mock_tg = ModuleType("telegram")
mock_tg_ext = ModuleType("telegram.ext")
sys.modules["telegram"] = mock_tg
sys.modules["telegram.ext"] = mock_tg_ext

class MockApplication:
    def __init__(self, is_modern=True):
        self.bot_data = {}
        self.job_queue = MagicMock()
        if is_modern:
            self.run_until_disconnected = MagicMock()
        self.run_polling = MagicMock()
        self.add_handler = MagicMock()

class MockBuilder:
    def __init__(self):
        self._token = None
    def token(self, t):
        self._token = t
        return self
    def build(self):
        return MockApplication()

mock_tg_ext.Application = MockApplication
mock_tg_ext.Application.builder = MockBuilder

# اختبار منطق main() الجديد
class StartupTests(unittest.TestCase):
    def setUp(self):
        # تحميل الملف يدوياً لتجنب مشاكل الاستيراد مع الـ mocks
        with open("/home/ubuntu/bot_final/main.py", "r", encoding="utf-8") as f:
            code = f.read()
        
        self.mod = ModuleType("main_module")
        # Mock dependencies قبل التنفيذ
        self.mod.init_db = MagicMock()
        self.mod.scoped_session = MagicMock()
        self.mod.Config = MagicMock()
        self.mod.Config.BOT_TOKEN = "fake_token"
        self.mod.Config.feature_enabled.return_value = True
        self.mod._setup_application = MagicMock()
        self.mod.Application = mock_tg_ext.Application
        self.mod.logger = MagicMock()
        
        # تنفيذ الكود في سياق الموديول
        exec(code, self.mod.__dict__)

    @patch("asyncio.new_event_loop")
    @patch("asyncio.set_event_loop")
    @patch("time.sleep")
    def test_modern_startup(self, mock_sleep, mock_set_loop, mock_new_loop):
        """اختبار الإقلاع للنسخ الحديثة (v20+)"""
        mock_loop = MagicMock()
        mock_new_loop.return_value = mock_loop
        
        # نحاكي وجود run_until_disconnected
        with patch("telegram.ext.Application.run_until_disconnected", create=True):
            app = MockApplication(is_modern=True)
            self.mod._setup_application.return_value = app
            mock_loop.run_until_complete.return_value = app
            
            # نشغل main مرة واحدة (عبر رفع استثناء يكسر الحلقة أو التحكم بـ side_effect)
            app.run_polling.side_effect = SystemExit
            
            with self.assertRaises(SystemExit):
                self.mod.main()
            
            app.run_polling.assert_called_once()
            mock_new_loop.assert_called()

    @patch("asyncio.new_event_loop")
    @patch("asyncio.set_event_loop")
    @patch("time.sleep")
    def test_old_startup(self, mock_sleep, mock_set_loop, mock_new_loop):
        """اختبار الإقلاع للنسخ القديمة (< v20)"""
        mock_loop = MagicMock()
        mock_new_loop.return_value = mock_loop
        
        # نحاكي عدم وجود run_until_disconnected
        with patch("telegram.ext.Application", spec=True) as mock_app_cls:
            # نحذف run_until_disconnected من الـ mock
            if hasattr(mock_app_cls, "run_until_disconnected"):
                delattr(mock_app_cls, "run_until_disconnected")
            
            app = MockApplication(is_modern=False)
            self.mod._setup_application.return_value = app
            mock_loop.run_until_complete.return_value = app
            
            # كسر الحلقة بعد أول محاولة
            app.run_polling.side_effect = SystemExit
            
            with self.assertRaises(SystemExit):
                self.mod.main()
            
            app.run_polling.assert_called_with(poll_interval=2.0)

if __name__ == '__main__':
    unittest.main()
