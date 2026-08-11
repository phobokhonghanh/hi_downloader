import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from app import run_workflow, WorkflowRunRequest, StepRunRequest
from core.base_module import ModuleMetadata, BaseModule


class MockModule(BaseModule):
    def __init__(self, module_id: str, supports_workflow: bool):
        self._module_id = module_id
        self._supports_workflow = supports_workflow

    @property
    def module_id(self) -> str:
        return self._module_id

    @property
    def metadata(self) -> ModuleMetadata:
        return ModuleMetadata(
            module_id=self.module_id,
            name=f"Mock {self.module_id}",
            description="Mock module",
            supports_workflow=self._supports_workflow
        )

    def validate_params(self, params) -> bool:
        return True

    def run(self, context):
        return MagicMock()


class TestWorkflowAPI(unittest.TestCase):
    def setUp(self):
        self.registry_mock = MagicMock()
        self.executor_mock = MagicMock()

    @patch("app.module_registry")
    @patch("app.executor")
    @patch("app.load_cached_dir")
    @patch("app.get_run_target_dir")
    @patch("app.task_store")
    @patch("app.save_cached_dir")
    @patch("app.os.makedirs")
    def test_run_workflow_success(self, mock_makedirs, mock_save_cached, mock_task_store, mock_target_dir, mock_cached_dir, mock_executor, mock_registry):
        mock_cached_dir.return_value = "/tmp"
        mock_target_dir.return_value = "/tmp/run1"
        
        # Setup module
        m = MockModule("downloader", supports_workflow=True)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m
        
        req = WorkflowRunRequest(
            name="Test Workflow",
            steps=[
                StepRunRequest(step_id="step1", module_id="downloader", on_error="stop")
            ],
            initial_inputs=[]
        )
        
        res = run_workflow(req)
        self.assertEqual(res["status"], "pending")
        self.assertIsNotNone(res["task_id"])
        mock_executor.submit.assert_called_once()
        mock_save_cached.assert_called_once_with(mock_cached_dir.return_value)
        mock_makedirs.assert_called_once_with(mock_cached_dir.return_value, exist_ok=True)

    @patch("app.module_registry")
    def test_run_workflow_missing_steps(self, mock_registry):
        req = WorkflowRunRequest(name="Test Workflow", steps=[], initial_inputs=[])
        with self.assertRaises(HTTPException) as context:
            run_workflow(req)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("ít nhất 1 bước", context.exception.detail)

    @patch("app.module_registry")
    def test_run_workflow_invalid_on_error(self, mock_registry):
        req = WorkflowRunRequest(
            name="Test Workflow",
            steps=[
                StepRunRequest(step_id="step1", module_id="downloader", on_error="invalid_value")
            ],
            initial_inputs=[]
        )
        with self.assertRaises(HTTPException) as context:
            run_workflow(req)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("không hợp lệ", context.exception.detail)

    @patch("app.module_registry")
    def test_run_workflow_missing_module(self, mock_registry):
        mock_registry.has.return_value = False
        req = WorkflowRunRequest(
            name="Test Workflow",
            steps=[
                StepRunRequest(step_id="step1", module_id="non_existent", on_error="stop")
            ],
            initial_inputs=[]
        )
        with self.assertRaises(HTTPException) as context:
            run_workflow(req)
        self.assertEqual(context.exception.status_code, 404)
        self.assertIn("không tồn tại", context.exception.detail)

    @patch("app.module_registry")
    def test_run_workflow_unsupported_module(self, mock_registry):
        m = MockModule("downloader", supports_workflow=False)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m
        req = WorkflowRunRequest(
            name="Test Workflow",
            steps=[
                StepRunRequest(step_id="step1", module_id="downloader", on_error="stop")
            ],
            initial_inputs=[]
        )
        with self.assertRaises(HTTPException) as context:
            run_workflow(req)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("không hỗ trợ", context.exception.detail)
    def test_run_workflow_empty_name(self):
        req = WorkflowRunRequest(name="   ", steps=[StepRunRequest(step_id="step1", module_id="downloader")], initial_inputs=[])
        with self.assertRaises(HTTPException) as context:
            run_workflow(req)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Tên workflow", context.exception.detail)

    def test_run_workflow_empty_step_or_module_id(self):
        req1 = WorkflowRunRequest(
            name="Test Workflow",
            steps=[StepRunRequest(step_id="  ", module_id="downloader")],
            initial_inputs=[]
        )
        with self.assertRaises(HTTPException) as context:
            run_workflow(req1)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("ID của step", context.exception.detail)

        req2 = WorkflowRunRequest(
            name="Test Workflow",
            steps=[StepRunRequest(step_id="step1", module_id=" ")],
            initial_inputs=[]
        )
        with self.assertRaises(HTTPException) as context:
            run_workflow(req2)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("ID của module", context.exception.detail)

    def test_run_workflow_duplicate_step_id(self):
        req = WorkflowRunRequest(
            name="Test Workflow",
            steps=[
                StepRunRequest(step_id="step1", module_id="downloader"),
                StepRunRequest(step_id="step1", module_id="downloader")
            ],
            initial_inputs=[]
        )
        with self.assertRaises(HTTPException) as context:
            run_workflow(req)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("bị trùng lặp", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
