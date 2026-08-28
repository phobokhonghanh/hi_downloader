import unittest
from typing import Dict, Any
from core.task_store import TaskStore, TaskStatus
from core.base_module import BaseModule, ModuleContext, ModuleResult
from workflow.schemas import StepConfig, WorkflowConfig
from workflow.engine import WorkflowEngine


class MockExtractorModule(BaseModule):
    @property
    def module_id(self) -> str:
        return "mock_extractor"

    def validate_params(self, params: Dict[str, Any]) -> bool:
        return True

    def run(self, context: ModuleContext) -> ModuleResult:
        if context.cancel_event.is_set():
            return ModuleResult(success=False, canceled=True, error="Canceled before run")
        inputs = context.input_files or ["raw_video.mp4"]
        outputs = [f"{f}_sub.srt" for f in inputs]
        return ModuleResult(success=True, output_files=outputs, metrics={"count": len(outputs)})


class MockTranslatorModule(BaseModule):
    @property
    def module_id(self) -> str:
        return "mock_translator"

    def validate_params(self, params: Dict[str, Any]) -> bool:
        return True

    def run(self, context: ModuleContext) -> ModuleResult:
        if context.cancel_event.is_set():
            return ModuleResult(success=False, canceled=True, error="Canceled before run")
        outputs = [f"{f}_vi.srt" for f in context.input_files]
        return ModuleResult(success=True, output_files=outputs, metrics={"lang": "vi"})


class MockFailingModule(BaseModule):
    @property
    def module_id(self) -> str:
        return "mock_failing"

    def validate_params(self, params: Dict[str, Any]) -> bool:
        return True

    def run(self, context: ModuleContext) -> ModuleResult:
        return ModuleResult(success=False, error="Mock step failed deliberately")


class MockInvalidParamsModule(BaseModule):
    @property
    def module_id(self) -> str:
        return "mock_invalid_params"

    def validate_params(self, params: Dict[str, Any]) -> bool:
        # Reject if params contain 'invalid' set to True
        return not params.get("invalid", False)

    def run(self, context: ModuleContext) -> ModuleResult:
        return ModuleResult(success=True, output_files=["should_not_run.txt"])


class TestWorkflowEngine(unittest.TestCase):
    def setUp(self):
        self.store = TaskStore()
        self.engine = WorkflowEngine(task_store=self.store)
        self.engine.register_module(MockExtractorModule())
        self.engine.register_module(MockTranslatorModule())
        self.engine.register_module(MockFailingModule())
        self.engine.register_module(MockInvalidParamsModule())

    def test_single_module_workflow_execution(self):
        config = WorkflowConfig(
            workflow_id="wf_single",
            name="Single Step Workflow",
            steps=[
                StepConfig(step_id="step1", module_id="mock_extractor")
            ],
            initial_inputs=["video1.mp4"]
        )

        wf_result = self.engine.execute_workflow("wf_task_1", config)
        self.assertTrue(wf_result.success)
        self.assertFalse(wf_result.canceled)
        self.assertEqual(len(wf_result.final_outputs), 1)
        self.assertEqual(wf_result.final_outputs[0], "video1.mp4_sub.srt")

        task_snap = self.store.get_task("wf_task_1")
        self.assertEqual(task_snap["status"], "completed")
        self.assertEqual(task_snap["progress"], 100.0)

    def test_two_step_workflow_output_to_input_piping(self):
        config = WorkflowConfig(
            workflow_id="wf_two_step",
            name="Two Step Pipeline",
            steps=[
                StepConfig(step_id="step_extract", module_id="mock_extractor"),
                StepConfig(step_id="step_translate", module_id="mock_translator")
            ],
            initial_inputs=["movie.mp4"]
        )

        wf_result = self.engine.execute_workflow("wf_task_2", config)
        self.assertTrue(wf_result.success)
        self.assertFalse(wf_result.canceled)
        self.assertIn("step_extract", wf_result.step_results)
        self.assertIn("step_translate", wf_result.step_results)

        # Output of step 1: movie.mp4_sub.srt
        # Output of step 2 (piped from step 1): movie.mp4_sub.srt_vi.srt
        self.assertEqual(len(wf_result.final_outputs), 1)
        self.assertEqual(wf_result.final_outputs[0], "movie.mp4_sub.srt_vi.srt")

        task_snap = self.store.get_task("wf_task_2")
        self.assertEqual(task_snap["status"], "completed")

    def test_workflow_stops_on_failed_result(self):
        config = WorkflowConfig(
            workflow_id="wf_fail",
            name="Failing Pipeline",
            steps=[
                StepConfig(step_id="step_fail", module_id="mock_failing", on_error="stop"),
                StepConfig(step_id="step_translate", module_id="mock_translator")
            ]
        )

        wf_result = self.engine.execute_workflow("wf_task_fail", config)
        self.assertFalse(wf_result.success)
        self.assertFalse(wf_result.canceled)
        self.assertIn("step_fail", wf_result.step_results)
        self.assertNotIn("step_translate", wf_result.step_results)
        self.assertEqual(wf_result.error, "Mock step failed deliberately")

        task_snap = self.store.get_task("wf_task_fail")
        self.assertEqual(task_snap["status"], "failed")

    def test_workflow_stops_on_cancel_event(self):
        self.store.create_task("wf_task_cancel", filename="Cancel Pipeline")
        self.store.cancel_task("wf_task_cancel")

        config = WorkflowConfig(
            workflow_id="wf_cancel",
            name="Cancel Pipeline",
            steps=[
                StepConfig(step_id="step_extract", module_id="mock_extractor")
            ]
        )

        wf_result = self.engine.execute_workflow("wf_task_cancel", config)
        self.assertFalse(wf_result.success)
        self.assertTrue(wf_result.canceled)

        task_snap = self.store.get_task("wf_task_cancel")
        self.assertEqual(task_snap["status"], "canceled")

    def test_workflow_stops_on_invalid_params(self):
        config = WorkflowConfig(
            workflow_id="wf_invalid_params",
            name="Invalid Params Pipeline",
            steps=[
                StepConfig(step_id="step_invalid", module_id="mock_invalid_params", params={"invalid": True})
            ]
        )

        wf_result = self.engine.execute_workflow("wf_task_invalid", config)
        self.assertFalse(wf_result.success)
        self.assertFalse(wf_result.canceled)
        self.assertIn("Invalid parameters for step 'step_invalid'", wf_result.error)

        task_snap = self.store.get_task("wf_task_invalid")
        self.assertEqual(task_snap["status"], "failed")
        self.assertIn("Invalid parameters for step 'step_invalid'", task_snap["error"])
    def test_engine_resolves_from_registry(self):
        from core.module_registry import ModuleRegistry
        registry = ModuleRegistry()
        registry.register(MockExtractorModule())

        engine_with_registry = WorkflowEngine(task_store=self.store, module_registry=registry)
        
        # Test finding module from registry
        config = WorkflowConfig(
            workflow_id="wf_registry_test",
            name="Registry Step Workflow",
            steps=[StepConfig(step_id="step1", module_id="mock_extractor")]
        )
        res = engine_with_registry.execute_workflow("wf_registry_task", config)
        self.assertTrue(res.success)

    def test_engine_fallback_to_internal_modules(self):
        from core.module_registry import ModuleRegistry
        registry = ModuleRegistry()
        
        engine_with_registry = WorkflowEngine(task_store=self.store, module_registry=registry)
        # Register in internal self.modules
        engine_with_registry.register_module(MockExtractorModule())

        config = WorkflowConfig(
            workflow_id="wf_fallback_test",
            name="Fallback Step Workflow",
            steps=[StepConfig(step_id="step1", module_id="mock_extractor")]
        )
        res = engine_with_registry.execute_workflow("wf_fallback_task", config)
        self.assertTrue(res.success)

    def test_engine_missing_module_returns_failure(self):
        config = WorkflowConfig(
            workflow_id="wf_missing_test",
            name="Missing Step Workflow",
            steps=[StepConfig(step_id="step1", module_id="non_existent")]
        )
        res = self.engine.execute_workflow("wf_missing_task", config)
        self.assertFalse(res.success)
        self.assertIn("is not registered", res.error)

    def test_workflow_result_to_dict_serialization(self):
        config = WorkflowConfig(
            workflow_id="wf_serialization",
            name="Serialization Workflow",
            steps=[StepConfig(step_id="step1", module_id="mock_extractor")]
        )
        res = self.engine.execute_workflow("wf_serialization_task", config)
        self.assertTrue(res.success)
        
        res_dict = res.to_dict()
        self.assertEqual(res_dict["workflow_id"], "wf_serialization")
        self.assertTrue(res_dict["success"])
        self.assertEqual(res_dict["step_results"]["step1"]["metrics"], {"count": 1})

    def test_workflow_progress_callback_math(self):
        self.store.create_task("wf_task_progress_math", filename="Progress Workflow")
        report = self.engine._make_progress_callback("wf_task_progress_math", 1, 2, "step2")
        report(50.0, "halfway")
        
        task_snap = self.store.get_task("wf_task_progress_math")
        self.assertEqual(task_snap["progress"], 75.0)
        self.assertEqual(task_snap["filename"], "Step 2/2: step2 - halfway")




if __name__ == "__main__":
    unittest.main()
