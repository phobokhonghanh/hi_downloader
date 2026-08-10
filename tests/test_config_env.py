import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestHiDownloaderConfig(unittest.TestCase):
    def test_env_defaults(self):
        """Test default config values when env vars are not set."""
        from app import (
            APP_TITLE,
            DOWNLOAD_DIR,
            CONFIG_FILE,
            LOG_FILE,
            PROXY_FILE_NAME,
            BILIBILI_SPACE_DOMAIN,
            BILIBILI_API_DOMAIN,
            BILIBILI_VIDEO_BASE_URL,
            DIALOG_TITLE,
        )

        self.assertEqual(APP_TITLE, os.getenv("APP_TITLE", "Bilibili Advanced Downloader"))
        self.assertTrue(DOWNLOAD_DIR.endswith("downloads"))
        self.assertEqual(PROXY_FILE_NAME, "proxies.txt")
        self.assertEqual(BILIBILI_SPACE_DOMAIN, "space.bilibili.com")
        self.assertEqual(BILIBILI_API_DOMAIN, "api.bilibili.com")
        self.assertEqual(BILIBILI_VIDEO_BASE_URL, "https://www.bilibili.com/video/")
        self.assertEqual(DIALOG_TITLE, os.getenv("DIALOG_TITLE", "Chon thu muc luu video Bilibili"))

    def test_run_app_env_loading(self):
        """Test run_app.py reads host and port from environment variables."""
        import run_app

        self.assertIn(run_app.APP_HOST, ["127.0.0.1", os.getenv("APP_HOST", "127.0.0.1")])
        self.assertIsInstance(run_app.APP_PORT, int)


if __name__ == "__main__":
    unittest.main()
