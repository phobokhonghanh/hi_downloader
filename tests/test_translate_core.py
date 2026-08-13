import os
import unittest
import threading
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.schemas import ChunkConfig, TranslationConfig
from modules.translate.formatting import extract_formatting_markers, validate_formatting_markers
from modules.translate.providers.mock import MockTranslateProvider
from modules.translate.analysis import analyze_translation_context
from modules.translate.service import TranslationService


class TestTranslateCore(unittest.TestCase):

    def test_formatting_marker_extraction(self):
        """Test extraction of HTML-like tags and ASS override blocks."""
        text = r"<b>Hello</b> {\an8} This is {\pos(10,20)} style."
        markers = extract_formatting_markers(text)
        self.assertEqual(markers, ["<b>", "</b>", r"{\an8}", r"{\pos(10,20)}"])

    def test_formatting_marker_preservation_valid(self):
        """Test tag matching returns True when tags are preserved sequentially."""
        orig = r"<i>Hello</i> {\pos(1,2)}"
        trans = r"[vi] <i>Xin chào</i> {\pos(1,2)}"
        self.assertTrue(validate_formatting_markers(orig, trans))

    def test_formatting_marker_preservation_invalid(self):
        """Test tag matching returns False when tags are missing, extra, or reordered."""
        # 1. Missing tag
        orig = "<b>Hello</b>"
        trans = "[vi] Hello"
        self.assertFalse(validate_formatting_markers(orig, trans))

        # 2. Reordered tags
        orig = "<b><i>Hello</i></b>"
        trans = "[vi] <i><b>Xin chào</b></i>"
        self.assertFalse(validate_formatting_markers(orig, trans))

        # 3. Mismatched tag content
        orig = "<font color='red'>Red</font>"
        trans = "[vi] <font color='blue'>Đỏ</font>"
        self.assertFalse(validate_formatting_markers(orig, trans))

    def test_translation_service_happy_path(self):
        """Test complete translation run with mock provider, chunk splits, and glossary replacements."""
        segments = []
        curr_time = 0
        for i in range(1, 11):
            if i == 5:
                curr_time += 4000  # Gap of 4000ms (Normal gap) to trigger split
            else:
                curr_time += 500   # Gap of 500ms (No gap)
            segments.append(
                SubtitleSegment(index=i, start_ms=curr_time, end_ms=curr_time + 1000, text=f"Hello segment {i}")
            )
            curr_time += 1000

        provider = MockTranslateProvider()
        service = TranslationService(provider)

        config = TranslationConfig(
            target_language="vi",
            model="balanced",
            glossary={"Hello": "Xin chào"},
            chunk_config=ChunkConfig(target_segments=4, hard_max_segments=8, boundary_search_window=2)
        )

        result = service.translate(segments, config)
        self.assertTrue(result.success, f"Dịch thất bại: {result.error}")
        self.assertEqual(len(result.translated_segments), 10)

        # Check glossary replacement and target language prepend behavior
        self.assertEqual(result.translated_segments[0].text, "[vi] Xin chào segment 1")
        self.assertEqual(result.translated_segments[4].text, "[vi] Xin chào segment 5")
        
        # Verify index and timestamps are strictly identical
        for orig, trans in zip(segments, result.translated_segments):
            self.assertEqual(trans.index, orig.index)
            self.assertEqual(trans.start_ms, orig.start_ms)
            self.assertEqual(trans.end_ms, orig.end_ms)

    def test_translation_service_context_analysis(self):
        """Test that deterministic sampling works during analysis initialization."""
        segments = [
            SubtitleSegment(index=i, start_ms=i*1000, end_ms=i*1000+500, text=f"L{i}")
            for i in range(1, 40)
        ]
        provider = MockTranslateProvider()
        config = TranslationConfig(target_language="vi", model="balanced")
        
        summary = analyze_translation_context(segments, config, provider, threading.Event())
        self.assertIn("sampled=15", summary.summary)
        self.assertIn("target_language=vi", summary.summary)

    def test_malformed_provider_count_mismatch(self):
        """Test validation fails if provider returns incorrect segment count."""
        class MismatchedCountProvider(MockTranslateProvider):
            def translate_chunk(self, segments, config, context, cancel_event):
                # Return only one translated segment instead of full list
                return [SubtitleSegment(index=segments[0].index, start_ms=segments[0].start_ms, end_ms=segments[0].end_ms, text="Mismatched count")]

        # Set gap to 500ms so they aggregate into a single chunk
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1"),
            SubtitleSegment(index=2, start_ms=1500, end_ms=2500, text="S2"),
        ]
        service = TranslationService(MismatchedCountProvider())
        config = TranslationConfig(target_language="vi", model="balanced", chunk_config=ChunkConfig(target_segments=5))
        
        result = service.translate(segments, config)
        self.assertFalse(result.success)
        self.assertIn("Sai lệch kết quả dịch", result.error)

    def test_malformed_provider_time_modification(self):
        """Test validation fails if provider changes segment timestamps."""
        class ModifiedTimesProvider(MockTranslateProvider):
            def translate_chunk(self, segments, config, context, cancel_event):
                # Change start_ms
                return [SubtitleSegment(index=s.index, start_ms=s.start_ms + 10, end_ms=s.end_ms, text="Modified time") for s in segments]

        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1"),
        ]
        service = TranslationService(ModifiedTimesProvider())
        config = TranslationConfig(target_language="vi", model="balanced")
        
        result = service.translate(segments, config)
        self.assertFalse(result.success)
        self.assertIn("Timestamps bị thay đổi", result.error)

    def test_formatting_marker_preservation_violation(self):
        """Test validation fails if translation loses tags."""
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="<b>S1</b>"),
        ]
        provider = MockTranslateProvider(behavior_prefix="")
        class BadTagsProvider(MockTranslateProvider):
            def translate_chunk(self, segments, config, context, cancel_event):
                # Drop tags
                return [SubtitleSegment(index=s.index, start_ms=s.start_ms, end_ms=s.end_ms, text="No tag here") for s in segments]

        service = TranslationService(BadTagsProvider())
        config = TranslationConfig(target_language="vi", model="balanced")
        
        result = service.translate(segments, config)
        self.assertFalse(result.success)
        self.assertIn("Thẻ HTML/ASS không khớp", result.error)

    def test_progress_callback(self):
        """Test progress reports are correctly dispatched in order."""
        segments = [
            SubtitleSegment(index=i, start_ms=i*2000, end_ms=i*2000+1000, text="S")
            for i in range(1, 9)
        ]
        provider = MockTranslateProvider()
        service = TranslationService(provider)
        config = TranslationConfig(
            target_language="vi",
            model="balanced",
            chunk_config=ChunkConfig(target_segments=2)
        )

        progress_reports = []
        def progress_cb(pct, status):
            progress_reports.append((pct, status))

        result = service.translate(segments, config, progress_callback=progress_cb)
        self.assertTrue(result.success)
        
        # Reports should include startup, context extraction, chunk iterations, and final success
        self.assertTrue(len(progress_reports) >= 4)
        self.assertEqual(progress_reports[0][0], 0.0)
        self.assertEqual(progress_reports[-1][0], 100.0)
        self.assertEqual(progress_reports[-1][1], "Hoàn tất dịch phụ đề!")

    def test_cooperative_cancellation(self):
        """Test cancellation triggers cooperative abort during run."""
        segments = [
            SubtitleSegment(index=i, start_ms=i*2000, end_ms=i*2000+1000, text="S")
            for i in range(1, 9)
        ]
        cancel_event = threading.Event()
        
        class SlowProvider(MockTranslateProvider):
            def translate_chunk(self, segments, config, context, cancel_event):
                # Cancel here
                cancel_event.set()
                return super().translate_chunk(segments, config, context, cancel_event)

        service = TranslationService(SlowProvider())
        config = TranslationConfig(target_language="vi", model="balanced", chunk_config=ChunkConfig(target_segments=2))

        result = service.translate(segments, config, cancel_event=cancel_event)
        self.assertFalse(result.success)
        self.assertIn("hủy", result.error.lower())

    def test_provider_error_propagation(self):
        """Test exceptions raised inside provider are captured and reported inside result."""
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Normal text"),
            SubtitleSegment(index=2, start_ms=2000, end_ms=3000, text="This contains __ERROR__ trigger"),
        ]
        
        provider = MockTranslateProvider()
        service = TranslationService(provider)
        config = TranslationConfig(target_language="vi", model="balanced")

        result = service.translate(segments, config)
        self.assertFalse(result.success)
        self.assertIn("Mock translation failed", result.error)

    def test_blank_target_language_fails_early(self):
        """Test that translation fails early if target_language is blank without querying provider."""
        class AnalysisCallTracker(MockTranslateProvider):
            def __init__(self):
                super().__init__()
                self.analyzed = False
            def analyze_context(self, sampled_segments, config, cancel_event):
                self.analyzed = True
                return super().analyze_context(sampled_segments, config, cancel_event)

        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Hello"),
        ]
        provider = AnalysisCallTracker()
        service = TranslationService(provider)
        config = TranslationConfig(target_language="   ")

        result = service.translate(segments, config)
        self.assertFalse(result.success)
        self.assertIn("không được để trống", result.error)
        self.assertFalse(provider.analyzed, "Phân tích ngữ cảnh đáng lẽ không được phép chạy.")

    def test_no_obsolete_model_defaults(self):
        """Test that TranslationConfig has no obsolete default values for model or provider."""
        import dataclasses
        fields = dataclasses.fields(TranslationConfig)
        provider_field = next(f for f in fields if f.name == 'provider')
        model_field = next(f for f in fields if f.name == 'model')
        
        self.assertIsNone(provider_field.default)
        self.assertIsNone(model_field.default)

    def test_cache_integration_all_cache_resume(self):
        """Test that running translation with a populated cache retrieves all chunks from cache directly."""
        import tempfile
        import shutil
        from modules.translate.cache import TranslationCache

        test_dir = tempfile.mkdtemp()
        try:
            cache = TranslationCache(test_dir)
            segments = [
                SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1"),
                SubtitleSegment(index=2, start_ms=4000, end_ms=5000, text="S2"),  # Force gap boundary split to make 2 chunks
            ]
            config = TranslationConfig(target_language="vi", model="balanced")
            
            provider = MockTranslateProvider()
            service = TranslationService(provider)

            # First run: translates both chunks via provider
            res1 = service.translate(segments, config, cache=cache)
            self.assertTrue(res1.success)
            self.assertEqual(res1.metrics["restored_chunks"], 0)
            self.assertEqual(res1.metrics["translated_chunks"], 2)

            # Second run: resolves both chunks from cache
            # Create a provider tracker to ensure analyze_context is not called if we mock it,
            # but mock provider translate_chunk must definitely not run
            class CallTrackerProvider(MockTranslateProvider):
                def __init__(self):
                    super().__init__()
                    self.chunk_calls = 0
                def translate_chunk(self, segs, cfg, ctx, ev):
                    self.chunk_calls += 1
                    return super().translate_chunk(segs, cfg, ctx, ev)

            tracker = CallTrackerProvider()
            service2 = TranslationService(tracker)
            res2 = service2.translate(segments, config, cache=cache)
            self.assertTrue(res2.success)
            self.assertEqual(res2.metrics["restored_chunks"], 2)
            self.assertEqual(res2.metrics["translated_chunks"], 0)
            self.assertEqual(tracker.chunk_calls, 0)
        finally:
            shutil.rmtree(test_dir)

    def test_cache_integration_partial_resume(self):
        """Test that translation resolves hit chunks from cache and miss chunks from provider."""
        import tempfile
        import shutil
        from modules.translate.cache import TranslationCache, generate_chunk_cache_key

        test_dir = tempfile.mkdtemp()
        try:
            cache = TranslationCache(test_dir)
            segments = [
                SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1"),
                SubtitleSegment(index=2, start_ms=4000, end_ms=5000, text="S2"),
            ]
            config = TranslationConfig(target_language="vi", model="balanced")
            
            # Manually pre-populate cache for the first chunk only
            # The context global summary defaults to the provider analysis text, let's pre-extract context or precompute
            pre_summary = "Bối cảnh phim"
            
            # Build key for chunk 1 (index 1)
            key_chunk1 = generate_chunk_cache_key(
                segments=[segments[0]],
                target_language="vi",
                resolved_model="gemini-3.5-flash",
                chunk_ordinal=1,
                global_context=pre_summary,
                prompt_version="v1"
            )
            cache.put(key_chunk1, [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="[vi] S1")])

            provider = MockTranslateProvider()
            service = TranslationService(provider)
            
            # Execute with precomputed global summary so context hash matches exactly
            res = service.translate(segments, config, cache=cache, precomputed_global_summary=pre_summary)
            self.assertTrue(res.success)
            self.assertEqual(res.metrics["restored_chunks"], 1)
            self.assertEqual(res.metrics["translated_chunks"], 1)
        finally:
            shutil.rmtree(test_dir)

    def test_cache_integration_invalid_fallback_and_invalidation(self):
        """Test that corrupted or invalid cached chunks trigger invalidation and fallback to provider."""
        import tempfile
        import shutil
        from modules.translate.cache import TranslationCache, generate_chunk_cache_key

        test_dir = tempfile.mkdtemp()
        try:
            cache = TranslationCache(test_dir)
            segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
            config = TranslationConfig(target_language="vi", model="balanced")
            pre_summary = "Bối cảnh phim"
            
            key = generate_chunk_cache_key(
                segments=segments,
                target_language="vi",
                resolved_model="gemini-3.5-flash",
                chunk_ordinal=1,
                global_context=pre_summary,
                prompt_version="v1"
            )
            # Write invalid cache entry (wrong start_ms timestamp mismatch)
            cache.put(key, [SubtitleSegment(index=1, start_ms=9999, end_ms=1000, text="[vi] S1")])

            provider = MockTranslateProvider()
            service = TranslationService(provider)
            res = service.translate(segments, config, cache=cache, precomputed_global_summary=pre_summary)
            
            self.assertTrue(res.success)
            self.assertEqual(res.metrics["restored_chunks"], 0)
            self.assertEqual(res.metrics["translated_chunks"], 1)
            
            # Mismatched cache key must have been invalidated and updated with correct provider results
            updated_cache = cache.get(key)
            self.assertIsNotNone(updated_cache)
            self.assertEqual(updated_cache[0].start_ms, 0)
        finally:
            shutil.rmtree(test_dir)

    def test_cache_integration_precomputed_context_reuse(self):
        """Verify precomputed global context summary skips context analysis provider calls."""
        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="balanced")

        class AnalyzeTracker(MockTranslateProvider):
            def __init__(self):
                super().__init__()
                self.analyze_called = False
            def analyze_context(self, sampled_segments, config, cancel_event):
                self.analyze_called = True
                return "Should not run"

        provider = AnalyzeTracker()
        service = TranslationService(provider)
        res = service.translate(segments, config, precomputed_global_summary="Precomputed video summary")
        
        self.assertTrue(res.success)
        self.assertFalse(provider.analyze_called)

    def test_cache_integration_cancellation(self):
        """Verify translation loop checks cancel event and exits gracefully with canceled status."""
        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="balanced")
        
        provider = MockTranslateProvider()
        service = TranslationService(provider)
        
        cancel_event = threading.Event()
        cancel_event.set()  # Cancel early
        
        res = service.translate(segments, config, cancel_event=cancel_event)
        self.assertFalse(res.success)
        self.assertTrue(res.metrics["canceled"])

    def test_invalid_empty_model_resolution_failure(self):
        """Verify empty or invalid resolved_model_id/config.model raises ValueError."""
        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="")  # empty model
        
        provider = MockTranslateProvider()
        service = TranslationService(provider)
        
        # 1. Empty config.model
        res = service.translate(segments, config)
        self.assertFalse(res.success)
        self.assertIn("không được để trống", res.error)

        # 2. Invalid config.model profile
        config_invalid = TranslationConfig(target_language="vi", model="obsolete-model-nonexistent")
        res2 = service.translate(segments, config_invalid)
        self.assertFalse(res2.success)
        self.assertIn("không hợp lệ", res2.error)

        # 3. Empty resolved_model_id
        config_ok = TranslationConfig(target_language="vi", model="balanced")
        res3 = service.translate(segments, config_ok, resolved_model_id="   ")
        self.assertFalse(res3.success)
        self.assertIn("không được để trống", res3.error)

    def test_no_obsolete_model_string_in_service(self):
        """Assert modules/translate/service.py does not hardcode obsolete models like gemini-1.5-flash or gemini-3.5-flash."""
        service_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules", "translate", "service.py")
        with open(service_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("gemini-1.5-flash", content)
        self.assertNotIn("gemini-3.5-flash", content)

    def test_shared_validation_behavior(self):
        """Assert both cache retrieves and provider outputs are strictly validated by the private helper."""
        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        
        service = TranslationService(MockTranslateProvider())
        
        # Case 1: Mismatched length
        with self.assertRaises(ValueError):
            service._validate_translated_chunk(segments, [])
            
        # Case 2: Index mismatch
        with self.assertRaises(ValueError):
            service._validate_translated_chunk(segments, [SubtitleSegment(index=2, start_ms=0, end_ms=1000, text="Trans")])
            
        # Case 3: Timestamps mismatch
        with self.assertRaises(ValueError):
            service._validate_translated_chunk(segments, [SubtitleSegment(index=1, start_ms=0, end_ms=9999, text="Trans")])
            
        # Case 4: Blank text
        with self.assertRaises(ValueError):
            service._validate_translated_chunk(segments, [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="   ")])

        # Case 5: Marker mismatch
        with self.assertRaises(ValueError):
            service._validate_translated_chunk(
                [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="<b>S1</b>")],
                [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
            )

    def test_distinct_progress_messages(self):
        """Test progress callback receives distinct progress messages for cached versus live translations."""
        import tempfile
        import shutil
        from modules.translate.cache import TranslationCache

        test_dir = tempfile.mkdtemp()
        try:
            cache = TranslationCache(test_dir)
            segments = [
                SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1"),
                SubtitleSegment(index=2, start_ms=4000, end_ms=5000, text="S2"),
            ]
            config = TranslationConfig(target_language="vi", model="balanced")
            
            pre_summary = "Bối cảnh"

            from modules.translate.cache import generate_chunk_cache_key
            key_chunk1 = generate_chunk_cache_key(
                segments=[segments[0]],
                target_language="vi",
                resolved_model="gemini-3.5-flash",
                chunk_ordinal=1,
                global_context=pre_summary,
                prompt_version="v1"
            )
            cache.put(key_chunk1, [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="[vi] S1")])

            progress_logs = []
            def progress_cb(pct, msg):
                progress_logs.append(msg)

            provider = MockTranslateProvider()
            service = TranslationService(provider)
            
            res = service.translate(
                segments, config, cache=cache,
                precomputed_global_summary=pre_summary,
                progress_callback=progress_cb
            )
            self.assertTrue(res.success)
            
            self.assertTrue(any("Khôi phục từ cache" in msg for msg in progress_logs), f"Progress logs: {progress_logs}")
            self.assertTrue(any("Dịch trực tiếp" in msg for msg in progress_logs), f"Progress logs: {progress_logs}")
        finally:
            shutil.rmtree(test_dir)

    def test_structured_service_caching_and_precomputed(self):
        """Test TranslationService prompt integration, metadata retention, and cache resume."""
        import tempfile
        import shutil
        from modules.translate.cache import TranslationCache
        from modules.translate.schemas import TranslationAnalysis
        
        test_dir = tempfile.mkdtemp()
        try:
            cache = TranslationCache(test_dir)
            segments = [
                SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")
            ]
            config = TranslationConfig(target_language="vi", model="balanced")
            
            # Using structured precomputed analysis
            precomputed_analysis = TranslationAnalysis(
                source_language_code="ja",
                source_language_name="Tiếng Nhật",
                summary="Phim Anime bối cảnh lớp học",
                tone="thân mật",
                addressing_style="tớ - cậu",
                content_type="Anime học đường"
            )
            
            # First run: Live translation with mock provider
            provider = MockTranslateProvider()
            service = TranslationService(provider)
            
            res_live = service.translate(
                segments, config, cache=cache,
                precomputed_global_summary=precomputed_analysis
            )
            
            self.assertTrue(res_live.success)
            self.assertEqual(res_live.metrics["restored_chunks"], 0)
            self.assertEqual(res_live.metrics["translated_chunks"], 1)
            self.assertEqual(res_live.metrics["context_metadata"]["source_language_code"], "ja")
            self.assertEqual(res_live.metrics["context_metadata"]["content_type"], "Anime học đường")

            # Second run: All chunks restore from cache (cache resume)
            res_cache = service.translate(
                segments, config, cache=cache,
                precomputed_global_summary=precomputed_analysis
            )
            
            self.assertTrue(res_cache.success)
            self.assertEqual(res_cache.metrics["restored_chunks"], 1)
            self.assertEqual(res_cache.metrics["translated_chunks"], 0)
            self.assertEqual(res_cache.metrics["context_metadata"]["source_language_code"], "ja")
            self.assertEqual(res_cache.metrics["context_metadata"]["summary"], "Phim Anime bối cảnh lớp học")
        finally:
            shutil.rmtree(test_dir)
