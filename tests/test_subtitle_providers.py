import unittest
from modules.subtitle.schemas import SubtitleSegment
from modules.subtitle.providers.base import SubtitleGenerationConfig, SubtitleProviderResult
from modules.subtitle.providers.whisper import WhisperSubtitleProvider


class TestSubtitleProviders(unittest.TestCase):
    def test_config_defaults(self):
        config = SubtitleGenerationConfig()
        self.assertEqual(config.model, "base")
        self.assertIsNone(config.language)
        self.assertEqual(config.task, "transcribe")
        self.assertEqual(config.source, "whisper")

    def test_no_runner_error(self):
        provider = WhisperSubtitleProvider(runner=None)
        config = SubtitleGenerationConfig()
        with self.assertRaises(RuntimeError) as ctx:
            provider.generate("/path/to/video.mp4", config)
        self.assertIn("Whisper runner is not configured", str(ctx.exception))

    def test_runner_returns_segments(self):
        expected_segs = [SubtitleSegment(1, 0, 1000, "Hello")]

        def mock_runner(video_path, config):
            return expected_segs

        provider = WhisperSubtitleProvider(runner=mock_runner)
        config = SubtitleGenerationConfig()
        res = provider.generate("/path/to/video.mp4", config)

        self.assertIsInstance(res, SubtitleProviderResult)
        self.assertEqual(res.segments, expected_segs)
        self.assertEqual(res.metadata, {})

    def test_runner_returns_dicts(self):
        expected_dicts = [{"index": 1, "start_ms": 0, "end_ms": 1000, "text": "Hello", "source": "whisper"}]

        def mock_runner(video_path, config):
            return expected_dicts

        provider = WhisperSubtitleProvider(runner=mock_runner)
        config = SubtitleGenerationConfig()
        res = provider.generate("/path/to/video.mp4", config)

        self.assertIsInstance(res, SubtitleProviderResult)
        self.assertEqual(len(res.segments), 1)
        seg = res.segments[0]
        self.assertIsInstance(seg, SubtitleSegment)
        self.assertEqual(seg.index, 1)
        self.assertEqual(seg.text, "Hello")

    def test_runner_returns_provider_result(self):
        expected_segs = [SubtitleSegment(1, 0, 1000, "Hello")]
        expected_result = SubtitleProviderResult(segments=expected_segs, metadata={"model": "base"})

        def mock_runner(video_path, config):
            return expected_result

        provider = WhisperSubtitleProvider(runner=mock_runner)
        config = SubtitleGenerationConfig()
        res = provider.generate("/path/to/video.mp4", config)

        self.assertIs(res, expected_result)

    def test_invalid_task_or_path(self):
        def dummy_runner(video_path, config):
            return []

        provider = WhisperSubtitleProvider(runner=dummy_runner)

        # Empty path
        with self.assertRaises(ValueError):
            provider.generate("", SubtitleGenerationConfig())

        # Whitespace path
        with self.assertRaises(ValueError):
            provider.generate("   ", SubtitleGenerationConfig())

        # Invalid task
        invalid_config = SubtitleGenerationConfig(task="invalid_task")
        with self.assertRaises(ValueError):
            provider.generate("/path/to/video.mp4", invalid_config)


if __name__ == "__main__":
    unittest.main()
