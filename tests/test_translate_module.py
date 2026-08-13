import os
import shutil
import tempfile
import unittest
import threading
from typing import Dict, Any

from core.base_module import ModuleContext, ModuleResult
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.providers.base import BaseTranslateProvider
from modules.translate.module import TranslateModule
from workflow.engine import WorkflowEngine
from workflow.schemas import WorkflowConfig, StepConfig


class FakeCredentialStore:
    def __init__(self, key: str = "SECRET_GEMINI_KEY"):
        self.key = key

    def resolve(self) -> str:
        return self.key


class FakeTranslateProvider(BaseTranslateProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.last_token_usage = {
            "input_tokens": 120,
            "output_tokens": 80,
            "total_tokens": 200
        }

    def analyze_context(self, segments, config, cancel_event):
        return "Fake context"

    def translate_chunk(self, segments, config, context, cancel_event):
        prefix = f"[{config.target_language}] "
        return [
            SubtitleSegment(
                index=s.index,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=f"{prefix}{s.text}",
                source="fake_provider"
            )
            for s in segments
        ]


class TestTranslateModule(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

        self.creds = FakeCredentialStore()
        self.cache = None
        self.provider_factory = lambda key: FakeTranslateProvider(api_key=key)

        self.module = TranslateModule(
            provider_factory=self.provider_factory,
            credential_store=self.creds,
            cache=self.cache
        )

        # Create dummy SRT files
        self.srt1 = os.path.join(self.temp_dir, "video1.srt")
        with open(self.srt1, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

        self.srt2 = os.path.join(self.temp_dir, "video2.srt")
        with open(self.srt2, "w", encoding="utf-8") as f:
            f.write("1\n00:00:02,000 --> 00:00:03,000\nWorld\n")

    def test_validation(self):
        """Test validate_params boundaries."""
        self.assertTrue(self.module.validate_params({"target_language": "vi", "profile": "balanced"}))
        self.assertTrue(self.module.validate_params({"target_language": "en", "profile": "economy", "prompt_version": "v1"}))
        self.assertFalse(self.module.validate_params({}))
        self.assertFalse(self.module.validate_params({"target_language": "vi"}))
        self.assertFalse(self.module.validate_params({"target_language": "vi", "profile": "invalid-profile-name"}))

    def test_run_success_multi_file(self):
        """Verify successful translation run of multiple files with metrics aggregates."""
        progress_calls = []
        def progress_cb(pct, phase):
            progress_calls.append((pct, phase))

        context = ModuleContext(
            task_id="test_task",
            input_files=[self.srt1, self.srt2],
            params={"target_language": "vi", "profile": "balanced"},
            progress_callback=progress_cb
        )

        res = self.module.run(context)
        self.assertTrue(res.success)
        self.assertEqual(len(res.output_files), 2)
        self.assertTrue(res.output_files[0].endswith("video1_vi.srt"))
        self.assertTrue(res.output_files[1].endswith("video2_vi.srt"))
        
        # Verify tokens totals aggregate
        self.assertEqual(res.metrics["files_processed"], 2)
        self.assertEqual(res.metrics["total_tokens"], 400)
        self.assertGreater(len(progress_calls), 0)

    def test_run_secret_absence(self):
        """Verify fallback when api key is not configured."""
        self.creds.key = None
        context = ModuleContext(
            task_id="test_task",
            input_files=[self.srt1],
            params={"target_language": "vi", "profile": "balanced"}
        )
        res = self.module.run(context)
        self.assertFalse(res.success)
        self.assertIn("API Key", res.error)

    def test_run_cancellation(self):
        """Verify early cooperatively stopped cancellations logic."""
        cancel_evt = threading.Event()
        cancel_evt.set()

        context = ModuleContext(
            task_id="test_task",
            input_files=[self.srt1],
            params={"target_language": "vi", "profile": "balanced"},
            cancel_event=cancel_evt
        )

        res = self.module.run(context)
        self.assertFalse(res.success)
        self.assertTrue(res.canceled)

    def test_run_partial_failure(self):
        """Verify failure in intermediate files retains already generated translations in output_files."""
        bad_srt = os.path.join(self.temp_dir, "missing.srt") # File does not exist initially
        
        context = ModuleContext(
            task_id="test_task",
            input_files=[self.srt1, bad_srt],
            params={"target_language": "vi", "profile": "balanced"}
        )

        res = self.module.run(context)
        self.assertFalse(res.success)
        self.assertEqual(len(res.output_files), 1)
        self.assertTrue(res.output_files[0].endswith("video1_vi.srt"))
        self.assertIn("missing.srt", res.error)

    def test_run_prompt_version_and_token_count(self):
        """Verify prompt_version validation and token usage doesn't double count."""
        self.assertFalse(self.module.validate_params({"target_language": "vi", "profile": "balanced", "prompt_version": ""}))
        self.assertFalse(self.module.validate_params({"target_language": "vi", "profile": "balanced", "prompt_version": 123}))
        self.assertTrue(self.module.validate_params({"target_language": "vi", "profile": "balanced", "prompt_version": "v2"}))

        context = ModuleContext(
            task_id="test_task",
            input_files=[self.srt1, self.srt2],
            params={"target_language": "vi", "profile": "balanced", "prompt_version": "v2"}
        )

        res = self.module.run(context)
        self.assertTrue(res.success)
        self.assertEqual(res.metrics["total_tokens"], 400)

    def test_workflow_engine_chain(self):
        """Verify integration inside WorkflowEngine pipeline chaining outputs to translate inputs."""
        from core.base_module import BaseModule, ModuleContext, ModuleResult, ModuleMetadata
        
        # Mock extractor step generating a fake SRT output
        class FakeExtractorModule(BaseModule):
            def __init__(self, output_path):
                self.output_path = output_path

            @property
            def module_id(self) -> str:
                return "extractor"

            def validate_params(self, params: Dict[str, Any]) -> bool:
                return True

            def run(self, context: ModuleContext) -> ModuleResult:
                # Emit fake SRT
                with open(self.output_path, "w", encoding="utf-8") as f:
                    f.write("1\n00:00:00,100 --> 00:00:01,200\nRaw audio segment\n")
                return ModuleResult(success=True, output_files=[self.output_path])

        # Register modules in WorkflowEngine
        engine = WorkflowEngine(task_store=None)
        
        extracted_file = os.path.join(self.temp_dir, "raw_extract.srt")
        engine.register_module(FakeExtractorModule(extracted_file))
        engine.register_module(self.module)

        config = WorkflowConfig(
            workflow_id="test_chain",
            name="Test workflow chain",
            steps=[
                StepConfig(step_id="step1", module_id="extractor", params={}),
                StepConfig(step_id="step2", module_id="translate", params={"target_language": "vi", "profile": "balanced"})
            ]
        )

        # Run workflow engine execution
        result = engine.execute_workflow("test_workflow_task_id", config)
        self.assertTrue(result.success)
        self.assertEqual(len(result.final_outputs), 1)
        self.assertTrue(result.final_outputs[0].endswith("raw_extract_vi.srt"))
        
        with open(result.final_outputs[0], "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("[vi] Raw audio segment", content)
