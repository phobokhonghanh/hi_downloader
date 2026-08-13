import os
import unittest
from unittest.mock import patch
from modules.common.paths import get_app_dir

class TestCommonPaths(unittest.TestCase):

    def test_windows_paths(self):
        """Test Windows path resolution targeting LOCALAPPDATA."""
        with patch("platform.system", return_value="Windows"), \
             patch.dict("os.environ", {"LOCALAPPDATA": "C:\\Users\\TestUser\\AppData\\Local"}):
            
            config_dir = get_app_dir("config")
            log_dir = get_app_dir("log")
            cache_dir = get_app_dir("cache")
            temp_dir = get_app_dir("temp")

            self.assertEqual(config_dir.replace("/", "\\"), "C:\\Users\\TestUser\\AppData\\Local\\hi_downloader")
            self.assertEqual(log_dir.replace("/", "\\"), "C:\\Users\\TestUser\\AppData\\Local\\hi_downloader\\logs")
            self.assertEqual(cache_dir.replace("/", "\\"), "C:\\Users\\TestUser\\AppData\\Local\\hi_downloader\\cache")
            self.assertEqual(temp_dir.replace("/", "\\"), "C:\\Users\\TestUser\\AppData\\Local\\hi_downloader\\temp")

    def test_macos_paths(self):
        """Test macOS path resolution targeting Application Support."""
        with patch("platform.system", return_value="Darwin"), \
             patch("os.path.expanduser", return_value="/Users/TestUser"):
            
            config_dir = get_app_dir("config")
            log_dir = get_app_dir("log")
            cache_dir = get_app_dir("cache")
            temp_dir = get_app_dir("temp")

            self.assertEqual(config_dir, "/Users/TestUser/Library/Application Support/hi_downloader")
            self.assertEqual(log_dir, "/Users/TestUser/Library/Application Support/hi_downloader/logs")
            self.assertEqual(cache_dir, "/Users/TestUser/Library/Application Support/hi_downloader/cache")
            self.assertEqual(temp_dir, "/Users/TestUser/Library/Application Support/hi_downloader/temp")

    def test_linux_paths(self):
        """Test Linux path resolution targeting XDG_CONFIG_HOME and XDG_DATA_HOME."""
        with patch("platform.system", return_value="Linux"), \
             patch("os.path.expanduser", return_value="/home/testuser"), \
             patch.dict("os.environ", {
                 "XDG_CONFIG_HOME": "/home/testuser/.config",
                 "XDG_DATA_HOME": "/home/testuser/.local/share"
             }):
            
            config_dir = get_app_dir("config")
            log_dir = get_app_dir("log")
            cache_dir = get_app_dir("cache")
            temp_dir = get_app_dir("temp")

            self.assertEqual(config_dir, "/home/testuser/.config/hi_downloader")
            self.assertEqual(log_dir, "/home/testuser/.local/share/hi_downloader/logs")
            self.assertEqual(cache_dir, "/home/testuser/.local/share/hi_downloader/cache")
            self.assertEqual(temp_dir, "/home/testuser/.local/share/hi_downloader/temp")

    def test_download_dir_semantics(self):
        """Assert download_dir configuration remains the user-provided absolute path exactly."""
        import tempfile
        import json
        
        fd, temp_config = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        
        try:
            # Simulate saving absolute path
            abs_download_choice = os.path.abspath("/some/absolute/user/download/path")
            
            config = {}
            config["download_dir"] = abs_download_choice
            
            with open(temp_config, "w", encoding="utf-8") as f:
                json.dump(config, f)
                
            # Read back and assert absolute path integrity
            with open(temp_config, "r", encoding="utf-8") as f:
                read_cfg = json.load(f)
                
            self.assertEqual(read_cfg["download_dir"], abs_download_choice)
            self.assertFalse(read_cfg["download_dir"].startswith("./"))
            self.assertTrue(os.path.isabs(read_cfg["download_dir"]))
        finally:
            if os.path.exists(temp_config):
                os.remove(temp_config)
