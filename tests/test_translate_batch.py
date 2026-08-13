import os
import time
import shutil
import tempfile
import unittest
import threading
from typing import List

from modules.subtitle.schemas import SubtitleSegment
from modules.translate.providers.base import BaseTranslateProvider
from modules.translate.batch_service import TranslateBatchService, clean_target_language_slug


class FakeCredentialStore:

    def __init__(self, key: str = "SECRET_GEMINI_KEY"):
        self.key = key

    def resolve(self) -> str:
        return self.key


class FakeTranslateProvider(BaseTranslateProvider):

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.last_token_usage = {
            "input_tokens": 120,
            "output_tokens": 80,
            "total_tokens": 200
        }

    def analyze_context(self, segments, config, cancel_event):
        return "Fake global summary context"

    def translate_chunk(self, segments, config, context, cancel_event):
        prefix = f"[{config.target_language}] "
        return [
            SubtitleSegment(
                index=s.index,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=f"{prefix}{s.text}",
                source="fake_provider"
            )
            for s in segments
        ]


class BlockedTranslateProvider(FakeTranslateProvider):
    def __init__(self, block_event: threading.Event, api_key: str = ""):
        super().__init__(api_key)
        self.block_event = block_event

    def translate_chunk(self, segments, config, context, cancel_event):
        self.block_event.wait(timeout=2.0)
        return super().translate_chunk(segments, config, context, cancel_event)


class FakeClock:

    def __init__(self):
        self.now = 1700000000.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TestTranslateBatch(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

        self.clock = FakeClock()
        self.creds = FakeCredentialStore()
        self.cache = None

        self.service = TranslateBatchService(
            provider_factory=lambda key: FakeTranslateProvider(api_key=key),
            credential_store=self.creds,
            cache=self.cache,
            max_workers_limit=4,
            clock=self.clock
        )
        self.addCleanup(self.service.shutdown)

        # Create dummy valid SRT files
        self.srt1 = os.path.join(self.temp_dir, "movie1.srt")
        with open(self.srt1, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,100 --> 00:00:01,200\nHello World\n")

        self.srt2 = os.path.join(self.temp_dir, "movie2.srt")
        with open(self.srt2, "w", encoding="utf-8") as f:
            f.write("1\n00:00:02,100 --> 00:00:03,200\nAction Segment\n")

    def test_slug_generation_and_guards(self):
        """Test clean target language slug helper validations."""
        self.assertEqual(clean_target_language_slug("English (US)"), "English_US")
        self.assertEqual(clean_target_language_slug("vi-VN"), "vi-VN")
        self.assertEqual(clean_target_language_slug("  Tiếng Việt  "), "Tiếng_Việt")
        
        with self.assertRaises(ValueError):
            clean_target_language_slug("")
        with self.assertRaises(ValueError):
            clean_target_language_slug("  ")
        with self.assertRaises(ValueError):
            clean_target_language_slug("CON")
        with self.assertRaises(ValueError):
            clean_target_language_slug("com1")

    def test_create_batch_validations(self):
        """Test input validations, deduplication, format types, and overwrite guards."""
        # 1. Deduplication check
        batch_id = self.service.create_batch([self.srt1, self.srt1, self.srt2], "vi", "balanced")
        snapshot = self.service.get_batch(batch_id)
        self.assertEqual(len(snapshot["jobs"]), 2)

        # 2. Reject non-existing paths
        with self.assertRaises(ValueError):
            self.service.create_batch([os.path.join(self.temp_dir, "missing.srt")], "vi", "balanced")

        # 3. Overwrite protection check
        srt_conflict = os.path.join(self.temp_dir, "movie1_vi.srt")
        with open(srt_conflict, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,100 --> 00:00:01,200\nHello\n")

        with self.assertRaises(ValueError):
            self.service.create_batch([srt_conflict], "vi", "balanced")

    def test_batch_execution_happy_path(self):
        """Test batch run transitions state and exports sibling file using normalized status."""
        batch_id = self.service.create_batch([self.srt1], "vi", "balanced")
        
        snapshot = self.service.get_batch(batch_id)
        self.assertEqual(snapshot["status"], "waiting")

        self.service.start_batch(batch_id)
        self._wait_for_batch(batch_id)

        snapshot = self.service.get_batch(batch_id)
        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["jobs"][0]["status"], "done")

        out_path = os.path.join(self.temp_dir, "movie1_vi.srt")
        self.assertTrue(os.path.exists(out_path))
        with open(out_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("[vi] Hello World", content)

    def test_cancel_waiting_and_running_jobs(self):
        """Test that active batch cancellation shifts job states appropriately."""
        block_event = threading.Event()
        self.service.provider_factory = lambda key: BlockedTranslateProvider(block_event, api_key=key)

        batch_id = self.service.create_batch([self.srt1, self.srt2], "vi", "balanced", concurrency=1)
        self.service.start_batch(batch_id)

        time.sleep(0.05)
        self.service.cancel_all(batch_id)
        block_event.set()

        self._wait_for_batch(batch_id)

        snapshot = self.service.get_batch(batch_id)
        self.assertEqual(snapshot["status"], "canceled")

    def test_retry_failed_job(self):
        """Test resetting and retrying failed jobs in queue."""
        self.creds.key = None

        batch_id = self.service.create_batch([self.srt1], "vi", "balanced")
        self.service.start_batch(batch_id)
        self._wait_for_batch(batch_id)

        snapshot = self.service.get_batch(batch_id)
        self.assertEqual(snapshot["status"], "error")
        job_id = snapshot["jobs"][0]["job_id"]

        self.creds.key = "RESTORED_KEY"
        retried = self.service.retry_job(batch_id, job_id)
        self.assertTrue(retried)

        self._wait_for_batch(batch_id)
        snapshot = self.service.get_batch(batch_id)
        self.assertEqual(snapshot["status"], "done")

    def test_secret_absence_from_snapshots(self):
        """Verify API keys are strictly kept out of snapshots and job states."""
        batch_id = self.service.create_batch([self.srt1], "vi", "balanced")
        self.service.start_batch(batch_id)
        self._wait_for_batch(batch_id)

        snapshot = self.service.get_batch(batch_id)
        self.assertNotIn("SECRET_GEMINI_KEY", str(snapshot))

    def test_compare_save_edits_and_path_safety(self):
        """Test safe compares, edits validations, output accessors, and path security validations."""
        # Setup source srt with formatting tags
        srt_tags = os.path.join(self.temp_dir, "tags.srt")
        with open(srt_tags, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,100 --> 00:00:01,200\n<b>Hello</b> {\an8} World\n")

        batch_id = self.service.create_batch([srt_tags], "vi", "balanced")
        self.service.start_batch(batch_id)
        self._wait_for_batch(batch_id)

        snapshot = self.service.get_batch(batch_id)
        self.assertEqual(snapshot["status"], "done")
        job_id = snapshot["jobs"][0]["job_id"]

        # 1. Output Path Accessor
        out_path = self.service.get_job_output_path(batch_id, job_id)
        self.assertEqual(out_path, os.path.join(self.temp_dir, "tags_vi.srt"))

        # 2. Get Compare Alignment
        compare_data = self.service.get_job_compare(batch_id, job_id)
        self.assertEqual(len(compare_data["segments"]), 1)
        seg = compare_data["segments"][0]
        self.assertEqual(seg["index"], 1)
        self.assertEqual(seg["source_text"], "<b>Hello</b> {\an8} World")
        self.assertEqual(seg["translated_text"], "[vi] <b>Hello</b> {\an8} World")

        # 3. Save Valid Edits (preserving formatting HTML/ASS tags)
        valid_edits = {1: "<b>Xin chào</b> {\an8} Thế giới"}
        self.assertTrue(self.service.save_job_edits(batch_id, job_id, valid_edits))

        # Check compare data updated
        compare_data2 = self.service.get_job_compare(batch_id, job_id)
        self.assertEqual(compare_data2["segments"][0]["translated_text"], "<b>Xin chào</b> {\an8} Thế giới")

        # 4. Reject Malformed Edits: missing HTML tags
        invalid_edits_markers = {1: "Xin chào Thế giới"}
        with self.assertRaises(ValueError):
            self.service.save_job_edits(batch_id, job_id, invalid_edits_markers)

        # Reject blank text edits
        invalid_edits_blank = {1: "  "}
        with self.assertRaises(ValueError):
            self.service.save_job_edits(batch_id, job_id, invalid_edits_blank)

        # Reject missing index mappings
        invalid_edits_missing = {}
        with self.assertRaises(ValueError):
            self.service.save_job_edits(batch_id, job_id, invalid_edits_missing)

    def test_dispatcher_thread_cleanup(self):
        """Verify that completed batches leave no stale dispatcher thread references in service list."""
        batch_id = self.service.create_batch([self.srt1], "vi", "balanced")
        self.service.start_batch(batch_id)
        
        # Verify dispatcher thread was added
        self.assertEqual(len(self.service.dispatcher_threads), 1)

        self._wait_for_batch(batch_id)
        
        # Give a small slice of time for thread run logic wrapper to clean up thread reference
        time.sleep(0.05)

        # Verify dispatcher thread reference was deleted from the service list
        self.assertEqual(len(self.service.dispatcher_threads), 0)

    def test_no_live_workers_after_shutdown(self):
        """Verify that calling shutdown terminates dispatcher threads and active workers cleanly."""
        batch_id = self.service.create_batch([self.srt1, self.srt2], "vi", "balanced", concurrency=2)
        self.service.start_batch(batch_id)
        
        time.sleep(0.02)
        self.service.shutdown()

        for t in self.service.dispatcher_threads:
            self.assertFalse(t.is_alive())

    def test_batch_stats_tokens_and_compare(self):
        """Verify get_batch stats/duration/tokens totals and get_job_compare returns."""
        batch_id = self.service.create_batch([self.srt1, self.srt2], "vi", "balanced")
        self.service.start_batch(batch_id)
        self._wait_for_batch(batch_id)

        snapshot = self.service.get_batch(batch_id)
        self.assertIn("stats", snapshot)
        self.assertEqual(snapshot["stats"]["done"], 2)
        self.assertEqual(snapshot["stats"]["total"], 2)
        self.assertGreater(snapshot["total_tokens"], 0)
        self.assertEqual(snapshot["total_tokens"], snapshot["input_tokens"] + snapshot["output_tokens"])

        jobs = snapshot["jobs"]
        self.assertEqual(len(jobs), 2)
        job_id = jobs[0]["job_id"]

        compare = self.service.get_job_compare(batch_id, job_id)
        self.assertIn("source_path", compare)
        self.assertIn("saved_path", compare)
        self.assertEqual(compare["source_path"], self.srt1)
        self.assertTrue(compare["saved_path"].endswith("_vi.srt"))

    def test_translate_job_storage_snapshot_and_compare(self):
        """Test translate job metadata storage, snapshot rendering, and compare fallback."""
        batch_id = self.service.create_batch([self.srt1], "vi", "balanced")
        self.service.start_batch(batch_id)
        self._wait_for_batch(batch_id)
        
        snapshot = self.service.get_batch(batch_id)
        self.assertEqual(snapshot["status"], "done")
        job = snapshot["jobs"][0]
        
        # Verify context_metadata was populated inside job snapshot
        self.assertIn("context_metadata", job)
        self.assertEqual(job["context_metadata"]["source_language_code"], "und")
        self.assertEqual(job["context_metadata"]["source_language_name"], "Không xác định")
        
        # Verify get_job_compare returns elapsed_time, target_language and context_metadata
        compare = self.service.get_job_compare(batch_id, job["job_id"])
        self.assertIn("context_metadata", compare)
        self.assertEqual(compare["context_metadata"]["source_language_code"], "und")
        self.assertEqual(compare["target_language"], "vi")
        self.assertGreaterEqual(compare["elapsed_time"], 0.0)

    def _wait_for_batch(self, batch_id: str, timeout: float = 3.0) -> None:
        """Helper to wait for background execution to settle using bounded deadlines."""
        start = time.time()
        while time.time() - start < timeout:
            snapshot = self.service.get_batch(batch_id)
            if snapshot["status"] in ("done", "error", "canceled"):
                return
            time.sleep(0.02)
        self.fail("Timed out waiting for batch execution to settle.")
