import unittest
from unittest.mock import patch, MagicMock
from modules.subtitle.providers.base import SubtitleGenerationConfig
from modules.subtitle.providers.openai_whisper import OpenAIWhisperRunner


class TestOpenAIWhisperRunner(unittest.TestCase):
    @patch("importlib.import_module")
    def test_missing_package_error(self, mock_import):
        mock_import.side_effect = ImportError("No module named 'whisper'")
        runner = OpenAIWhisperRunner()
        config = SubtitleGenerationConfig()
        with self.assertRaises(RuntimeError) as ctx:
            runner("/path/to/video.mp4", config)
        self.assertIn("openai-whisper", str(ctx.exception))

    @patch("importlib.import_module")
    def test_load_transcribe_called_with_config(self, mock_import):
        mock_whisper = MagicMock()
        mock_import.return_value = mock_whisper

        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        mock_model.transcribe.return_value = {
            "segments": [{"start": 1.0, "end": 2.5, "text": "Hello World", "confidence": 0.9}],
            "language": "en",
        }

        runner = OpenAIWhisperRunner()
        config = SubtitleGenerationConfig(model="medium", language="en", task="translate")
        res = runner("/path/to/video.mp4", config)

        # Check load_model called with correct model
        mock_whisper.load_model.assert_called_once_with("medium")

        # Check transcribe called with correct args
        mock_model.transcribe.assert_called_once_with("/path/to/video.mp4", language="en", task="translate")

        self.assertEqual(len(res.segments), 1)
        seg = res.segments[0]
        self.assertEqual(seg.index, 1)
        self.assertEqual(seg.start_ms, 1000)
        self.assertEqual(seg.end_ms, 2500)
        self.assertEqual(seg.text, "Hello World")
        self.assertEqual(seg.confidence, 0.9)
        self.assertEqual(res.metadata["raw_language"], "en")

    @patch("importlib.import_module")
    def test_empty_text_skipped(self, mock_import):
        mock_whisper = MagicMock()
        mock_import.return_value = mock_whisper
        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "segments": [
                {"start": 1.0, "end": 2.0, "text": "   "},
                {"start": 2.0, "end": 3.0, "text": "Hello"},
            ]
        }

        runner = OpenAIWhisperRunner()
        res = runner("/path/to/video.mp4", SubtitleGenerationConfig())
        self.assertEqual(len(res.segments), 1)
        self.assertEqual(res.segments[0].text, "Hello")
        self.assertEqual(res.segments[0].index, 1)  # Index re-arranged sequentially

    @patch("importlib.import_module")
    def test_invalid_timing_raises(self, mock_import):
        mock_whisper = MagicMock()
        mock_import.return_value = mock_whisper
        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        runner = OpenAIWhisperRunner()

        # negative start time
        mock_model.transcribe.return_value = {"segments": [{"start": -0.5, "end": 2.0, "text": "Negative start"}]}
        with self.assertRaises(ValueError):
            runner("/path/to/video.mp4", SubtitleGenerationConfig())

        # end time <= start time
        mock_model.transcribe.return_value = {"segments": [{"start": 2.0, "end": 1.5, "text": "End before start"}]}
        with self.assertRaises(ValueError):
            runner("/path/to/video.mp4", SubtitleGenerationConfig())

        # missing start time
        mock_model.transcribe.return_value = {"segments": [{"end": 1.5, "text": "Missing start"}]}
        with self.assertRaises(ValueError):
            runner("/path/to/video.mp4", SubtitleGenerationConfig())


if __name__ == "__main__":
    unittest.main()
