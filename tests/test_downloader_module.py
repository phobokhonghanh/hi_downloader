import unittest
import threading
from unittest.mock import MagicMock, patch
from core.base_module import ModuleContext, ModuleResult
from modules.downloader.module import DownloaderModule
from modules.downloader.schemas import AnalyzeRequestData, DownloadRequestData, DownloadTaskResult


class TestDownloaderModule(unittest.TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.module = DownloaderModule(self.mock_service)

    def test_metadata_exists(self):
        meta = self.module.metadata
        self.assertEqual(meta.module_id, "downloader")
        self.assertEqual(meta.name, "Downloader Module")
        self.assertTrue(meta.supports_standalone)
        self.assertTrue(meta.supports_workflow)

    def test_validate_params(self):
        # Empty parameters
        self.assertFalse(self.module.validate_params({}))
        # Missing URL
        self.assertFalse(self.module.validate_params({"action": "analyze"}))
        # Empty URL
        self.assertFalse(self.module.validate_params({"action": "analyze", "url": ""}))
        # Invalid action
        self.assertFalse(self.module.validate_params({"action": "invalid_action", "url": "https://bilibili.com"}))
        # Valid parameters
        self.assertTrue(self.module.validate_params({"action": "analyze", "url": "https://bilibili.com"}))
        self.assertTrue(self.module.validate_params({"action": "download", "url": "https://bilibili.com"}))

    def test_analyze_action_calls_service(self):
        mock_result = {"title": "Test Title", "type": "video"}
        self.mock_service.analyze.return_value = mock_result
        
        ctx = ModuleContext(
            task_id="test_task_1",
            params={"action": "analyze", "url": "https://bilibili.com/video/BV123"}
        )
        res = self.module.run(ctx)
        
        self.assertTrue(res.success)
        self.assertFalse(res.canceled)
        self.assertEqual(res.metrics["analysis"], mock_result)
        self.mock_service.analyze.assert_called_once()

    def test_download_action_calls_service(self):
        mock_result = DownloadTaskResult(task_id="dl_id_123", status="pending")
        self.mock_service.start_download.return_value = mock_result
        
        ctx = ModuleContext(
            task_id="test_task_2",
            params={"action": "download", "url": "https://bilibili.com/video/BV123", "quality": "1080"}
        )
        res = self.module.run(ctx)
        
        self.assertTrue(res.success)
        self.assertFalse(res.canceled)
        self.assertEqual(res.metrics["download"]["task_id"], "dl_id_123")
        self.assertEqual(res.metrics["download"]["status"], "pending")
        self.mock_service.start_download.assert_called_once()

    def test_cancel_before_run(self):
        cancel_evt = threading.Event()
        cancel_evt.set()
        
        ctx = ModuleContext(
            task_id="test_task_3",
            params={"action": "analyze", "url": "https://bilibili.com"},
            cancel_event=cancel_evt
        )
        res = self.module.run(ctx)
        
        self.assertFalse(res.success)
        self.assertTrue(res.canceled)
        self.assertEqual(res.error, "Canceled before run")

    def test_service_exception_returns_failed_result(self):
        self.mock_service.analyze.side_effect = Exception("Network error")
        
        ctx = ModuleContext(
            task_id="test_task_4",
            params={"action": "analyze", "url": "https://bilibili.com"}
        )
        res = self.module.run(ctx)
        
        self.assertFalse(res.success)
        self.assertFalse(res.canceled)
        self.assertEqual(res.error, "Network error")


if __name__ == "__main__":
    unittest.main()
