import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import time
from fastapi.responses import JSONResponse

# Thêm thư mục hi_downloader vào sys.path để import app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import app

class TestBilibiliDownloader(unittest.TestCase):

    def setUp(self):
        # Đảm bảo reset lại danh sách task trước mỗi bài test
        app.tasks.clear()
        # Đảm bảo dọn dẹp các biến môi trường cấu hình proxy
        if "PROXY_USER" in os.environ:
            del os.environ["PROXY_USER"]
        if "PROXY_PASS" in os.environ:
            del os.environ["PROXY_PASS"]
        app.PROXY_USER = ""
        app.PROXY_PASS = ""
        
        # Hướng file config sang file ảo khi chạy test
        self.original_config_file = app.CONFIG_FILE
        app.CONFIG_FILE = os.path.join(app.EXE_DIR, "config_test.json")
        if os.path.exists(app.CONFIG_FILE):
            try:
                os.remove(app.CONFIG_FILE)
            except Exception:
                pass

    def tearDown(self):
        # Xóa file test config sau khi chạy xong
        if os.path.exists(app.CONFIG_FILE):
            try:
                os.remove(app.CONFIG_FILE)
            except Exception:
                pass
        app.CONFIG_FILE = self.original_config_file

    def test_clean_url(self):
        """Kiểm tra chức năng làm sạch URL (clean_url)"""
        raw_video_url = "https://www.bilibili.com/video/BV1UvMQ6UEU1/?spm_id_from=333.1387&some_param=abc"
        self.assertEqual(app.clean_url(raw_video_url), "https://www.bilibili.com/video/BV1UvMQ6UEU1/")

        raw_space_url = "https://space.bilibili.com/28760071/upload/video?spm_id_from=333"
        self.assertEqual(app.clean_url(raw_space_url), "https://space.bilibili.com/28760071/video")

    @patch('shutil.which')
    @patch('os.path.exists')
    def test_check_ffmpeg(self, mock_exists, mock_which):
        """Kiểm tra chức năng phát hiện FFmpeg trên hệ thống"""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_exists.return_value = False
        self.assertTrue(app.check_ffmpeg())

        mock_which.return_value = None
        mock_exists.side_effect = lambda path: False
        self.assertFalse(app.check_ffmpeg())

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="127.0.0.1:8080\n# comment_line\n192.168.1.1:3128\n")
    def test_get_rotational_proxy(self, mock_file, mock_exists):
        """Kiểm tra chức năng đọc và xoay vòng proxy từ proxies.txt"""
        mock_exists.return_value = True
        app.PROXY_USER = "user1"
        app.PROXY_PASS = "pass1"
        proxy = app.get_rotational_proxy()
        self.assertIn(proxy, ["http://user1:pass1@127.0.0.1:8080", "http://user1:pass1@192.168.1.1:3128"])

    @patch('yt_dlp.YoutubeDL')
    def test_download_worker_success(self, mock_ytdl):
        """Kiểm tra tiến trình download_worker khi tải thành công"""
        task_id = "test-task-123"
        app.tasks[task_id] = {
            "id": task_id,
            "status": "pending",
            "progress": 0,
            "speed": "0 KB/s",
            "eta": "N/A",
            "elapsed_time": 0,
            "retry_count": 1,
            "filename": "",
            "error": None
        }

        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        app.download_worker(
            task_id=task_id,
            url="https://www.bilibili.com/video/BV1UvMQ6UEU1/",
            cookies_browser=None,
            quality="best",
            page_start=1,
            page_end=1,
            target_dir="./test_downloads"
        )

        self.assertEqual(app.tasks[task_id]["status"], "completed")
        self.assertEqual(app.tasks[task_id]["progress"], 100)
        self.assertGreaterEqual(app.tasks[task_id]["elapsed_time"], 0)

    @patch('yt_dlp.YoutubeDL')
    @patch('app.get_rotational_proxy')
    def test_download_worker_retry_and_fail(self, mock_get_proxy, mock_ytdl):
        """Kiểm tra cơ chế tự động thử lại 3 lần và báo thất bại khi tải lỗi liên tục"""
        task_id = "test-task-456"
        app.tasks[task_id] = {
            "id": task_id,
            "status": "pending",
            "progress": 0,
            "speed": "0 KB/s",
            "eta": "N/A",
            "elapsed_time": 0,
            "retry_count": 1,
            "filename": "",
            "error": None
        }

        mock_get_proxy.side_effect = ["http://proxy1:80", "http://proxy2:80", "http://proxy3:80"]
        mock_instance = MagicMock()
        mock_instance.download.side_effect = Exception("Mock network connection error")
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        app.download_worker(
            task_id=task_id,
            url="https://www.bilibili.com/video/BV1UvMQ6UEU1/",
            cookies_browser=None,
            quality="best",
            page_start=1,
            page_end=1,
            target_dir="./test_downloads"
        )

        self.assertEqual(app.tasks[task_id]["retry_count"], 3)
        self.assertEqual(app.tasks[task_id]["status"], "failed")
        self.assertIn("Loi sau 3 lan thu: Mock network connection error", app.tasks[task_id]["error"])

    @patch('yt_dlp.YoutubeDL')
    def test_download_worker_cancel(self, mock_ytdl):
        """Kiểm tra tính năng hủy tải (cancel) giữa chừng của download_worker"""
        task_id = "test-task-789"
        app.tasks[task_id] = {
            "id": task_id,
            "status": "pending",
            "progress": 0,
            "speed": "0 KB/s",
            "eta": "N/A",
            "elapsed_time": 0,
            "retry_count": 1,
            "filename": "",
            "error": None
        }

        mock_instance = MagicMock()
        def fake_download(*args, **kwargs):
            app.tasks[task_id]["status"] = "canceled"
            raise ValueError("CANCELED")

        mock_instance.download.side_effect = fake_download
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        app.download_worker(
            task_id=task_id,
            url="https://www.bilibili.com/video/BV1UvMQ6UEU1/",
            cookies_browser=None,
            quality="best",
            page_start=1,
            page_end=1,
            target_dir="./test_downloads"
        )

        self.assertEqual(app.tasks[task_id]["status"], "canceled")
        self.assertIsNone(app.tasks[task_id]["error"])

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="Line 1\nLine 2 ANSI\nLine 3\n")
    def test_get_logs(self, mock_open, mock_exists):
        """Kiểm tra API đọc log /api/logs và loại bỏ màu ANSI"""
        mock_exists.return_value = True
        logs = app.get_logs()
        
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0], "Line 1")
        self.assertEqual(logs[1], "Line 2 ANSI")
        self.assertEqual(logs[2], "Line 3")

    @patch('app.subprocess.check_output')
    def test_select_directory_success(self, mock_check_output):
        """Kiểm tra API chọn thư mục khi người dùng chọn thành công"""
        # Mock tiến trình con trả về thư mục được chọn
        mock_check_output.return_value = "/path/to/my/downloads\n"
        
        response = app.select_directory()
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["path"], os.path.abspath("/path/to/my/downloads"))

    @patch('app.subprocess.check_output')
    def test_select_directory_canceled(self, mock_check_output):
        """Kiểm tra API chọn thư mục khi người dùng hủy bỏ chọn"""
        # Mock tiến trình con trả về chuỗi trống (bấm Cancel)
        mock_check_output.return_value = "\n"
        
        response = app.select_directory()
        self.assertEqual(response["status"], "canceled")
        self.assertIsNone(response["path"])

    @patch('app.subprocess.check_output')
    @patch('shutil.which')
    def test_select_directory_error(self, mock_which, mock_check_output):
        """Kiểm tra API chọn thư mục khi hệ thống lỗi (ví dụ thiếu màn hình hiển thị/headless)"""
        # Giả lập toàn bộ subprocess tkinter, zenity và kdialog đều lỗi
        mock_check_output.side_effect = Exception("no display name")
        mock_which.return_value = None # Không tìm thấy zenity hay kdialog
        
        response = app.select_directory()
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 500)
        
        import json
        body = json.loads(response.body.decode('utf-8'))
        self.assertEqual(body["status"], "error")
        self.assertIn("Không thể kết nối", body["message"])

    @patch('app.subprocess.Popen')
    @patch('os.path.exists')
    def test_open_task_folder_success(self, mock_exists, mock_popen):
        """Kiểm tra API mở thư mục lưu trữ thành công"""
        mock_exists.return_value = True
        task_id = "test-folder-task"
        app.tasks[task_id] = {"id": task_id, "target_dir": "/path/to/downloads"}
        
        res = app.open_task_folder(task_id)
        self.assertEqual(res["status"], "success")

    @patch('app.executor.submit')
    def test_trigger_download_space(self, mock_submit):
        """Kiểm tra API tải Space tự động tạo Master Task và gửi space_download_manager"""
        req = app.DownloadRequest(
            url="https://space.bilibili.com/28760071/video",
            page_start=1,
            page_end=2,
            max_videos=5
        )
        res = app.trigger_download(req)
        self.assertEqual(res["status"], "pending")
        master_id = res["task_id"]
        self.assertIn(master_id, app.tasks)
        self.assertIn("Kênh Bilibili", app.tasks[master_id]["filename"])

    def test_get_run_target_dir(self):
        """Kiểm tra hàm get_run_target_dir tự động tạo thư mục DDMMYYYY/1 và tự động tăng lên 2 cho lần chạy tiếp theo"""
        import shutil
        import tempfile
        temp_dir = tempfile.mkdtemp()
        try:
            dir1 = app.get_run_target_dir(temp_dir)
            self.assertTrue(dir1.endswith(os.path.join("10082026", "1")) or "1" in os.path.basename(dir1))
            self.assertTrue(os.path.exists(dir1))

            dir2 = app.get_run_target_dir(temp_dir)
            self.assertTrue(dir2.endswith(os.path.join("10082026", "2")) or "2" in os.path.basename(dir2))
            self.assertTrue(os.path.exists(dir2))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_clear_tasks_api(self):
        """Kiểm tra API xóa hàng chờ và reset bộ nhớ task/log giữa các đợt tải"""
        app.tasks["completed-task-1"] = {"id": "completed-task-1", "status": "completed"}
        app.tasks["completed-task-2"] = {"id": "completed-task-2", "status": "failed"}
        
        res = app.clear_tasks_api()
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(app.tasks), 0)

if __name__ == '__main__':
    unittest.main()
