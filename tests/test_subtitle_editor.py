import unittest
from modules.subtitle.schemas import SubtitleSegment
from modules.subtitle.editor import SubtitleEditor


class TestSubtitleEditor(unittest.TestCase):
    def test_initial_reindexing(self):
        # Even if segments have custom index values, editor should reindex sequentially from 1
        s1 = SubtitleSegment(10, 0, 1000, "First")
        s2 = SubtitleSegment(20, 1100, 2000, "Second")
        editor = SubtitleEditor([s1, s2])
        segs = editor.list_segments()
        self.assertEqual(segs[0].index, 1)
        self.assertEqual(segs[1].index, 2)

    def test_safe_merge_adjacent_small_gap(self):
        s1 = SubtitleSegment(1, 0, 1000, "First")
        s2 = SubtitleSegment(2, 1200, 2000, "Second")  # Gap is 200ms (< 300ms)
        editor = SubtitleEditor([s1, s2])

        merged = editor.merge_segments(1, 2)
        self.assertEqual(merged.index, 1)
        self.assertEqual(merged.start_ms, 0)
        self.assertEqual(merged.end_ms, 2000)
        self.assertEqual(merged.text, "First Second")

        segs = editor.list_segments()
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].text, "First Second")

    def test_reject_large_gap(self):
        s1 = SubtitleSegment(1, 0, 1000, "First")
        s2 = SubtitleSegment(2, 1400, 2000, "Second")  # Gap is 400ms (> 300ms)
        editor = SubtitleEditor([s1, s2])

        with self.assertRaises(ValueError):
            editor.merge_segments(1, 2)

    def test_allow_large_gap_override(self):
        s1 = SubtitleSegment(1, 0, 1000, "First")
        s2 = SubtitleSegment(2, 1400, 2000, "Second")  # Gap is 400ms (> 300ms)
        editor = SubtitleEditor([s1, s2])

        merged = editor.merge_segments(1, 2, allow_large_gap=True)
        self.assertEqual(merged.text, "First Second")
        self.assertEqual(merged.end_ms, 2000)

    def test_reject_max_duration(self):
        s1 = SubtitleSegment(1, 0, 3000, "First")
        s2 = SubtitleSegment(2, 3100, 7000, "Second")  # Duration is 7000ms (> 6000ms)
        editor = SubtitleEditor([s1, s2])

        with self.assertRaises(ValueError):
            editor.merge_segments(1, 2)

    def test_reject_max_chars(self):
        s1 = SubtitleSegment(1, 0, 1000, "A" * 60)
        s2 = SubtitleSegment(2, 1100, 2000, "B" * 61)  # Combined text is 121 chars (> 120 chars)
        editor = SubtitleEditor([s1, s2])

        with self.assertRaises(ValueError):
            editor.merge_segments(1, 2)

    def test_split_valid(self):
        s1 = SubtitleSegment(1, 0, 2000, "Hello World")
        editor = SubtitleEditor([s1])

        first, second = editor.split_segment(1, 1000, "Hello", "World")
        self.assertEqual(first.index, 1)
        self.assertEqual(first.start_ms, 0)
        self.assertEqual(first.end_ms, 1000)
        self.assertEqual(first.text, "Hello")

        self.assertEqual(second.index, 2)
        self.assertEqual(second.start_ms, 1000)
        self.assertEqual(second.end_ms, 2000)
        self.assertEqual(second.text, "World")

        segs = editor.list_segments()
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].text, "Hello")
        self.assertEqual(segs[1].text, "World")

    def test_split_rejects_invalid_time_and_text(self):
        s1 = SubtitleSegment(1, 1000, 3000, "Hello World")
        editor = SubtitleEditor([s1])

        # Split time out of bounds (before start)
        with self.assertRaises(ValueError):
            editor.split_segment(1, 999, "Hello", "World")

        # Split time out of bounds (after end)
        with self.assertRaises(ValueError):
            editor.split_segment(1, 3001, "Hello", "World")

        # Split time exactly on boundary
        with self.assertRaises(ValueError):
            editor.split_segment(1, 1000, "Hello", "World")

        # Empty first text
        with self.assertRaises(ValueError):
            editor.split_segment(1, 2000, "", "World")

        # Whitespace second text
        with self.assertRaises(ValueError):
            editor.split_segment(1, 2000, "Hello", "   ")

    def test_replace_text(self):
        s1 = SubtitleSegment(1, 0, 1000, "Hello")
        editor = SubtitleEditor([s1])

        editor.replace_text(1, "Hi There")
        segs = editor.list_segments()
        self.assertEqual(segs[0].text, "Hi There")

        # Invalid replacement (empty text)
        with self.assertRaises(ValueError):
            editor.replace_text(1, "")

        # Invalid replacement (non-existent index)
        with self.assertRaises(ValueError):
            editor.replace_text(99, "Oops")

    def test_list_returns_defensive_copies_and_reindexing(self):
        s1 = SubtitleSegment(1, 0, 1000, "First")
        s2 = SubtitleSegment(2, 1100, 2000, "Second")
        editor = SubtitleEditor([s1, s2])

        # Check list returned is a copy
        segs_list_1 = editor.list_segments()
        segs_list_1.pop()
        self.assertEqual(len(editor.list_segments()), 2)

        # Check elements returned are copies
        segs_list_2 = editor.list_segments()
        segs_list_2[0].text = "Modified Externally"
        self.assertEqual(editor.list_segments()[0].text, "First")

    def test_returned_merged_split_are_defensive_copies(self):
        s1 = SubtitleSegment(1, 0, 1000, "First")
        s2 = SubtitleSegment(2, 1100, 2000, "Second")
        editor = SubtitleEditor([s1, s2])

        # Test merge_segments returned object mutation
        merged = editor.merge_segments(1, 2)
        merged.text = "Mutated Merged Text"
        self.assertEqual(editor.list_segments()[0].text, "First Second")

        # Test split_segment returned objects mutation
        first, second = editor.split_segment(1, 1000, "Hello", "World")
        first.text = "Mutated First"
        second.text = "Mutated Second"
        self.assertEqual(editor.list_segments()[0].text, "Hello")
        self.assertEqual(editor.list_segments()[1].text, "World")


if __name__ == "__main__":
    unittest.main()
