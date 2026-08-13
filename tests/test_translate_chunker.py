import unittest
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.schemas import ChunkConfig
from modules.translate.validator import validate_segments
from modules.translate.chunker import chunk_segments, sample_context_segments


class TestTranslateChunker(unittest.TestCase):

    def test_validator_valid_sequence(self):
        """Test validator with a fully valid sequence of segments."""
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1500, text="Chào bạn!"),
            SubtitleSegment(index=2, start_ms=2000, end_ms=3500, text="Hôm nay thế nào?"),
            SubtitleSegment(index=3, start_ms=3500, end_ms=5000, text="<b>Đồng hành cùng Python.</b>"),
            SubtitleSegment(index=4, start_ms=6000, end_ms=7500, text="学习中文"),
        ]
        errors = validate_segments(segments)
        self.assertEqual(len(errors), 0, f"Mong đợi không có lỗi, nhận: {errors}")

    def test_validator_empty_list(self):
        """Test validator flags empty list errors."""
        errors = validate_segments([])
        self.assertTrue(any("không được để trống" in err for err in errors))

    def test_validator_invalid_indices(self):
        """Test validator flags non-contiguous index issues."""
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Tập 1"),
            # Missing index 2
            SubtitleSegment(index=3, start_ms=1200, end_ms=2000, text="Tập 2"),
        ]
        errors = validate_segments(segments)
        self.assertTrue(any("không liên tục" in err for err in errors))

    def test_validator_negative_times(self):
        """Test validator catches negative start or backward end times."""
        segments_neg = [
            SubtitleSegment(index=1, start_ms=-100, end_ms=1000, text="Lỗi âm"),
        ]
        errors_neg = validate_segments(segments_neg)
        self.assertTrue(any("start_ms must be >= 0" in err for err in errors_neg))

        segments_back = [
            SubtitleSegment(index=1, start_ms=1000, end_ms=500, text="Lỗi ngược"),
        ]
        errors_back = validate_segments(segments_back)
        self.assertTrue(any("must be strictly greater than start_ms" in err for err in errors_back))

    def test_validator_overlap_accepted(self):
        """Test validator allows overlapping segments with monotonic start times."""
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=2000, text="Segment 1"),
            SubtitleSegment(index=2, start_ms=1500, end_ms=3000, text="Segment 2 (overlap)"),
        ]
        errors = validate_segments(segments)
        self.assertEqual(len(errors), 0)

    def test_validator_empty_text(self):
        """Test validator catches empty or whitespace only text."""
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="   "),
        ]
        errors = validate_segments(segments)
        self.assertTrue(any("cannot be empty" in err for err in errors))

    def test_chunker_reconstruction_equality(self):
        """Test that chunks contain exactly the same segments in order without duplicates/loss."""
        segments = [
            SubtitleSegment(index=i, start_ms=i * 5000, end_ms=i * 5000 + 3000, text=f"Câu thoại số {i}")
            for i in range(1, 151)  # 150 segments (Short SRT context)
        ]
        
        config = ChunkConfig(target_segments=40, hard_max_segments=80)
        chunks = chunk_segments(segments, config)
        
        reconstructed = []
        for chunk in chunks:
            reconstructed.extend(chunk.segments)
            
        self.assertEqual(len(reconstructed), len(segments))
        for original, recon in zip(segments, reconstructed):
            self.assertEqual(original.index, recon.index)
            self.assertEqual(original.start_ms, recon.start_ms)
            self.assertEqual(original.text, recon.text)

    def test_chunker_scene_aware_gaps(self):
        """Test chunk splits at strong, normal, and fallback gaps within search window."""
        # Setup: 10 segments. Target: 5. Window: 3.
        # Window range for target 5: [5 - 3, 5 + 3] = [2, 8] split index.
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="1"),
            SubtitleSegment(index=2, start_ms=1500, end_ms=2500, text="2"),
            SubtitleSegment(index=3, start_ms=3000, end_ms=4000, text="3"),
            SubtitleSegment(index=4, start_ms=4500, end_ms=5500, text="4"),
            # Let's put a Strong Gap of 9000ms at split index 5 (between seg index 5 and 4)
            SubtitleSegment(index=5, start_ms=14500, end_ms=15500, text="5 (Strong gap)"), # gap=9000
            SubtitleSegment(index=6, start_ms=16000, end_ms=17000, text="6"),
            SubtitleSegment(index=7, start_ms=17500, end_ms=18500, text="7"),
            SubtitleSegment(index=8, start_ms=19000, end_ms=20000, text="8"),
            SubtitleSegment(index=9, start_ms=24000, end_ms=25000, text="9"),
            SubtitleSegment(index=10, start_ms=25500, end_ms=26500, text="10"),
        ]

        config = ChunkConfig(target_segments=5, boundary_search_window=3)
        chunks = chunk_segments(segments, config)
        
        # The first chunk should split at index 5 (which is the 5th element, index=5, split_index=4 because 0-indexed)
        self.assertEqual(len(chunks[0].segments), 4)
        self.assertEqual(chunks[0].metadata.boundary_reason, "strong_gap")
        self.assertEqual(chunks[0].metadata.preceding_gap_ms, None)
        self.assertEqual(chunks[1].metadata.preceding_gap_ms, 9000)

    def test_chunker_overlong_segment(self):
        """Test that single segment exceeding hard character limit is isolated and warned."""
        long_text = "Dòng chữ vô cùng dài... " * 300  # 7200 characters
        segments = [
            SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Dòng ngắn"),
            SubtitleSegment(index=2, start_ms=2000, end_ms=3000, text=long_text),
            SubtitleSegment(index=3, start_ms=4000, end_ms=5000, text="Dòng ngắn tiếp theo"),
        ]

        config = ChunkConfig(target_segments=2, hard_max_chars=4000)
        chunks = chunk_segments(segments, config)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[1].metadata.boundary_reason, "overlong_segment")
        self.assertEqual(len(chunks[1].segments), 1)
        self.assertTrue(len(chunks[1].metadata.warnings) > 0)

    def test_deterministic_sampling(self):
        """Test sampling yields expected size and contains correct distributed parts."""
        segments = [
            SubtitleSegment(index=i, start_ms=i*1000, end_ms=i*1000+500, text=f"Line {i}")
            for i in range(1, 101)  # 100 segments
        ]

        sampled = sample_context_segments(segments, max_sample_segs=10)
        self.assertEqual(len(sampled), 10)
        
        # Indexes must remain sorted and preserve their original values
        sampled_indexes = [s.index for s in sampled]
        self.assertEqual(sampled_indexes, sorted(sampled_indexes))

        # First 3 should be beginning (1, 2, 3)
        self.assertEqual(sampled_indexes[:3], [1, 2, 3])
        # Last 3 should be end (98, 99, 100)
        self.assertEqual(sampled_indexes[-3:], [98, 99, 100])

    def test_several_thousand_line_srt(self):
        """Test chunking limits on multi-hour, large subtitle file containing thousands of rows."""
        segments = [
            SubtitleSegment(index=i, start_ms=i * 2000, end_ms=i * 2000 + 1500, text=f"Tập thoại dài tiếng Việt {i}")
            for i in range(1, 3001)  # 3000 segments (Multi-hour SRT)
        ]

        config = ChunkConfig(target_segments=40, hard_max_segments=60, target_chars=1000, hard_max_chars=1500)
        chunks = chunk_segments(segments, config)

        self.assertTrue(len(chunks) > 1)
        for chunk in chunks:
            # No chunk exceeds hard max limits
            self.assertTrue(len(chunk.segments) <= config.hard_max_segments)
            self.assertTrue(chunk.metadata.char_count <= config.hard_max_chars)
            # Reconstruct sequence order check
            self.assertEqual(chunk.metadata.start_index, chunk.segments[0].index)
            self.assertEqual(chunk.metadata.end_index, chunk.segments[-1].index)
            self.assertEqual(chunk.metadata.start_ms, chunk.segments[0].start_ms)
            self.assertEqual(chunk.metadata.end_ms, chunk.segments[-1].end_ms)
            self.assertEqual(chunk.metadata.char_count, sum(len(s.text) for s in chunk.segments))

    def test_invalid_configs(self):
        """Test that validation fails for configs violating ranges and constraints."""
        # 1. target exceeds hard max segments
        c1 = ChunkConfig(target_segments=10, hard_max_segments=5)
        with self.assertRaises(ValueError):
            chunk_segments([SubtitleSegment(1, 0, 1000, "t")], c1)

        # 2. negative values
        c2 = ChunkConfig(target_segments=-1)
        with self.assertRaises(ValueError):
            chunk_segments([SubtitleSegment(1, 0, 1000, "t")], c2)

        # 3. target exceeds hard max chars
        c3 = ChunkConfig(target_chars=2000, hard_max_chars=1000)
        with self.assertRaises(ValueError):
            chunk_segments([SubtitleSegment(1, 0, 1000, "t")], c3)

        # 4. negative window
        c4 = ChunkConfig(boundary_search_window=-2)
        with self.assertRaises(ValueError):
            chunk_segments([SubtitleSegment(1, 0, 1000, "t")], c4)

    def test_target_chars_influence(self):
        """Test that target_chars successfully functions as a sizing signal and changes split index."""
        # 10 segments, each having a text of length 100 characters (total 1000 chars)
        segments = [
            SubtitleSegment(index=i, start_ms=i*2000, end_ms=i*2000+1000, text="A" * 100)
            for i in range(1, 11)
        ]
        # Introduce a Strong Gap (9000ms) at index 3 (split index 2, between 2 and 3)
        # Gap = segments[2].start_ms (6000) - segments[1].end_ms (5000) = 1000ms (Fallback)
        # Gap = segments[3].start_ms (8000) - segments[2].end_ms (7000) = 1000ms
        # Introduce gap of 9000ms between index 3 and 4:
        # segment 3 ends at 7000. segment 4 starts at 16000. Gap = 9000ms.
        segments[3] = SubtitleSegment(index=4, start_ms=16000, end_ms=17000, text="A" * 100)

        # Case A: target_segments = 8, target_chars = 1000. target_char_idx = 10. Target_idx = 8.
        # Search window for target_idx=8 with window=3: [5, 10].
        # split_idx 4 (gap=9000ms) is at index 4 (0-indexed index 3). This is OUTSIDE window [5, 10].
        # Therefore, Case A split index will not use the strong gap at 4, but fallback to end_of_file or split elsewhere.
        config_a = ChunkConfig(target_segments=8, target_chars=1000, boundary_search_window=3)
        chunks_a = chunk_segments(segments, config_a)
        
        # Case B: target_segments = 8, but target_chars = 300 (which is reached at segment 3, so target_char_idx = 3).
        # target_idx = min(8, 3) = 3.
        # Search window for target_idx=3 with window=3: [1, 6].
        # split_idx 4 (index 3) having gap=9000ms is INSIDE the window [1, 6].
        # So Case B splits exactly at split_idx 4 (strong_gap).
        config_b = ChunkConfig(target_segments=8, target_chars=300, boundary_search_window=3)
        chunks_b = chunk_segments(segments, config_b)
        
        self.assertEqual(chunks_b[0].metadata.boundary_reason, "strong_gap")
        self.assertEqual(len(chunks_b[0].segments), 3)  # contains segments 1, 2, 3
        self.assertNotEqual(len(chunks_a[0].segments), 3)
