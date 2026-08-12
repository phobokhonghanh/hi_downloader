import unittest
from modules.subtitle.schemas import SubtitleSegment
from modules.subtitle.srt import parse_srt, export_srt, parse_timestamp, to_timestamp


class TestSubtitleSrt(unittest.TestCase):
    def test_parse_timestamp(self):
        self.assertEqual(parse_timestamp("00:00:00,000"), 0)
        self.assertEqual(parse_timestamp("00:00:01,000"), 1000)
        self.assertEqual(parse_timestamp("00:01:00,500"), 60500)
        self.assertEqual(parse_timestamp("02:00:00,000"), 7200000)
        self.assertEqual(parse_timestamp("123:45:06,789"), (123 * 3600 + 45 * 60 + 6) * 1000 + 789)

        # Invalid cases
        with self.assertRaises(ValueError):
            parse_timestamp("00:00:01")
        with self.assertRaises(ValueError):
            parse_timestamp("00:00:01,00")
        with self.assertRaises(ValueError):
            parse_timestamp("00:60:00,000")  # minutes >= 60
        with self.assertRaises(ValueError):
            parse_timestamp("00:00:65,000")  # seconds >= 60
        with self.assertRaises(ValueError):
            parse_timestamp("00:00:01.000")  # dot instead of comma
        with self.assertRaises(ValueError):
            parse_timestamp("aa:bb:cc,ddd")

    def test_to_timestamp(self):
        self.assertEqual(to_timestamp(0), "00:00:00,000")
        self.assertEqual(to_timestamp(1000), "00:00:01,000")
        self.assertEqual(to_timestamp(60500), "00:01:00,500")
        self.assertEqual(to_timestamp(7200000), "02:00:00,000")
        self.assertEqual(to_timestamp((123 * 3600 + 45 * 60 + 6) * 1000 + 789), "123:45:06,789")

        with self.assertRaises(ValueError):
            to_timestamp(-1)

    def test_parse_single_block(self):
        srt_content = """1
00:00:01,000 --> 00:00:02,500
Hello World
"""
        segs = parse_srt(srt_content)
        self.assertEqual(len(segs), 1)
        seg = segs[0]
        self.assertEqual(seg.index, 1)
        self.assertEqual(seg.start_ms, 1000)
        self.assertEqual(seg.end_ms, 2500)
        self.assertEqual(seg.text, "Hello World")
        self.assertEqual(seg.source, "manual")

    def test_parse_multiline_text(self):
        srt_content = """1
00:00:01,000 --> 00:00:02,500
Hello
World
This is a test.
"""
        segs = parse_srt(srt_content)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].text, "Hello\nWorld\nThis is a test.")

    def test_export_roundtrip(self):
        original_segs = [
            SubtitleSegment(1, 1000, 2500, "First segment"),
            SubtitleSegment(2, 3000, 4500, "Second segment\nwith newline"),
        ]
        exported = export_srt(original_segs)
        parsed_segs = parse_srt(exported)

        self.assertEqual(len(parsed_segs), len(original_segs))
        for o, p in zip(original_segs, parsed_segs):
            self.assertEqual(o.index, p.index)
            self.assertEqual(o.start_ms, p.start_ms)
            self.assertEqual(o.end_ms, p.end_ms)
            self.assertEqual(o.text, p.text)

    def test_invalid_timestamp(self):
        # end before start
        srt_content = """1
00:00:02,500 --> 00:00:01,000
Invalid Timing
"""
        with self.assertRaises(ValueError):
            parse_srt(srt_content)

        # end equals start
        srt_content = """1
00:00:01,000 --> 00:00:01,000
Invalid Timing
"""
        with self.assertRaises(ValueError):
            parse_srt(srt_content)

    def test_invalid_block(self):
        # Non-numeric index
        srt_content_1 = """abc
00:00:01,000 --> 00:00:02,500
Hello
"""
        with self.assertRaises(ValueError):
            parse_srt(srt_content_1)

        # Missing index
        srt_content_2 = """00:00:01,000 --> 00:00:02,500
Hello
"""
        with self.assertRaises(ValueError):
            parse_srt(srt_content_2)

        # Missing timestamp separator
        srt_content_3 = """1
00:00:01,000 00:00:02,500
Hello
"""
        with self.assertRaises(ValueError):
            parse_srt(srt_content_3)

        # Non-sequential index
        srt_content_4 = """2
00:00:01,000 --> 00:00:02,500
Hello
"""
        with self.assertRaises(ValueError):
            parse_srt(srt_content_4)

        # Chronologically out-of-order start times
        srt_content_5 = """1
00:00:05,000 --> 00:00:06,000
Second block starts first

2
00:00:01,000 --> 00:00:02,000
First block starts second
"""
        with self.assertRaises(ValueError):
            parse_srt(srt_content_5)


        # Empty text
        srt_content_6 = """1
00:00:01,000 --> 00:00:02,000

2
00:00:03,000 --> 00:00:04,000
Valid
"""
        with self.assertRaises(ValueError):
            parse_srt(srt_content_6)

    def test_export_sequential_indexes(self):
        # Input segments with non-sequential, non-1-based indexes
        input_segs = [
            SubtitleSegment(10, 1000, 2000, "First"),
            SubtitleSegment(25, 3000, 4000, "Second"),
        ]
        exported = export_srt(input_segs)
        expected_output = """1
00:00:01,000 --> 00:00:02,000
First

2
00:00:03,000 --> 00:00:04,000
Second
"""
        # Trim whitespace for a robust comparison
        self.assertEqual(exported.strip(), expected_output.strip())

        # Also parsing it back should result in indexes 1 and 2
        parsed = parse_srt(exported)
        self.assertEqual(parsed[0].index, 1)
        self.assertEqual(parsed[1].index, 2)


if __name__ == "__main__":
    unittest.main()
