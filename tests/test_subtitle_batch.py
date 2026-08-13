import unittest
import threading
import time
import copy
from typing import Dict, Any, List
from modules.subtitle.batch_service import SubtitleBatchService


class TestSubtitleBatch(unittest.TestCase):
    def setUp(self):
        self.service = None
        self.settle_events = {}
        self.settle_lock = threading.Lock()

    def tearDown(self):
        if self.service:
            self.service.shutdown()

    def _setup_service(self, runner_fn):
        self.service = SubtitleBatchService(provider_runner=runner_fn)
        
        # Override _settle_batch to notify tests deterministically when a batch settles
        original_settle = self.service._settle_batch
        
        def mock_settle(batch_id: str):
            original_settle(batch_id)
            snap = self.service.get_batch_snapshot(batch_id)
            if snap and snap["status"] in ("done", "error"):
                with self.settle_lock:
                    event = self.settle_events.get(batch_id)
                    if event:
                        event.set()

        self.service._settle_batch = mock_settle

    def _register_settle_event(self, batch_id: str) -> threading.Event:
        event = threading.Event()
        with self.settle_lock:
            self.settle_events[batch_id] = event
        return event

    def test_concurrency_validation(self):
        self._setup_service(None)
        
        # Invalid concurrency bounds
        with self.assertRaises(ValueError):
            self.service.create_batch(["v1.mp4"], {}, concurrency=0)
        with self.assertRaises(ValueError):
            self.service.create_batch(["v1.mp4"], {}, concurrency=11)
            
        # Valid concurrency bounds
        b1 = self.service.create_batch(["v1.mp4"], {}, concurrency=1)
        b2 = self.service.create_batch(["v1.mp4"], {}, concurrency=2)
        b3 = self.service.create_batch(["v1.mp4"], {}, concurrency=10)
        
        self.assertIsNotNone(b1)
        self.assertIsNotNone(b2)
        self.assertIsNotNone(b3)

    def test_concurrency_throttling_deterministic(self):
        # 3 jobs, concurrency 2.
        # We block jobs inside the fake runner to verify concurrency bounds
        job_entered_events = [threading.Event() for _ in range(3)]
        job_allow_proceed = [threading.Event() for _ in range(3)]
        
        entered_count = 0
        entered_lock = threading.Lock()
        max_active_workers = 0
        active_workers = 0
        active_lock = threading.Lock()

        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            nonlocal entered_count, max_active_workers, active_workers
            idx = int(video_path.split("_")[-1])
            
            with entered_lock:
                entered_count += 1
            
            with active_lock:
                active_workers += 1
                if active_workers > max_active_workers:
                    max_active_workers = active_workers
            
            job_entered_events[idx].set()
            job_allow_proceed[idx].wait()
            
            with active_lock:
                active_workers -= 1
                
            return {"srt_text": f"SRT_{idx}", "segments": []}

        self._setup_service(fake_runner)
        batch_id = self.service.create_batch(
            files=["video_0", "video_1", "video_2"],
            provider_params={},
            concurrency=2
        )
        settle_event = self._register_settle_event(batch_id)

        self.service.start_batch(batch_id)

        # Wait for the first two jobs to enter the runner
        job_entered_events[0].wait()
        job_entered_events[1].wait()

        # At this stage, max active workers must be 2, and the 3rd job (video_2) must not run
        self.assertEqual(max_active_workers, 2)
        self.assertFalse(job_entered_events[2].is_set())

        # Release first job (video_0), allowing the third job (video_2) to acquire slot
        job_allow_proceed[0].set()
        job_entered_events[2].wait()

        # Release remaining jobs to let batch settle
        job_allow_proceed[1].set()
        job_allow_proceed[2].set()

        settle_event.wait()

        # Assert all completed cleanly
        snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap["status"], "done")
        self.assertEqual(max_active_workers, 2)

    def test_concurrency_ten_runners_simultaneous(self):
        # 10 jobs, concurrency 10.
        # We use a Barrier of size 11 (10 runners + 1 main test thread) to align threads simultaneously
        barrier = threading.Barrier(11)
        entered_count = 0
        entered_lock = threading.Lock()

        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            nonlocal entered_count
            with entered_lock:
                entered_count += 1
            barrier.wait()
            return {"srt_text": "text", "segments": []}

        self._setup_service(fake_runner)
        files = [f"video_{i}" for i in range(10)]
        batch_id = self.service.create_batch(files, {}, concurrency=10)
        settle_event = self._register_settle_event(batch_id)

        self.service.start_batch(batch_id)

        # Wait for all 10 threads to enter the barrier simultaneously
        barrier.wait(timeout=5.0)
        settle_event.wait()

        self.assertEqual(entered_count, 10)

    def test_two_batches_parallel_no_deadlock(self):
        # Batch 1 (concurrency 5) and Batch 2 (concurrency 5) running concurrently
        # Verify no deadlock happens due to dispatcher workers exhaustion
        barrier = threading.Barrier(11) # 5 + 5 + 1 main test thread = 11

        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            barrier.wait()
            return {}

        self._setup_service(fake_runner)
        
        b1_files = [f"b1_vid_{i}" for i in range(5)]
        b2_files = [f"b2_vid_{i}" for i in range(5)]

        batch_1 = self.service.create_batch(b1_files, {}, concurrency=5)
        batch_2 = self.service.create_batch(b2_files, {}, concurrency=5)

        s1 = self._register_settle_event(batch_1)
        s2 = self._register_settle_event(batch_2)

        self.service.start_batch(batch_1)
        self.service.start_batch(batch_2)

        barrier.wait(timeout=5.0)

        s1.wait()
        s2.wait()

        snap1 = self.service.get_batch_snapshot(batch_1)
        snap2 = self.service.get_batch_snapshot(batch_2)
        self.assertEqual(snap1["status"], "done")
        self.assertEqual(snap2["status"], "done")

    def test_progress_clamping_and_monotonicity(self):
        stored_callbacks = []
        callback_event = threading.Event()
        proceed_event = threading.Event()

        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            stored_callbacks.append(progress_callback)
            callback_event.set()
            proceed_event.wait()
            return {"srt_text": "text", "segments": []}

        self._setup_service(fake_runner)
        batch_id = self.service.create_batch(["video_0"], {}, concurrency=1)
        settle_event = self._register_settle_event(batch_id)
        self.service.start_batch(batch_id)

        callback_event.wait()
        cb = stored_callbacks[0]

        # 1. Clamping check: pct=150.0 clamped to 100.0, pct=-10 clamped to 0.0
        cb(-5.0, "low")
        snap = self.service.get_batch_snapshot(batch_id)
        # initial progress at running starts at 5.0, clamping to 0.0 shouldn't apply as it violates monotonicity
        self.assertEqual(snap["jobs"][0]["progress"], 5.0)

        cb(15.0, "step1")
        snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap["jobs"][0]["progress"], 15.0)
        self.assertEqual(snap["jobs"][0]["phase"], "step1")

        # 2. Monotonicity check: decreasing progress is ignored
        cb(10.0, "step_lower")
        snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap["jobs"][0]["progress"], 15.0)
        self.assertEqual(snap["jobs"][0]["phase"], "step1")

        cb(150.0, "step_clamp")
        snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap["jobs"][0]["progress"], 100.0)
        self.assertEqual(snap["jobs"][0]["phase"], "step_clamp")

        proceed_event.set()
        settle_event.wait()

    def test_job_failure_isolation(self):
        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            if "fail" in video_path:
                raise RuntimeError("Mock failure")
            return {"srt_text": "success_srt", "segments": []}

        self._setup_service(fake_runner)
        batch_id = self.service.create_batch(["video_fail", "video_ok"], {}, concurrency=2)
        settle_event = self._register_settle_event(batch_id)
        self.service.start_batch(batch_id)

        settle_event.wait()

        snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap["status"], "error") # Batch is error if any job fails
        
        job_fail = next(j for j in snap["jobs"] if "fail" in j["video_path"])
        job_ok = next(j for j in snap["jobs"] if "ok" in j["video_path"])

        self.assertEqual(job_fail["status"], "error")
        self.assertEqual(job_fail["error"], "Mock failure")
        self.assertEqual(job_ok["status"], "done")
        self.assertEqual(job_ok["srt_text"], "success_srt")

    def test_subtitle_job_detail_metadata_exposure(self):
        """Test that subtitle batch snapshots dynamically expose provider and language details."""
        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            return {"srt_text": "1\n00:00:00,000 --> 00:00:01,000\nHello", "segments": []}
            
        self._setup_service(fake_runner)
        # Case 1: Custom language and normalized provider
        batch_id = self.service.create_batch(["video1.mp4"], {"language": "vi"})
        self.service.batches[batch_id]["provider"] = "whisper"
        snap = self.service.get_batch_snapshot(batch_id)
        job = snap["jobs"][0]
        self.assertEqual(job["provider"], "whisper")
        self.assertEqual(job["language"], "vi")

        # Case 2: Auto/None language fallback and invalid provider normalization
        batch_id2 = self.service.create_batch(["video2.mp4"], {"language": "auto"})
        self.service.batches[batch_id2]["provider"] = "invalid_prov"
        snap2 = self.service.get_batch_snapshot(batch_id2)
        job2 = snap2["jobs"][0]
        self.assertEqual(job2["provider"], "whisper")
        self.assertEqual(job2["language"], "auto")

    def test_cancel_action_and_eligibility(self):
        # We start running job_0 and keep it active while job_1 waits.
        job_0_entered = threading.Event()
        job_0_allow_proceed = threading.Event()

        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            if "job_0" in video_path:
                job_0_entered.set()
                # Wait until cancelled
                while not cancel_event.is_set():
                    cancel_event.wait(timeout=0.01)
                return {}
            return {}

        self._setup_service(fake_runner)
        batch_id = self.service.create_batch(["video_job_0", "video_job_1"], {}, concurrency=1)
        settle_event = self._register_settle_event(batch_id)
        self.service.start_batch(batch_id)

        job_0_entered.wait()

        # Snapshot checks before cancel
        snap = self.service.get_batch_snapshot(batch_id)
        job_0_id = snap["jobs"][0]["job_id"]
        job_1_id = snap["jobs"][1]["job_id"]

        # Cancel both jobs: job_0 (running) and job_1 (waiting)
        outcomes = self.service.cancel_batch_jobs(batch_id, [job_0_id, job_1_id])

        self.assertEqual(outcomes[job_0_id]["outcome"], "applied")
        self.assertEqual(outcomes[job_1_id]["outcome"], "applied")

        settle_event.wait()

        snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap["status"], "error")
        
        j0 = next(j for j in snap["jobs"] if j["job_id"] == job_0_id)
        j1 = next(j for j in snap["jobs"] if j["job_id"] == job_1_id)

        self.assertEqual(j0["status"], "canceled")
        self.assertEqual(j1["status"], "canceled")

        # Retry eligibility check on canceled/done jobs
        # Retry canceled jobs should be applied, but done/waiting are skipped
        outcomes_retry = self.service.retry_batch_jobs(batch_id, [job_0_id, job_1_id])
        self.assertEqual(outcomes_retry[job_0_id]["outcome"], "applied")
        self.assertEqual(outcomes_retry[job_1_id]["outcome"], "applied")

    def test_retry_eligibility_and_reset(self):
        runner_calls = []
        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            runner_calls.append(video_path)
            if "fail" in video_path and len(runner_calls) == 1:
                raise RuntimeError("Failed first pass")
            return {"srt_text": "retry_srt", "segments": []}

        self._setup_service(fake_runner)
        batch_id = self.service.create_batch(["video_fail"], {}, concurrency=1)
        settle_event = self._register_settle_event(batch_id)
        self.service.start_batch(batch_id)

        settle_event.wait()

        snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap["status"], "error")
        job_id = snap["jobs"][0]["job_id"]
        self.assertEqual(snap["jobs"][0]["status"], "error")

        # Retry the job
        settle_event.clear()
        outcomes = self.service.retry_batch_jobs(batch_id, [job_id])
        self.assertEqual(outcomes[job_id]["outcome"], "applied")

        settle_event.wait()

        snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap["status"], "done")
        self.assertEqual(snap["jobs"][0]["status"], "done")
        self.assertEqual(snap["jobs"][0]["srt_text"], "retry_srt")

    def test_aggregate_stats_canceled_grouped(self):
        self._setup_service(None)
        batch_id = self.service.create_batch(["v1.mp4", "v2.mp4"], {}, concurrency=2)
        
        # Manually force job state updates to verify stats calculation in snapshots
        batch = self.service.batches[batch_id]
        batch["jobs"][0]["status"] = "canceled"
        batch["jobs"][1]["status"] = "error"
        
        snap = self.service.get_batch_snapshot(batch_id)
        # canceled (v1) and error (v2) should both group into the "error" aggregate count
        self.assertEqual(snap["stats"]["error"], 2)

    def test_wall_clock_lifecycle_and_defensive_snapshots(self):
        def fake_runner(video_path: str, params: dict, progress_callback, cancel_event):
            return {"srt_text": "text", "segments": []}

        self._setup_service(fake_runner)
        batch_id = self.service.create_batch(["v1.mp4"], {}, concurrency=1)
        settle_event = self._register_settle_event(batch_id)
        
        self.service.start_batch(batch_id)
        settle_event.wait()

        snap = self.service.get_batch_snapshot(batch_id)
        self.assertIsNotNone(snap["start_time"])
        self.assertIsNotNone(snap["settle_time"])
        
        # Settle duration calculation check
        self.assertEqual(snap["total_duration"], snap["settle_time"] - snap["start_time"])

        # Defensive snapshot checks: changing snapshot dictionary values must not affect service state
        snap["status"] = "tampered"
        snap["jobs"][0]["status"] = "tampered"
        
        real_snap = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(real_snap["status"], "done")
        self.assertEqual(real_snap["jobs"][0]["status"], "done")

    def test_nested_defensive_copies(self):
        original_params = {"nested": {"key": "original_val"}}
        self._setup_service(None)
        
        batch_id = self.service.create_batch(["video.mp4"], original_params, concurrency=1)
        original_params["nested"]["key"] = "mutated_val"
        
        snap = self.service.get_batch_snapshot(batch_id)
        # Verify deep copy of provider params was preserved on creation
        self.assertEqual(snap["jobs"][0]["video_path"], "video.mp4")

        # Verify snapshot deep copy works correctly and is read-only
        snap["jobs"][0]["video_path"] = "hacked.mp4"
        snap2 = self.service.get_batch_snapshot(batch_id)
        self.assertEqual(snap2["jobs"][0]["video_path"], "video.mp4")

    def test_shutdown_lifecycle_and_rejections(self):
        self._setup_service(None)
        self.service.shutdown()
        
        # Verify service rejects new batch operations after shutdown
        with self.assertRaises(RuntimeError):
            self.service.create_batch(["v1.mp4"], {}, concurrency=1)
            
        with self.assertRaises(RuntimeError):
            self.service.start_batch("fake_batch")
            
        with self.assertRaises(RuntimeError):
            self.service.retry_batch_jobs("fake_batch", ["job_1"])

        # Verify shutdown is idempotent (no errors on second call)
        self.service.shutdown()

        # Verify cooperative cancel works during shutdown
        job_entered = threading.Event()
        job_proceed = threading.Event()
        
        def blocking_runner(video_path: str, params: dict, progress_callback, cancel_event):
            job_entered.set()
            while not cancel_event.is_set():
                cancel_event.wait(timeout=0.01)
            job_proceed.set()
            return {}
            
        self._setup_service(blocking_runner)
        batch_id = self.service.create_batch(["video.mp4"], {}, concurrency=1)
        self.service.start_batch(batch_id)
        
        job_entered.wait()
        self.service.shutdown()
        
        self.assertTrue(job_proceed.is_set())

    def test_detected_language_in_batch(self):
        def runner_with_lang(video_path: str, params: dict, progress_callback, cancel_event):
            return {
                "srt_text": "1\n00:00:01,000 --> 00:00:02,000\nHello",
                "segments": [{"index": 1, "start_ms": 1000, "end_ms": 2000, "text": "Hello"}],
                "metadata": {"raw_language": "vi", "model": "base"}
            }
            
        self._setup_service(runner_with_lang)
        event = self._register_settle_event("batch_lang_test")
        
        batch_id = self.service.create_batch(
            files=["video_1.mp4"],
            provider_params={"language": "auto"},
            concurrency=1
        )
        # Hack batch_id to match registered settle event
        self.service.batches[batch_id]["batch_id"] = "batch_lang_test"
        self.service.batches["batch_lang_test"] = self.service.batches.pop(batch_id)
        for j in self.service.batches["batch_lang_test"]["jobs"]:
            j["batch_id"] = "batch_lang_test"

        self.service.start_batch("batch_lang_test")
        event.wait(timeout=5)
        
        snap = self.service.get_batch_snapshot("batch_lang_test")
        self.assertIsNotNone(snap)
        job = snap["jobs"][0]
        self.assertEqual(job["detected_language"], "vi")
        self.assertEqual(job["language"], "vi")


if __name__ == "__main__":
    unittest.main()
