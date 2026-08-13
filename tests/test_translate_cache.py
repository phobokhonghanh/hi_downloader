import os
import json
import time
import shutil
import tempfile
import unittest
import threading
import concurrent.futures
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.cache import TranslationCache, generate_chunk_cache_key


class TestTranslateCache(unittest.TestCase):

    def setUp(self):
        # Create dedicated isolated temp directory for test cache root
        self.test_cache_root = tempfile.mkdtemp()
        self.cache = TranslationCache(self.test_cache_root)

    def tearDown(self):
        # Clean up all created files
        if os.path.exists(self.test_cache_root):
            shutil.rmtree(self.test_cache_root)

    def test_cache_hit_and_miss(self):
        """Test getting and putting items inside cache generates clean hits and misses."""
        segments = [SubtitleSegment(1, 100, 200, "Hello")]
        key = generate_chunk_cache_key(segments, "vi", "balanced", 1)

        # 1. Miss on empty cache
        self.assertIsNone(self.cache.get(key))

        # 2. Put segments
        trans_segs = [SubtitleSegment(1, 100, 200, "[vi] Chào")]
        self.cache.put(key, trans_segs)

        # 3. Hit on configured key
        hits = self.cache.get(key)
        self.assertIsNotNone(hits)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].text, "[vi] Chào")
        self.assertEqual(hits[0].source, "cache")

    def test_config_and_content_invalidation(self):
        """Test that changes in parameters or segments generate distinct hashes causing invalidation."""
        segments_1 = [SubtitleSegment(1, 100, 200, "Hello")]
        segments_2 = [SubtitleSegment(1, 100, 200, "Hello World")]  # content changed

        key_1 = generate_chunk_cache_key(segments_1, "vi", "balanced", 1)
        key_2 = generate_chunk_cache_key(segments_2, "vi", "balanced", 1)
        key_3 = generate_chunk_cache_key(segments_1, "en", "balanced", 1)  # lang changed
        key_4 = generate_chunk_cache_key(segments_1, "vi", "quality", 1)   # model changed
        key_5 = generate_chunk_cache_key(segments_1, "vi", "balanced", 1, glossary={"A": "B"}) # glossary changed

        self.assertNotEqual(key_1, key_2)
        self.assertNotEqual(key_1, key_3)
        self.assertNotEqual(key_1, key_4)
        self.assertNotEqual(key_1, key_5)

    def test_no_secret_serialization(self):
        """Verify that cache storage never dumps sensitive API Key values to disk."""
        segments = [SubtitleSegment(1, 100, 200, "Hello")]
        key = generate_chunk_cache_key(segments, "vi", "balanced", 1)
        trans_segs = [SubtitleSegment(1, 100, 200, "[vi] Chào")]

        # Put with non-secret metadata
        self.cache.put(key, trans_segs, metadata={"some_config": "value", "api_key": "AIzaSy_Secret_Should_Not_Save"})

        cache_file = os.path.join(self.test_cache_root, f"{key}.json")
        with open(cache_file, "r", encoding="utf-8") as f:
            content = f.read()

        # The serialized file should contain translated details, but absolutely no API Key secrets
        self.assertIn("[vi] Chào", content)
        self.assertNotIn("AIzaSy_Secret_Should_Not_Save", content)

    def test_corruption_handling(self):
        """Test that corrupted, malformed, or structural mismatch files default to soft cache miss."""
        key = "a" * 64
        cache_file = os.path.join(self.test_cache_root, f"{key}.json")

        # 1. Write corrupted raw text
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write("This is a corrupted non-json file.")

        self.assertIsNone(self.cache.get(key))

        # 2. Write invalid structural json (missing key / segments fields)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"invalid_field": "test"}))

        self.assertIsNone(self.cache.get(key))

    def test_atomic_replacement(self):
        """Test that updates are written atomically without corrupting state."""
        segments = [SubtitleSegment(1, 100, 200, "Hello")]
        key = generate_chunk_cache_key(segments, "vi", "balanced", 1)
        trans_segs = [SubtitleSegment(1, 100, 200, "[vi] Chào")]

        self.cache.put(key, trans_segs)
        cache_file = os.path.join(self.test_cache_root, f"{key}.json")
        self.assertTrue(os.path.exists(cache_file))

        # Verify no stale temporary files are left behind
        temp_files = [f for f in os.listdir(self.test_cache_root) if f.startswith("tmp_cache_")]
        self.assertEqual(len(temp_files), 0)

    def test_explicit_invalidation(self):
        """Test that invalidating removes the cache file."""
        segments = [SubtitleSegment(1, 100, 200, "Hello")]
        key = generate_chunk_cache_key(segments, "vi", "balanced", 1)
        trans_segs = [SubtitleSegment(1, 100, 200, "[vi] Chào")]

        self.cache.put(key, trans_segs)
        self.assertIsNotNone(self.cache.get(key))

        self.cache.invalidate(key)
        self.assertIsNone(self.cache.get(key))

    def test_age_cleanup(self):
        """Test that cleaning up files removes older cache keys."""
        # 1. Create a fresh key
        seg_fresh = [SubtitleSegment(1, 0, 100, "Fresh")]
        key_fresh = generate_chunk_cache_key(seg_fresh, "vi", "balanced", 1)
        self.cache.put(key_fresh, seg_fresh)

        # 2. Create an old key
        seg_old = [SubtitleSegment(2, 200, 300, "Old")]
        key_old = generate_chunk_cache_key(seg_old, "vi", "balanced", 2)
        self.cache.put(key_old, seg_old)

        old_file = os.path.join(self.test_cache_root, f"{key_old}.json")
        
        # Modify old file timestamp back 1 hour
        past_time = time.time() - 3600
        os.utime(old_file, (past_time, past_time))

        # Clean up files older than 60 seconds (1 minute)
        self.cache.cleanup(max_age_seconds=60)

        # Fresh key should stay, old key should be cleared
        self.assertIsNotNone(self.cache.get(key_fresh))
        self.assertIsNone(self.cache.get(key_old))

    def test_concurrent_access_safety(self):
        """Test concurrent multithreaded puts and gets complete without exceptions."""
        store = TranslationCache(self.test_cache_root)

        def worker(i):
            import hashlib
            key = hashlib.sha256(f"thread_{i}".encode()).hexdigest()
            seg = [SubtitleSegment(i, 0, 100, f"Thread {i}")]
            # Concurrently write and read
            store.put(key, seg)
            store.get(key)
            store.invalidate(key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, idx) for idx in range(1, 101)]
            for f in concurrent.futures.as_completed(futures):
                f.result()  # Assert no threads fail due to lock deadlocks

    def test_key_safety_and_path_traversal_rejection(self):
        """Test that Cache APIs reject non-SHA-256 keys with ValueError to prevent path traversal."""
        bad_keys = [
            "shortkey",
            "a" * 63,
            "a" * 65,
            "../" + "a" * 61,
            "A" * 64,  # uppercase
            "g" * 64,  # non-hex
        ]
        for key in bad_keys:
            with self.assertRaises(ValueError):
                self.cache.get(key)
            with self.assertRaises(ValueError):
                self.cache.put(key, [])
            with self.assertRaises(ValueError):
                self.cache.invalidate(key)
