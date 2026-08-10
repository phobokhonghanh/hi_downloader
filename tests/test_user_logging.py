import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import UserLogBuffer, user_log_buffer, log_user, get_logs, clear_logs


class TestUserLogging(unittest.TestCase):
    def setUp(self):
        user_log_buffer.clear()

    def tearDown(self):
        user_log_buffer.clear()

    def test_buffer_append_and_clear(self):
        buf = UserLogBuffer(max_size=5)
        buf.append("Test info message", "INFO")
        buf.append("Test success message", "SUCCESS")
        buf.append("Test error message", "ERROR")

        logs = buf.get_logs()
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0]["message"], "Test info message")
        self.assertEqual(logs[0]["level"], "INFO")
        self.assertEqual(logs[1]["level"], "SUCCESS")
        self.assertEqual(logs[2]["level"], "ERROR")

        buf.clear()
        self.assertEqual(len(buf.get_logs()), 0)

    def test_log_buffer_overflow(self):
        buf = UserLogBuffer(max_size=3)
        for i in range(5):
            buf.append(f"Msg {i}")

        logs = buf.get_logs()
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0]["message"], "Msg 2")
        self.assertEqual(logs[2]["message"], "Msg 4")

    def test_api_logs_functions(self):
        # Clear logs
        clear_logs()
        self.assertEqual(get_logs(), [])

        # Emit user log
        log_user("Phân tích URL thành công", level="SUCCESS")
        data = get_logs()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["message"], "Phân tích URL thành công")
        self.assertEqual(data[0]["level"], "SUCCESS")

        # Test Clear API
        res = clear_logs()
        self.assertEqual(res, {"status": "success"})
        self.assertEqual(get_logs(), [])


if __name__ == "__main__":
    unittest.main()
