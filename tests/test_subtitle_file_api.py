import os
import tempfile
import unittest
from fastapi import HTTPException

from modules.subtitle.batch_service import scan_video_folder, save_imported_srt
from app import api_scan_folder, api_save_imported_srt, ScanFolderRequest, SaveImportedSrtRequest


class TestSubtitleFileApi(unittest.TestCase):
    def test_scan_video_folder_flat_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create video files in top directory
            v1 = os.path.join(tmpdir, "video_b.mp4")
            v2 = os.path.join(tmpdir, "video_a.MKV")  # case sensitivity test
            # Create subfolder with another video file
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)
            v3 = os.path.join(subdir, "video_c.mp4")
            # Create non-video file
            txt = os.path.join(tmpdir, "doc.txt")
            
            for path in [v1, v2, v3, txt]:
                with open(path, "w") as f:
                    f.write("mock content")

            # Scan folder
            res = scan_video_folder(tmpdir)
            self.assertEqual(res["total"], 2)
            self.assertEqual(len(res["files"]), 2)
            # Check sorting: video_a.MKV then video_b.mp4
            self.assertEqual(res["files"][0]["name"], "video_a.MKV")
            self.assertEqual(res["files"][1]["name"], "video_b.mp4")

    def test_scan_video_folder_missing_and_invalid(self):
        with self.assertRaises(ValueError):
            scan_video_folder("/non/existent/path")
            
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "regular_file.txt")
            with open(file_path, "w") as f:
                f.write("mock")
            with self.assertRaises(ValueError):
                scan_video_folder(file_path)

    def test_scan_video_folder_ignores_symlink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "target.mp4")
            with open(target, "w") as f:
                f.write("target content")
                
            symlink_path = os.path.join(tmpdir, "link.mp4")
            try:
                os.symlink(target, symlink_path)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported in this environment")

            res = scan_video_folder(tmpdir)
            # link.mp4 should be ignored because it is a symlink
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["files"][0]["name"], "target.mp4")

    def test_save_imported_srt_atomic_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "source.srt")
            with open(source, "w", encoding="utf-8") as f:
                f.write("Original SRT Content")

            content_edit_1 = "Edited Content V1 (Tiếng Việt)"
            res1 = save_imported_srt(source, content_edit_1)
            
            # Check target path is <stem>_edit.srt
            expected_saved_path = os.path.join(tmpdir, "source_edit.srt")
            self.assertEqual(res1["saved_path"], expected_saved_path)
            self.assertTrue(os.path.exists(expected_saved_path))
            
            # Verify original content is intact
            with open(source, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "Original SRT Content")
                
            # Verify edit file has UTF-8 contents
            with open(expected_saved_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), content_edit_1)

            # Test overwrite functionality
            content_edit_2 = "Edited Content V2"
            res2 = save_imported_srt(source, content_edit_2)
            self.assertEqual(res2["saved_path"], expected_saved_path)
            with open(expected_saved_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), content_edit_2)

    def test_api_route_functions_error_mapping(self):
        # 1. Test scan-folder missing path mapping
        req_scan = ScanFolderRequest(folder_path="/non/existent/path")
        with self.assertRaises(HTTPException) as ctx:
            api_scan_folder(req_scan)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Thư mục không tồn tại", ctx.exception.detail)

        # 2. Test save-srt missing file mapping
        req_save = SaveImportedSrtRequest(source_path="/non/existent/file.srt", content="text")
        with self.assertRaises(HTTPException) as ctx:
            api_save_imported_srt(req_save)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Tệp nguồn không tồn tại", ctx.exception.detail)

    def test_select_video_folder_does_not_mutate_cache(self):
        from app import select_video_folder, load_cached_dir
        import unittest.mock as mock
        
        old_cache = load_cached_dir()
        
        with mock.patch("subprocess.check_output") as mock_check, \
             mock.patch("shutil.which", return_value="/usr/bin/zenity"):
            mock_check.return_value = "/tmp/mock_folder\n"
            
            res = select_video_folder()
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["path"], "/tmp/mock_folder")
            
            new_cache = load_cached_dir()
            self.assertEqual(old_cache, new_cache)


if __name__ == "__main__":
    unittest.main()
