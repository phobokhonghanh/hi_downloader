import unittest
from modules.subtitle.schemas import SubtitleSegment, SubtitleProject


class TestSubtitleSchemas(unittest.TestCase):
    def test_valid_segment(self):
        seg = SubtitleSegment(
            index=1,
            start_ms=0,
            end_ms=1500,
            text="Hello, how are you?",
            source="manual",
            confidence=0.95,
        )
        self.assertEqual(seg.index, 1)
        self.assertEqual(seg.start_ms, 0)
        self.assertEqual(seg.end_ms, 1500)
        self.assertEqual(seg.text, "Hello, how are you?")
        self.assertEqual(seg.source, "manual")
        self.assertEqual(seg.confidence, 0.95)
        self.assertEqual(seg.duration_ms, 1500)
        self.assertEqual(seg.validate(), [])

    def test_invalid_index(self):
        seg = SubtitleSegment(index=0, start_ms=0, end_ms=1000, text="Test")
        errors = seg.validate()
        self.assertTrue(any("Index must be >= 1" in err for err in errors))

        seg = SubtitleSegment(index=-5, start_ms=0, end_ms=1000, text="Test")
        errors = seg.validate()
        self.assertTrue(any("Index must be >= 1" in err for err in errors))

    def test_invalid_timing(self):
        # negative start
        seg = SubtitleSegment(index=1, start_ms=-10, end_ms=1000, text="Test")
        errors = seg.validate()
        self.assertTrue(any("start_ms must be >= 0" in err for err in errors))

        # end_ms <= start_ms
        seg = SubtitleSegment(index=1, start_ms=1000, end_ms=1000, text="Test")
        errors = seg.validate()
        self.assertTrue(any("must be strictly greater than start_ms" in err for err in errors))

        seg = SubtitleSegment(index=1, start_ms=1000, end_ms=500, text="Test")
        errors = seg.validate()
        self.assertTrue(any("must be strictly greater than start_ms" in err for err in errors))

    def test_invalid_text(self):
        # empty text
        seg = SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="")
        errors = seg.validate()
        self.assertTrue(any("text cannot be empty" in err for err in errors))

        # whitespace text
        seg = SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="   ")
        errors = seg.validate()
        self.assertTrue(any("text cannot be empty" in err for err in errors))

    def test_invalid_confidence(self):
        # below 0
        seg = SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Test", confidence=-0.1)
        errors = seg.validate()
        self.assertTrue(any("confidence must be in range 0..1" in err for err in errors))

        # above 1
        seg = SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Test", confidence=1.01)
        errors = seg.validate()
        self.assertTrue(any("confidence must be in range 0..1" in err for err in errors))

        # correct boundary confidence values should not fail
        seg = SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Test", confidence=0.0)
        self.assertEqual(seg.validate(), [])

        seg = SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Test", confidence=1.0)
        self.assertEqual(seg.validate(), [])

    def test_gap_and_overlap(self):
        s1 = SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Hello")
        s2 = SubtitleSegment(index=2, start_ms=1000, end_ms=2000, text="World")
        s3 = SubtitleSegment(index=3, start_ms=1500, end_ms=2500, text="Overlap")

        # Gap tests
        self.assertEqual(s1.gap_to_next(s2), 0)
        self.assertEqual(s1.gap_to_next(s3), 500)
        self.assertEqual(s2.gap_to_next(s3), -500)

        # Overlap tests
        self.assertFalse(s1.overlaps(s2))
        self.assertTrue(s2.overlaps(s3))
        self.assertTrue(s3.overlaps(s2))
        self.assertFalse(s1.overlaps(s3))

    def test_to_from_dict(self):
        seg = SubtitleSegment(
            index=3,
            start_ms=1200,
            end_ms=2400,
            text="Python is awesome",
            source="manual",
            confidence=0.88,
        )
        d = seg.to_dict()
        expected = {
            "index": 3,
            "start_ms": 1200,
            "end_ms": 2400,
            "text": "Python is awesome",
            "source": "manual",
            "confidence": 0.88,
            "asr_corrected": False,
            "corrected_source": None,
            "correction_note": None,
            "original_translation": None,
        }
        self.assertEqual(d, expected)

        seg_from = SubtitleSegment.from_dict(d)
        self.assertEqual(seg, seg_from)

    def test_project_active_segments(self):
        raw_segs = [SubtitleSegment(1, 0, 1000, "Raw 1")]
        edited_segs = [SubtitleSegment(1, 0, 1200, "Edited 1")]
        project = SubtitleProject(
            project_id="proj_1",
            video_path="/path/to/video.mp4",
            raw_segments=raw_segs,
            edited_segments=edited_segs,
            settings={"lang": "en"},
        )

        self.assertEqual(project.get_active_segments(use_edited=True), edited_segs)
        self.assertEqual(project.get_active_segments(use_edited=False), raw_segs)

    def test_project_to_from_dict(self):
        raw_segs = [SubtitleSegment(1, 0, 1000, "Raw 1")]
        edited_segs = [SubtitleSegment(1, 0, 1200, "Edited 1")]
        project = SubtitleProject(
            project_id="proj_1",
            video_path="/path/to/video.mp4",
            raw_segments=raw_segs,
            edited_segments=edited_segs,
            settings={"lang": "en"},
        )

        d = project.to_dict()
        project_from = SubtitleProject.from_dict(d)
        self.assertEqual(project.project_id, project_from.project_id)
        self.assertEqual(project.video_path, project_from.video_path)
        self.assertEqual(project.settings, project_from.settings)
        self.assertEqual(len(project_from.raw_segments), 1)
        self.assertEqual(project_from.raw_segments[0].text, "Raw 1")
        self.assertEqual(len(project_from.edited_segments), 1)
        self.assertEqual(project_from.edited_segments[0].text, "Edited 1")

    def test_project_validation_clean(self):
        raw_segs = [
            SubtitleSegment(1, 0, 1000, "Raw 1"),
            SubtitleSegment(2, 1000, 2000, "Raw 2"),
        ]
        edited_segs = [
            SubtitleSegment(1, 0, 1000, "Edited 1"),
            SubtitleSegment(2, 1200, 2200, "Edited 2"),
        ]
        project = SubtitleProject(
            project_id="proj_1",
            video_path="/path/to/video.mp4",
            raw_segments=raw_segs,
            edited_segments=edited_segs,
        )
        self.assertEqual(project.validate(), [])

    def test_project_validation_aggregates_segment_errors(self):
        raw_segs = [SubtitleSegment(0, 0, 1000, "Raw 1")]  # invalid index
        edited_segs = [SubtitleSegment(1, 1000, 500, "")]  # invalid end_ms and text
        project = SubtitleProject(
            project_id="proj_1",
            video_path="/path/to/video.mp4",
            raw_segments=raw_segs,
            edited_segments=edited_segs,
        )
        errors = project.validate()
        self.assertTrue(len(errors) >= 3)
        self.assertTrue(any("Raw segment at index 0" in err for err in errors))
        self.assertTrue(any("Index must be >= 1" in err for err in errors))
        self.assertTrue(any("Edited segment at index 0" in err for err in errors))
        self.assertTrue(any("must be strictly greater than start_ms" in err for err in errors))
        self.assertTrue(any("text cannot be empty" in err for err in errors))

    def test_project_validation_chronological_ordering(self):
        # edited segments out of order
        edited_segs = [
            SubtitleSegment(1, 1000, 2000, "Second in time"),
            SubtitleSegment(2, 0, 1000, "First in time"),
        ]
        project = SubtitleProject(
            project_id="proj_1",
            video_path="/path/to/video.mp4",
            edited_segments=edited_segs,
        )
        errors = project.validate()
        self.assertTrue(any("not in chronological order" in err for err in errors))

    def test_project_validation_overlap(self):
        # edited segments overlap
        edited_segs = [
            SubtitleSegment(1, 0, 1500, "First"),
            SubtitleSegment(2, 1000, 2000, "Overlap"),
        ]
        project = SubtitleProject(
            project_id="proj_1",
            video_path="/path/to/video.mp4",
            edited_segments=edited_segs,
        )
        errors = project.validate()
        self.assertTrue(any("overlaps with segment" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
