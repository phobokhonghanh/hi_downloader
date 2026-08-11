import unittest
from modules.downloader.schemas import AnalyzeRequestData, DownloadRequestData, DownloadTaskResult


class TestDownloaderSchemas(unittest.TestCase):
    def test_analyze_request_data_defaults(self):
        data = AnalyzeRequestData(url="https://bilibili.com/video/123")
        self.assertEqual(data.url, "https://bilibili.com/video/123")
        self.assertIsNone(data.cookies_browser)

    def test_analyze_request_data_custom(self):
        data = AnalyzeRequestData(url="https://bilibili.com/video/123", cookies_browser="firefox")
        self.assertEqual(data.cookies_browser, "firefox")

    def test_download_request_data_defaults(self):
        data = DownloadRequestData(url="https://bilibili.com/video/123")
        self.assertEqual(data.url, "https://bilibili.com/video/123")
        self.assertIsNone(data.cookies_browser)
        self.assertEqual(data.quality, "best")
        self.assertEqual(data.page_start, 1)
        self.assertEqual(data.page_end, 1)
        self.assertIsNone(data.max_videos)
        self.assertIsNone(data.output_dir)

    def test_download_request_data_custom(self):
        data = DownloadRequestData(
            url="https://bilibili.com/video/123",
            cookies_browser="chrome",
            quality="1080",
            page_start=2,
            page_end=5,
            max_videos=10,
            output_dir="/tmp/videos"
        )
        self.assertEqual(data.cookies_browser, "chrome")
        self.assertEqual(data.quality, "1080")
        self.assertEqual(data.page_start, 2)
        self.assertEqual(data.page_end, 5)
        self.assertEqual(data.max_videos, 10)
        self.assertEqual(data.output_dir, "/tmp/videos")

    def test_download_task_result_defaults(self):
        res = DownloadTaskResult(task_id="task_abc")
        self.assertEqual(res.task_id, "task_abc")
        self.assertEqual(res.status, "pending")
        self.assertIsNone(res.error)


if __name__ == "__main__":
    unittest.main()
