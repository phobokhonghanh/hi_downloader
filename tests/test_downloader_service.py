import time
import unittest
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor
from core.task_store import TaskStore, TaskStatus
from modules.downloader.schemas import AnalyzeRequestData, DownloadRequestData, DownloadTaskResult
from modules.downloader.service import DownloaderService


class TestDownloaderService(unittest.TestCase):
    def setUp(self):
        self.store = TaskStore()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.service = DownloaderService(task_store=self.store, executor=self.executor)

    def tearDown(self):
        self.executor.shutdown(wait=True)

    def test_url_validation(self):
        # Valid URLs
        self.assertTrue(self.service.validate_url("https://www.bilibili.com/video/BV123"))
        self.assertTrue(self.service.validate_url("http://space.bilibili.com/999"))
        self.assertTrue(self.service.validate_url("https://bilibili.com"))
        self.assertTrue(self.service.validate_url("https://b23.tv/xyz"))
        self.assertTrue(self.service.validate_url("https://abc.b23.tv/xyz"))
        
        # Invalid URLs
        self.assertFalse(self.service.validate_url(""))
        self.assertFalse(self.service.validate_url("bilibili.com"))
        self.assertFalse(self.service.validate_url("ftp://bilibili.com"))
        self.assertFalse(self.service.validate_url("https://google.com"))
        self.assertFalse(self.service.validate_url("https://evilbilibili.com"))
        self.assertFalse(self.service.validate_url("https://bilibili.com.evil.test"))

    def test_clean_url(self):
        url = "https://space.bilibili.com/123/upload/video?some_query=abc"
        cleaned = self.service.clean_url(url)
        self.assertEqual(cleaned, "https://space.bilibili.com/123/video")

    @patch("yt_dlp.YoutubeDL")
    def test_analyze_video(self, mock_ytdl):
        # Set up mock yt-dlp response
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "title": "Test Video",
            "uploader": "Uploader Name",
            "duration": 120,
            "formats": [{"height": 1080}, {"height": 720}, {"height": 360}]
        }
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        req = AnalyzeRequestData(url="https://www.bilibili.com/video/BV123")
        res = self.service.analyze(req)
        
        self.assertEqual(res["type"], "video")
        self.assertEqual(res["title"], "Test Video")
        self.assertEqual(res["uploader"], "Uploader Name")
        self.assertEqual(len(res["qualities"]), 3)

    @patch("yt_dlp.YoutubeDL")
    def test_analyze_space(self, mock_ytdl):
        # Set up mock yt-dlp response
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "title": "Space Channel",
            "entries": [{"id": "1"}, {"id": "2"}]
        }
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        req = AnalyzeRequestData(url="https://space.bilibili.com/123")
        res = self.service.analyze(req)
        
        self.assertEqual(res["type"], "space")
        self.assertEqual(res["title"], "Space Channel")
        self.assertEqual(res["total_videos"], 2)

    @patch("yt_dlp.YoutubeDL")
    def test_start_download_video(self, mock_ytdl):
        # mock yt_dlp to avoid network downloads
        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        req = DownloadRequestData(url="https://www.bilibili.com/video/BV123", quality="1080")
        res = self.service.start_download(req)
        
        self.assertIsNotNone(res.task_id)
        self.assertEqual(res.status, "pending")
        
        # Wait for task to finish running in the worker thread
        for _ in range(50):
            t = self.store.get_task(res.task_id)
            if t and t["status"] in ("completed", "failed"):
                break
            time.sleep(0.01)

        self.executor.shutdown(wait=True)

        tasks = self.service.get_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], res.task_id)
        self.assertEqual(tasks[0]["url"], "https://www.bilibili.com/video/BV123")

    @patch("yt_dlp.YoutubeDL")
    def test_start_download_space(self, mock_ytdl):
        # mock yt_dlp to avoid network extract_info / downloads
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "title": "Space Channel",
            "entries": [{"id": "1", "title": "Video 1"}, {"id": "2", "title": "Video 2"}]
        }
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        req = DownloadRequestData(url="https://space.bilibili.com/123", quality="720", page_start=1, page_end=1)
        res = self.service.start_download(req)
        
        self.assertIsNotNone(res.task_id)
        self.assertEqual(res.status, "pending")
        
        # Wait for master task to finish extraction
        for _ in range(50):
            t = self.store.get_task(res.task_id)
            if t and t["status"] in ("completed", "failed"):
                break
            time.sleep(0.01)

        self.executor.shutdown(wait=True)

        tasks = self.service.get_tasks()
        # There should be 1 master task + 2 sub-tasks created
        self.assertEqual(len(tasks), 3)

    def test_cancel_task(self):
        self.service.executor = None
        req = DownloadRequestData(url="https://www.bilibili.com/video/BV123")
        res = self.service.start_download(req)
        
        cancel_res = self.service.cancel_task(res.task_id)
        self.assertEqual(cancel_res["status"], "canceling")
        self.assertTrue(self.store.is_canceled(res.task_id))

    def test_clear_tasks(self):
        self.store.create_task(task_id="idle_task", status="completed")
        res = self.service.clear_tasks()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["remaining"], 0)

    @patch("os.path.isfile")
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_get_all_proxies_custom_file(self, mock_open_func, mock_exists, mock_isfile):
        mock_isfile.return_value = True
        def exists_side_effect(path):
            if "config.json" in path:
                return True
            if "/custom/path/proxies.txt" in path:
                return True
            return False
        
        mock_exists.side_effect = exists_side_effect
        
        config_json_content = '{"proxy_mode": "custom", "proxy_file": "/custom/path/proxies.txt"}'
        proxy_file_content = "1.2.3.4:8080:user1:pass1\n#comment\n5.6.7.8:9090\n"
        
        from unittest.mock import mock_open
        config_open = mock_open(read_data=config_json_content)
        proxy_open = mock_open(read_data=proxy_file_content)
        
        def open_side_effect(file, *args, **kwargs):
            if "config.json" in str(file):
                return config_open()
            else:
                return proxy_open()
        
        mock_open_func.side_effect = open_side_effect
        
        self.service.config["proxy_user"] = "global_user"
        self.service.config["proxy_pass"] = "global_pass"
        
        proxies = self.service.get_all_proxies()
        self.assertEqual(len(proxies), 2)
        self.assertEqual(proxies[0], "http://user1:pass1@1.2.3.4:8080")
        self.assertEqual(proxies[1], "http://global_user:global_pass@5.6.7.8:9090")

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_get_all_proxies_fallback(self, mock_open_func, mock_exists):
        def exists_side_effect(path):
            if "config.json" in path:
                return False
            if "proxies.txt" in path:
                return True
            return False
            
        mock_exists.side_effect = exists_side_effect
        
        from unittest.mock import mock_open
        mock_open_func.side_effect = mock_open(read_data="11.22.33.44:5555\n")
        
        self.service.config["proxy_user"] = ""
        self.service.config["proxy_pass"] = ""
        
        proxies = self.service.get_all_proxies()
        self.assertEqual(len(proxies), 1)
        self.assertEqual(proxies[0], "http://11.22.33.44:5555")

    @patch("yt_dlp.YoutubeDL")
    def test_downloader_output_template_format(self, mock_ytdl):
        """Verify that downloader uses uploader folder prefix and prepends Bilibili/Video ID to filename."""
        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        req = DownloadRequestData(url="https://www.bilibili.com/video/BV123", quality="1080")
        res = self.service.start_download(req)
        
        # Wait for worker task thread execution
        for _ in range(50):
            t = self.store.get_task(res.task_id)
            if t and t["status"] in ("completed", "failed"):
                break
            time.sleep(0.01)

        # Assert yt_dlp was initialized with correct outtmpl option
        mock_ytdl.assert_called()
        init_args, init_kwargs = mock_ytdl.call_args
        ydl_opts = init_args[0] if init_args else init_kwargs.get("params", {})
        
        outtmpl = ydl_opts.get("outtmpl", "")
        self.assertTrue(outtmpl, "outtmpl is missing or empty")
        
        # Ensure it contains both uploader directory prefix and ID prefix format
        self.assertIn("%(uploader)s", outtmpl)
        self.assertIn("%(id)s_%(title)s.%(ext)s", outtmpl)
        self.assertNotIn("%(uploader)s/%(title)s.%(ext)s", outtmpl, "Found legacy title-only output template")


if __name__ == "__main__":
    unittest.main()
