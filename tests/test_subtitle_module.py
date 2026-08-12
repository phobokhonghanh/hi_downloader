import unittest
import threading
from core.base_module import ModuleContext
from modules.subtitle.module import SubtitleModule
from modules.subtitle.schemas import SubtitleSegment


class TestSubtitleModule(unittest.TestCase):
    def setUp(self):
        self.module = SubtitleModule()

    def test_metadata(self):
        self.assertEqual(self.module.module_id, "subtitle")
        metadata = self.module.metadata
        self.assertEqual(metadata.module_id, "subtitle")
        self.assertTrue(metadata.supports_standalone)
        self.assertTrue(metadata.supports_workflow)
        self.assertIn("parse_srt", metadata.input_schema["properties"]["action"]["enum"])

    def test_validate_params(self):
        # Invalid parameters
        self.assertFalse(self.module.validate_params(None))
        self.assertFalse(self.module.validate_params({}))
        self.assertFalse(self.module.validate_params({"action": "invalid_action"}))

        # parse_srt validation
        self.assertFalse(self.module.validate_params({"action": "parse_srt"}))
        self.assertFalse(self.module.validate_params({"action": "parse_srt", "srt_text": 123}))
        self.assertTrue(self.module.validate_params({"action": "parse_srt", "srt_text": "SRT"}))

        # export_srt validation
        self.assertFalse(self.module.validate_params({"action": "export_srt"}))
        self.assertFalse(self.module.validate_params({"action": "export_srt", "segments": "not_list"}))
        self.assertTrue(self.module.validate_params({"action": "export_srt", "segments": []}))

        # merge validation
        self.assertFalse(self.module.validate_params({"action": "merge"}))
        self.assertFalse(self.module.validate_params({"action": "merge", "segments": []}))  # missing start_index/end_index
        self.assertFalse(
            self.module.validate_params({"action": "merge", "segments": [], "start_index": 1, "end_index": "2"})
        )
        self.assertTrue(
            self.module.validate_params({"action": "merge", "segments": [], "start_index": 1, "end_index": 2})
        )
        # test optional params
        self.assertTrue(
            self.module.validate_params(
                {
                    "action": "merge",
                    "segments": [],
                    "start_index": 1,
                    "end_index": 2,
                    "max_gap_ms": 500,
                    "allow_large_gap": True,
                }
            )
        )
        self.assertFalse(
            self.module.validate_params(
                {
                    "action": "merge",
                    "segments": [],
                    "start_index": 1,
                    "end_index": 2,
                    "max_gap_ms": "500",  # String instead of int
                }
            )
        )

        # split validation
        self.assertFalse(self.module.validate_params({"action": "split"}))
        self.assertFalse(
            self.module.validate_params(
                {
                    "action": "split",
                    "segments": [],
                    "index": 1,
                    "split_at_ms": 1000,
                    "first_text": "One",
                    # missing second_text
                }
            )
        )
        self.assertTrue(
            self.module.validate_params(
                {
                    "action": "split",
                    "segments": [],
                    "index": 1,
                    "split_at_ms": 1000,
                    "first_text": "One",
                    "second_text": "Two",
                }
            )
        )

        # replace_text validation
        self.assertFalse(self.module.validate_params({"action": "replace_text"}))
        self.assertTrue(
            self.module.validate_params({"action": "replace_text", "segments": [], "index": 1, "text": "New text"})
        )
        self.assertFalse(
            self.module.validate_params({"action": "replace_text", "segments": [], "index": "1", "text": "New text"})
        )

        # generate_whisper validation
        self.assertFalse(self.module.validate_params({"action": "generate_whisper"}))
        self.assertFalse(self.module.validate_params({"action": "generate_whisper", "video_path": ""}))
        self.assertFalse(self.module.validate_params({"action": "generate_whisper", "video_path": 123}))
        self.assertTrue(self.module.validate_params({"action": "generate_whisper", "video_path": "path.mp4"}))
        self.assertTrue(
            self.module.validate_params(
                {
                    "action": "generate_whisper",
                    "video_path": "path.mp4",
                    "model": "base",
                    "task": "translate",
                    "language": "en",
                }
            )
        )
        self.assertFalse(
            self.module.validate_params({"action": "generate_whisper", "video_path": "path.mp4", "task": "invalid"})
        )
        self.assertFalse(
            self.module.validate_params({"action": "generate_whisper", "video_path": "path.mp4", "model": 123})
        )

    def test_run_parse_srt(self):
        srt_text = "1\n00:00:01,000 --> 00:00:02,000\nHello World\n"
        context = ModuleContext(task_id="task_1", params={"action": "parse_srt", "srt_text": srt_text})
        res = self.module.run(context)
        self.assertTrue(res.success)
        self.assertIn("segments", res.metrics)
        self.assertEqual(len(res.metrics["segments"]), 1)
        self.assertEqual(res.metrics["segments"][0]["text"], "Hello World")

    def test_run_export_srt(self):
        segments = [SubtitleSegment(1, 1000, 2000, "Hello World").to_dict()]
        context = ModuleContext(task_id="task_2", params={"action": "export_srt", "segments": segments})
        res = self.module.run(context)
        self.assertTrue(res.success)
        self.assertIn("srt_text", res.metrics)
        self.assertIn("00:00:01,000 --> 00:00:02,000\nHello World", res.metrics["srt_text"])

    def test_run_merge_reject_large_gap(self):
        segments = [
            SubtitleSegment(1, 0, 1000, "First").to_dict(),
            SubtitleSegment(2, 2000, 3000, "Second").to_dict(),  # Gap is 1000ms
        ]
        context = ModuleContext(
            task_id="task_3",
            params={
                "action": "merge",
                "segments": segments,
                "start_index": 1,
                "end_index": 2,
                "max_gap_ms": 300,
                "allow_large_gap": False,
            },
        )
        res = self.module.run(context)
        self.assertFalse(res.success)
        self.assertIsNotNone(res.error)

    def test_run_merge_allow_override(self):
        segments = [
            SubtitleSegment(1, 0, 1000, "First").to_dict(),
            SubtitleSegment(2, 2000, 3000, "Second").to_dict(),  # Gap is 1000ms
        ]
        context = ModuleContext(
            task_id="task_4",
            params={
                "action": "merge",
                "segments": segments,
                "start_index": 1,
                "end_index": 2,
                "max_gap_ms": 300,
                "allow_large_gap": True,
            },
        )
        res = self.module.run(context)
        self.assertTrue(res.success)
        self.assertEqual(res.metrics["merged_segment"]["text"], "First Second")
        self.assertEqual(len(res.metrics["segments"]), 1)

    def test_run_split(self):
        segments = [SubtitleSegment(1, 0, 2000, "First Second").to_dict()]
        context = ModuleContext(
            task_id="task_5",
            params={
                "action": "split",
                "segments": segments,
                "index": 1,
                "split_at_ms": 1000,
                "first_text": "First",
                "second_text": "Second",
            },
        )
        res = self.module.run(context)
        self.assertTrue(res.success)
        self.assertEqual(len(res.metrics["segments"]), 2)
        self.assertEqual(res.metrics["split_segments"][0]["text"], "First")
        self.assertEqual(res.metrics["split_segments"][1]["text"], "Second")

    def test_run_replace_text(self):
        segments = [SubtitleSegment(1, 0, 1000, "Original").to_dict()]
        context = ModuleContext(
            task_id="task_6",
            params={"action": "replace_text", "segments": segments, "index": 1, "text": "Replacement"},
        )
        res = self.module.run(context)
        self.assertTrue(res.success)
        self.assertEqual(res.metrics["segments"][0]["text"], "Replacement")

    def test_run_generate_whisper_success(self):
        from modules.subtitle.providers import SubtitleProviderResult, SubtitleGenerationConfig
        from unittest.mock import MagicMock

        fake_result = SubtitleProviderResult(
            segments=[SubtitleSegment(1, 1000, 2000, "Hello")], metadata={"model": "base"}
        )
        fake_provider = MagicMock()
        fake_provider.generate.return_value = fake_result

        module = SubtitleModule(whisper_provider=fake_provider)
        context = ModuleContext(
            task_id="task_9",
            params={
                "action": "generate_whisper",
                "video_path": "test.mp4",
                "model": "base",
                "language": "en",
                "task": "translate",
            },
        )
        res = module.run(context)
        self.assertTrue(res.success)
        self.assertEqual(res.metrics["metadata"], {"model": "base"})
        self.assertEqual(len(res.metrics["segments"]), 1)
        self.assertEqual(res.metrics["segments"][0]["text"], "Hello")
        self.assertIn("00:00:01,000 --> 00:00:02,000\nHello", res.metrics["srt_text"])

        fake_provider.generate.assert_called_once()
        called_args, called_kwargs = fake_provider.generate.call_args
        self.assertEqual(called_args[0], "test.mp4")
        self.assertIsInstance(called_args[1], SubtitleGenerationConfig)
        self.assertEqual(called_args[1].model, "base")
        self.assertEqual(called_args[1].language, "en")
        self.assertEqual(called_args[1].task, "translate")

    def test_run_generate_whisper_error(self):
        from unittest.mock import MagicMock

        fake_provider = MagicMock()
        fake_provider.generate.side_effect = RuntimeError("Generation failed")

        module = SubtitleModule(whisper_provider=fake_provider)
        context = ModuleContext(task_id="task_10", params={"action": "generate_whisper", "video_path": "test.mp4"})
        res = module.run(context)
        self.assertFalse(res.success)
        self.assertIn("Generation failed", res.error)

    def test_cancel_before_run(self):
        cancel_event = threading.Event()
        cancel_event.set()
        context = ModuleContext(
            task_id="task_7", params={"action": "parse_srt", "srt_text": ""}, cancel_event=cancel_event
        )
        res = self.module.run(context)
        self.assertFalse(res.success)
        self.assertTrue(res.canceled)
        self.assertEqual(res.error, "Canceled before run")

    def test_invalid_params_returns_failed(self):
        context = ModuleContext(task_id="task_8", params={"action": "parse_srt"})  # missing srt_text
        res = self.module.run(context)
        self.assertFalse(res.success)
        self.assertEqual(res.error, "Invalid parameters")


if __name__ == "__main__":
    unittest.main()
