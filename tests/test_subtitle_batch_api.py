import os
import tempfile
import unittest
import threading
from fastapi import HTTPException

# We import the route functions directly from app to run decoupled tests
from app import (
    api_create_batch,
    api_get_batch,
    api_batch_action,
    CreateBatchRequest,
    BatchActionRequest,
    subtitle_batch_service
)


class TestSubtitleBatchApi(unittest.TestCase):
    def setUp(self):
        # Clear batches state in the global service before each test
        self.original_runner = subtitle_batch_service.provider_runner
        self.original_settle = subtitle_batch_service._settle_batch
        with subtitle_batch_service.lock:
            subtitle_batch_service.batches.clear()
            subtitle_batch_service.is_shutdown = False
            subtitle_batch_service.dispatcher_threads.clear()

    def tearDown(self):
        subtitle_batch_service.provider_runner = self.original_runner
        subtitle_batch_service._settle_batch = self.original_settle
        subtitle_batch_service.shutdown()

    def test_create_batch_validation(self):
        # 1. OCR provider -> HTTP 400
        req = CreateBatchRequest(video_paths=["v.mp4"], provider="ocr")
        with self.assertRaises(HTTPException) as ctx:
            api_create_batch(req)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("OCR method is not implemented yet", ctx.exception.detail)

        # 2. Unsupported provider -> HTTP 400
        req = CreateBatchRequest(video_paths=["v.mp4"], provider="invalid")
        with self.assertRaises(HTTPException) as ctx:
            api_create_batch(req)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Unsupported provider", ctx.exception.detail)

        # 3. Invalid concurrency bounds -> HTTP 400
        req = CreateBatchRequest(video_paths=["v.mp4"], provider="whisper", concurrency=0)
        with self.assertRaises(HTTPException) as ctx:
            api_create_batch(req)
        self.assertEqual(ctx.exception.status_code, 400)

        req = CreateBatchRequest(video_paths=["v.mp4"], provider="whisper", concurrency=11)
        with self.assertRaises(HTTPException) as ctx:
            api_create_batch(req)
        self.assertEqual(ctx.exception.status_code, 400)

        # 4. Empty video_paths -> HTTP 400
        req = CreateBatchRequest(video_paths=[], provider="whisper")
        with self.assertRaises(HTTPException) as ctx:
            api_create_batch(req)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_batch_with_missing_and_invalid_files(self):
        # Missing file -> HTTP 400
        req = CreateBatchRequest(video_paths=["/non/existent/video.mp4"], provider="whisper")
        with self.assertRaises(HTTPException) as ctx:
            api_create_batch(req)
        self.assertEqual(ctx.exception.status_code, 400)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Regular text file with invalid extension -> HTTP 400
            txt_file = os.path.join(tmpdir, "doc.txt")
            with open(txt_file, "w") as f:
                f.write("text")
            req = CreateBatchRequest(video_paths=[txt_file], provider="whisper")
            with self.assertRaises(HTTPException) as ctx:
                api_create_batch(req)
            self.assertEqual(ctx.exception.status_code, 400)

            # Valid video file but is actually a directory -> HTTP 400
            fake_dir_video = os.path.join(tmpdir, "video.mp4")
            os.makedirs(fake_dir_video)
            req = CreateBatchRequest(video_paths=[fake_dir_video], provider="whisper")
            with self.assertRaises(HTTPException) as ctx:
                api_create_batch(req)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_create_batch_success_and_de_duplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            v1 = os.path.join(tmpdir, "video1.mp4")
            v2 = os.path.join(tmpdir, "video2.mkv")
            for path in [v1, v2]:
                with open(path, "w") as f:
                    f.write("mock")

            # Duplicate v1 in request, verify order and de-duplication
            req = CreateBatchRequest(
                video_paths=[v1, v2, v1],
                provider="whisper",
                model="tiny",
                language="vi",
                concurrency=3
            )
            
            res = api_create_batch(req)
            self.assertIn("batch_id", res)
            self.assertIn("snapshot", res)
            
            # 2 jobs created because of de-duplication
            snap = res["snapshot"]
            self.assertEqual(len(snap["jobs"]), 2)
            self.assertEqual(snap["jobs"][0]["video_path"], os.path.abspath(v1))
            self.assertEqual(snap["jobs"][1]["video_path"], os.path.abspath(v2))
            
            # Verify custom metadata properties required by frontend
            self.assertEqual(snap["provider"], "whisper")
            self.assertEqual(snap["provider_params"]["model"], "tiny")
            self.assertEqual(snap["provider_params"]["language"], "vi")

    def test_get_batch_snapshot_mapping(self):
        # 1. Missing batch -> HTTP 404
        with self.assertRaises(HTTPException) as ctx:
            api_get_batch("non_existent_batch")
        self.assertEqual(ctx.exception.status_code, 404)

        # 2. Existing batch success
        with tempfile.TemporaryDirectory() as tmpdir:
            v = os.path.join(tmpdir, "vid.mp4")
            with open(v, "w") as f:
                f.write("mock")
            req = CreateBatchRequest(video_paths=[v], provider="whisper")
            create_res = api_create_batch(req)
            batch_id = create_res["batch_id"]

            snap = api_get_batch(batch_id)
            self.assertEqual(snap["batch_id"], batch_id)
            self.assertEqual(snap["provider"], "whisper")
            self.assertIn("provider_params", snap)

    def test_batch_actions_cancel_retry_save(self):
        # 1. Action invalid or missing batch
        with self.assertRaises(HTTPException) as ctx:
            api_batch_action("missing_batch", BatchActionRequest(action="cancel", job_ids=["job1"]))
        self.assertEqual(ctx.exception.status_code, 404)

        # Setup events and mock runner for deterministic flow
        job_entered = threading.Event()
        settle_event = threading.Event()

        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            job_entered.set()
            while not cancel_event.is_set():
                cancel_event.wait(timeout=0.01)
            return {}

        subtitle_batch_service.provider_runner = fake_runner

        original_settle = subtitle_batch_service._settle_batch
        def mock_settle(batch_id: str):
            original_settle(batch_id)
            snap = subtitle_batch_service.get_batch_snapshot(batch_id)
            if snap and snap["status"] in ("done", "error"):
                settle_event.set()

        subtitle_batch_service._settle_batch = mock_settle

        with tempfile.TemporaryDirectory() as tmpdir:
            v = os.path.join(tmpdir, "vid.mp4")
            with open(v, "w") as f:
                f.write("mock")
            req = CreateBatchRequest(video_paths=[v], provider="whisper")
            create_res = api_create_batch(req)
            batch_id = create_res["batch_id"]

            # Invalid action name -> HTTP 400
            with self.assertRaises(HTTPException) as ctx:
                api_batch_action(batch_id, BatchActionRequest(action="hacked", job_ids=["job1"]))
            self.assertEqual(ctx.exception.status_code, 400)

            # Empty job_ids -> HTTP 400
            with self.assertRaises(HTTPException) as ctx:
                api_batch_action(batch_id, BatchActionRequest(action="cancel", job_ids=[]))
            self.assertEqual(ctx.exception.status_code, 400)

            snap = api_get_batch(batch_id)
            job_id = snap["jobs"][0]["job_id"]

            # Wait for job to enter runner (so it's active 'running')
            job_entered.wait(timeout=5.0)

            # Test Cancel outcome (applied to running job)
            res_cancel = api_batch_action(batch_id, BatchActionRequest(action="cancel", job_ids=[job_id]))
            self.assertTrue(res_cancel["success"])
            self.assertEqual(res_cancel["results"][job_id]["outcome"], "applied")

            # Wait for batch to settle after cancellation completes
            settle_event.wait(timeout=5.0)

            # Check snapshot: job must be in 'canceled' status now
            snap_check = api_get_batch(batch_id)
            self.assertEqual(snap_check["jobs"][0]["status"], "canceled")

            # Test Retry outcome (applied because job is officially settled as 'canceled')
            res_retry = api_batch_action(batch_id, BatchActionRequest(action="retry", job_ids=[job_id]))
            self.assertTrue(res_retry["success"])
            self.assertEqual(res_retry["results"][job_id]["outcome"], "applied")

            # Test Save skipped outcome (job is reset to waiting and is not done)
            res_save = api_batch_action(batch_id, BatchActionRequest(action="save", job_ids=[job_id]))
            self.assertTrue(res_save["success"])
            self.assertEqual(res_save["results"][job_id]["outcome"], "skipped")

            # Mock job completion to test successful save
            with subtitle_batch_service.lock:
                batch = subtitle_batch_service.batches[batch_id]
                job = batch["jobs"][0]
                job["status"] = "done"
                job["srt_text"] = "1\n00:00:01,000 --> 00:00:04,000\nSub text"

            res_save_ok = api_batch_action(batch_id, BatchActionRequest(action="save", job_ids=[job_id]))
            self.assertTrue(res_save_ok["success"])
            self.assertEqual(res_save_ok["results"][job_id]["outcome"], "applied")
            
            expected_srt_path = os.path.join(tmpdir, "vid.srt")
            self.assertEqual(res_save_ok["results"][job_id]["saved_path"], os.path.abspath(expected_srt_path))
            self.assertTrue(os.path.exists(expected_srt_path))

            # Verify saved_path in snapshot was updated
            snap_updated = api_get_batch(batch_id)
            self.assertEqual(snap_updated["jobs"][0]["saved_path"], os.path.abspath(expected_srt_path))

    def test_update_job_srt(self):
        from app import update_job_srt, UpdateJobSrtRequest
        
        req = UpdateJobSrtRequest(srt_text="text", segments=[])
        with self.assertRaises(HTTPException) as ctx:
            update_job_srt("non_existent_batch", "job1", req)
        self.assertEqual(ctx.exception.status_code, 404)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            v = os.path.join(tmpdir, "vid.mp4")
            with open(v, "w") as f:
                f.write("mock")
                
            create_req = CreateBatchRequest(video_paths=[v], provider="whisper")
            create_res = api_create_batch(create_req)
            batch_id = create_res["batch_id"]
            job_id = create_res["snapshot"]["jobs"][0]["job_id"]
            
            # Update on non-completed (waiting) job with valid request -> HTTP 400
            req_init = UpdateJobSrtRequest(srt_text="valid srt", segments=[{"index": 1, "start_ms": 0, "end_ms": 1000, "text": "OK"}])
            with self.assertRaises(HTTPException) as ctx:
                update_job_srt(batch_id, job_id, req_init)
            self.assertEqual(ctx.exception.status_code, 400)
            
            with subtitle_batch_service.lock:
                batch = subtitle_batch_service.batches[batch_id]
                job = batch["jobs"][0]
                job["status"] = "done"

            # 3. Test input validation errors
            req_empty = UpdateJobSrtRequest(srt_text="", segments=[])
            with self.assertRaises(HTTPException) as ctx:
                update_job_srt(batch_id, job_id, req_empty)
            self.assertEqual(ctx.exception.status_code, 400)

            from pydantic import ValidationError
            with self.assertRaises(ValidationError):
                UpdateJobSrtRequest(srt_text="text", segments="not-a-list")

            req_missing_keys = UpdateJobSrtRequest(srt_text="text", segments=[{"index": 1}])
            with self.assertRaises(HTTPException) as ctx:
                update_job_srt(batch_id, job_id, req_missing_keys)
            self.assertEqual(ctx.exception.status_code, 400)
                
            test_srt = "1\n00:00:01,000 --> 00:00:03,000\nHello"
            test_segs = [{"index": 1, "start_ms": 1000, "end_ms": 3000, "text": "Hello"}]
            req_valid = UpdateJobSrtRequest(srt_text=test_srt, segments=test_segs)
            
            res = update_job_srt(batch_id, job_id, req_valid)
            self.assertEqual(res["status"], "success")
            
            expected_srt_path = os.path.join(tmpdir, "vid.srt")
            self.assertEqual(res["saved_path"], os.path.abspath(expected_srt_path))
            self.assertTrue(os.path.exists(expected_srt_path))
            
            with open(expected_srt_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), test_srt)
                
            updated_snap = api_get_batch(batch_id)
            self.assertEqual(updated_snap["jobs"][0]["saved_path"], os.path.abspath(expected_srt_path))
            self.assertEqual(updated_snap["jobs"][0]["srt_text"], test_srt)
            self.assertEqual(updated_snap["jobs"][0]["segments"][0]["text"], "Hello")


if __name__ == "__main__":
    unittest.main()
