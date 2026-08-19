import unittest
from modules.subtitle.schemas import SubtitleSegment
from modules.subtitle.editor import SubtitleEditor
from modules.translate.condenser import (
    calculate_segment_word_budget,
    calculate_segment_char_budget,
    check_segment_duration_overflow,
    format_segment_for_prompt,
    count_words,
)
from modules.translate.schemas import TranslationConfig
from modules.translate.providers.gemini import GeminiTranslateProvider, TranslatedLine


class MockGeminiClient:
    def __init__(self):
        self.last_contents = None
        self.last_system_instruction = None
        self.models = self

    def generate_content(self, model, contents, config):
        self.last_contents = contents
        if isinstance(config, dict):
            self.last_system_instruction = config.get("system_instruction")
        else:
            self.last_system_instruction = getattr(config, "system_instruction", None)
        
        # Return mock structured response
        class Response:
            text = '[{"index": 1, "translated_text": "Xin chào thế giới"}]'
            usage_metadata = None

        return Response()


class TestTranslateCondenser(unittest.TestCase):

    def test_word_budget_calculation(self):
        # 2.96s at 3.8 wps with 15% margin -> floor(2.96 * 3.8 * 1.15) = floor(12.935) = 12 words
        budget = calculate_segment_word_budget(start_ms=0, end_ms=2960, target_wps=3.8)
        self.assertEqual(budget, 12)

        # 1.0s at 3.8 wps -> floor(3.8 * 1.15) = 4 words
        budget_short = calculate_segment_word_budget(start_ms=0, end_ms=1000, target_wps=3.8)
        self.assertEqual(budget_short, 4)

        # Very short segment (< 0.5s) respects min_words fallback
        budget_tiny = calculate_segment_word_budget(start_ms=0, end_ms=200, target_wps=3.8, min_words=4)
        self.assertEqual(budget_tiny, 4)

    def test_char_budget_calculation(self):
        # 2.96s at 15 cps -> floor(2.96 * 15) = 44 chars
        budget = calculate_segment_char_budget(start_ms=0, end_ms=2960, target_cps=15.0)
        self.assertEqual(budget, 44)

    def test_duration_overflow_detection(self):
        # 20 words in 2.96s duration (budget 12 words) -> overflow!
        long_text = "Đây là một câu thoại có độ dài quá lớn bao gồm hai mươi từ để kiểm tra khả năng phát hiện tràn thời gian của hệ thống."
        self.assertGreater(count_words(long_text), 15)

        seg = SubtitleSegment(index=1, start_ms=0, end_ms=2960, text=long_text)
        res = check_segment_duration_overflow(seg, target_wps=3.8)

        self.assertTrue(res["is_overflow"])
        self.assertEqual(res["max_words"], 12)
        self.assertGreater(res["actual_words"], 12)
        self.assertGreater(res["actual_wps"], 3.8)

        # Short text in 2.96s duration (budget 12 words) -> no overflow
        short_text = "Xin chào các bạn."
        seg_short = SubtitleSegment(index=2, start_ms=0, end_ms=2960, text=short_text)
        res_short = check_segment_duration_overflow(seg_short, target_wps=3.8)

        self.assertFalse(res_short["is_overflow"])

    def test_subtitle_editor_budget_methods(self):
        long_text = "Đây là một câu thoại dài hơn mười hai từ được sử dụng cho việc kiểm thử tính năng phát hiện tràn thời lượng."
        short_text = "Câu ngắn vừa đủ."
        segs = [
            SubtitleSegment(index=1, start_ms=0, end_ms=2960, text=long_text),
            SubtitleSegment(index=2, start_ms=0, end_ms=5000, text=short_text)
        ]
        editor = SubtitleEditor(segs)

        b1 = editor.calculate_segment_budget(1, target_wps=3.8)
        self.assertTrue(b1["is_overflow"])

        overflows = editor.find_overflow_segments(target_wps=3.8)
        self.assertEqual(len(overflows), 1)
        self.assertEqual(overflows[0]["index"], 1)

    def test_gemini_provider_time_constraint_prompt(self):
        mock_client = MockGeminiClient()
        provider = GeminiTranslateProvider(client=mock_client)

        seg = SubtitleSegment(index=1, start_ms=0, end_ms=2960, text="This is a very long test sentence that contains way too many words for a short timeline segment")
        config = TranslationConfig(
            target_language="vi",
            model="economy",
            enable_time_constraint=True,
            target_wps=3.8
        )

        import threading
        from modules.translate.schemas import TranslationContext
        provider.translate_chunk([seg], config, TranslationContext(), threading.Event())

        self.assertIsNotNone(mock_client.last_contents)
        self.assertIn("duration_s", mock_client.last_contents)
        self.assertIn("max_words", mock_client.last_contents)
        self.assertIn("2.96", mock_client.last_contents)
        self.assertIn("is_overtime", mock_client.last_system_instruction)





if __name__ == "__main__":
    unittest.main()
