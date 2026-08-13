import os
import json
import tempfile
import unittest
from unittest.mock import patch
from modules.downloader.service import DownloaderService, get_proxy_source_label
from core.task_store import TaskStore
from concurrent.futures import ThreadPoolExecutor

class TestDownloaderProxy(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = os.path.join(self.temp_dir.name, "config")
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Write config.json
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.write_config({"proxy_disabled": False})
        
        # Write system proxies.txt
        self.system_proxy_file = os.path.join(self.config_dir, "proxies.txt")
        self.write_file(self.system_proxy_file, "1.2.3.4:8080\n")
        
        # Write custom proxies.txt
        self.custom_proxy_file = os.path.join(self.temp_dir.name, "custom_proxies.txt")
        self.write_file(self.custom_proxy_file, "5.6.7.8:1080:usr:pwd\n")

        self.store = TaskStore()
        self.executor = ThreadPoolExecutor(max_workers=1)
        
    def tearDown(self):
        self.executor.shutdown(wait=True)
        self.temp_dir.cleanup()

    def write_config(self, data):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def write_file(self, path, content):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    @patch("modules.common.paths.get_app_dir")
    def test_unchecked_valid_custom_uses_custom(self, mock_get_app_dir):
        """Test unchecked + valid custom file uses custom."""
        mock_get_app_dir.return_value = self.config_dir
        self.write_config({
            "proxy_disabled": False,
            "proxy_file": self.custom_proxy_file
        })
        service = DownloaderService(task_store=self.store, executor=self.executor)
        proxies = service.get_all_proxies()
        self.assertEqual(proxies, ["http://usr:pwd@5.6.7.8:1080"])
        self.assertEqual(get_proxy_source_label(self.config_file), "custom proxy")

    @patch("modules.common.paths.get_app_dir")
    def test_unchecked_no_custom_uses_system(self, mock_get_app_dir):
        """Test unchecked + no custom uses system."""
        mock_get_app_dir.return_value = self.config_dir
        self.write_config({
            "proxy_disabled": False,
            "proxy_file": None
        })
        service = DownloaderService(task_store=self.store, executor=self.executor)
        proxies = service.get_all_proxies()
        self.assertEqual(proxies, ["http://1.2.3.4:8080"])
        self.assertEqual(get_proxy_source_label(self.config_file), "system proxy")

    @patch("modules.common.paths.get_app_dir")
    def test_checked_bypasses_both(self, mock_get_app_dir):
        """Test checked bypasses both."""
        mock_get_app_dir.return_value = self.config_dir
        self.write_config({
            "proxy_disabled": True,
            "proxy_file": self.custom_proxy_file
        })
        service = DownloaderService(task_store=self.store, executor=self.executor)
        proxies = service.get_all_proxies()
        self.assertEqual(proxies, [None])
        self.assertEqual(get_proxy_source_label(self.config_file), "Không dùng proxy")

    @patch("modules.common.paths.get_app_dir")
    def test_old_proxy_mode_configs_do_not_break(self, mock_get_app_dir):
        """Test old proxy_mode configs do not break backward compatibility."""
        mock_get_app_dir.return_value = self.config_dir
        
        # Mode system -> unchecked, uses system
        self.write_config({"proxy_mode": "system"})
        service = DownloaderService(task_store=self.store, executor=self.executor)
        self.assertEqual(service.get_all_proxies(), ["http://1.2.3.4:8080"])
        self.assertEqual(get_proxy_source_label(self.config_file), "system proxy")

        # Mode custom -> unchecked, uses custom
        self.write_config({
            "proxy_mode": "custom",
            "proxy_file": self.custom_proxy_file
        })
        self.assertEqual(service.get_all_proxies(), ["http://usr:pwd@5.6.7.8:1080"])
        self.assertEqual(get_proxy_source_label(self.config_file), "custom proxy")

        # Mode none -> checked, bypasses both
        self.write_config({"proxy_mode": "none"})
        self.assertEqual(service.get_all_proxies(), [None])
        self.assertEqual(get_proxy_source_label(self.config_file), "Không dùng proxy")

    @patch("modules.common.paths.get_app_dir")
    def test_no_proxy_available_label(self, mock_get_app_dir):
        """Test 'Không có proxy khả dụng' when unchecked but both files empty or missing."""
        mock_get_app_dir.return_value = self.config_dir
        self.write_config({
            "proxy_disabled": False,
            "proxy_file": "/nonexistent/path.txt"
        })
        # Empty the system proxy file
        self.write_file(self.system_proxy_file, "")
        
        service = DownloaderService(task_store=self.store, executor=self.executor)
        self.assertEqual(service.get_all_proxies(), [None])
        self.assertEqual(get_proxy_source_label(self.config_file), "Không có proxy khả dụng")
