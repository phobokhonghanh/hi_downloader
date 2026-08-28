import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from app import run_workflow, WorkflowRunRequest, StepRunRequest, get_modules
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
    @patch("app.workflow_executor")
    @patch("app.load_cached_dir")
    @patch("app.get_run_target_dir")
    @patch("app.task_store")
    @patch("app.save_cached_dir")
    @patch("app.os.makedirs")
    def test_run_workflow_success(self, mock_makedirs, mock_save_cached, mock_task_store, mock_target_dir, mock_cached_dir, mock_executor, mock_registry):
        mock_cached_dir.return_value = "/tmp"
        
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
        mock_save_cached.assert_not_called()
        mock_makedirs.assert_called_once_with(mock_cached_dir.return_value, exist_ok=True)

    @patch("app.module_registry")
    @patch("app.workflow_executor")
    @patch("app.load_cached_dir")
    @patch("app.task_store")
    @patch("app.os.makedirs")
    def test_run_workflow_explicit_output_dir(self, mock_makedirs, mock_task_store, mock_cached_dir, mock_executor, mock_registry):
        m = MockModule("downloader", supports_workflow=True)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m
        req = WorkflowRunRequest(
            name="Test",
            steps=[StepRunRequest(step_id="step1", module_id="downloader")],
            initial_inputs=[],
            output_dir="/explicit/dir"
        )
        res = run_workflow(req)
        args, kwargs = mock_executor.submit.call_args
        config = args[2]
        self.assertEqual(config.output_dir, "/explicit/dir")

    @patch("app.module_registry")
    @patch("app.workflow_executor")
    @patch("app.load_cached_dir")
    @patch("app.task_store")
    @patch("app.os.makedirs")
    def test_run_workflow_fallback_input_file(self, mock_makedirs, mock_task_store, mock_cached_dir, mock_executor, mock_registry):
        m = MockModule("downloader", supports_workflow=True)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m
        req = WorkflowRunRequest(
            name="Test",
            steps=[StepRunRequest(step_id="step1", module_id="downloader")],
            initial_inputs=["/path/to/myvideo.mp4"]
        )
        res = run_workflow(req)
        args, kwargs = mock_executor.submit.call_args
        config = args[2]
        self.assertEqual(config.output_dir, "/path/to")

    @patch("app.module_registry")
    @patch("app.workflow_executor")
    @patch("app.load_cached_dir")
    @patch("app.task_store")
    @patch("app.os.makedirs")
    def test_run_workflow_fallback_cached_dir(self, mock_makedirs, mock_task_store, mock_cached_dir, mock_executor, mock_registry):
        mock_cached_dir.return_value = "/cached/dir"
        m = MockModule("downloader", supports_workflow=True)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m
        req = WorkflowRunRequest(
            name="Test",
            steps=[StepRunRequest(step_id="step1", module_id="downloader")],
            initial_inputs=[]
        )
        res = run_workflow(req)
        args, kwargs = mock_executor.submit.call_args
        config = args[2]
        self.assertEqual(config.output_dir, "/cached/dir")

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
                StepRunRequest(step_id="step1", module_id="subtitle"),
                StepRunRequest(step_id="step1", module_id="subtitle")
            ],
            initial_inputs=[]
        )
        with self.assertRaises(HTTPException) as context:
            run_workflow(req)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("bị trùng lặp", context.exception.detail)

    def test_get_modules_includes_subtitle(self):
        modules = get_modules()
        module_ids = [m["module_id"] for m in modules]
        self.assertIn("subtitle", module_ids)
        self.assertIn("downloader", module_ids)

    @patch("app.module_registry")
    @patch("app.workflow_executor")
    def test_run_workflow_conflict_detection(self, mock_executor, mock_registry):
        import tempfile
        import os
        from app import task_store
        from core.task_store import TaskStatus
        # Clean task store first
        with task_store._lock:
            task_store._tasks.clear()

        m = MockModule("subtitle", supports_workflow=True)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m

        video_path = os.path.join(tempfile.gettempdir(), "video.mp4")

        req1 = WorkflowRunRequest(
            name="Workflow 1",
            steps=[StepRunRequest(step_id="step1", module_id="subtitle")],
            initial_inputs=[video_path]
        )
        res1 = run_workflow(req1)
        self.assertEqual(res1["status"], "pending")
        task_id_1 = res1["task_id"]

        # Run workflow 2 with the same video file -> should raise HTTP 409
        req2 = WorkflowRunRequest(
            name="Workflow 2",
            steps=[StepRunRequest(step_id="step1", module_id="subtitle")],
            initial_inputs=[video_path]
        )
        with self.assertRaises(HTTPException) as context:
            run_workflow(req2)
        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("đang chạy hoặc đang chờ", context.exception.detail)

        # Set status of task 1 to completed
        task_store.update_task(task_id_1, status=TaskStatus.COMPLETED)

        # Run workflow 3 with the same video file -> should succeed now
        req3 = WorkflowRunRequest(
            name="Workflow 3",
            steps=[StepRunRequest(step_id="step1", module_id="subtitle")],
            initial_inputs=[video_path]
        )
        res3 = run_workflow(req3)
        self.assertEqual(res3["status"], "pending")

    @patch("app.module_registry")
    @patch("app.workflow_executor")
    @patch("app.load_cached_dir")
    @patch("app.task_store")
    def test_retry_workflow_success(self, mock_task_store, mock_cached_dir, mock_executor, mock_registry):
        mock_cached_dir.return_value = "/tmp"
        m = MockModule("downloader", supports_workflow=True)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m

        stored_config = {
            "workflow_id": "wf_orig",
            "name": "Test Retry",
            "steps": [
                {"step_id": "step1", "module_id": "downloader", "params": {}, "on_error": "stop"}
            ],
            "output_dir": "/tmp",
            "initial_inputs": []
        }

        # Setup mock_task_store.get_task
        mock_task_store.get_task.return_value = {
            "task_id": "wf_orig_task",
            "module_id": "workflow",
            "status": "failed",
            "workflow_config": stored_config
        }

        from app import retry_workflow
        res = retry_workflow("wf_orig_task")

        self.assertEqual(res["status"], "pending")
        self.assertEqual(res["workflow_id"], "wf_orig")
        self.assertIsNotNone(res["task_id"])
        mock_executor.submit.assert_called_once()
        mock_task_store.create_task.assert_called_once()

    @patch("app.task_store")
    def test_retry_workflow_404_not_found(self, mock_task_store):
        mock_task_store.get_task.return_value = None
        from app import retry_workflow
        with self.assertRaises(HTTPException) as context:
            retry_workflow("missing_task")
        self.assertEqual(context.exception.status_code, 404)

        # Not a workflow task
        mock_task_store.get_task.return_value = {
            "task_id": "some_task",

            "module_id": "downloader",
            "status": "failed"
        }
        with self.assertRaises(HTTPException) as context:
            retry_workflow("some_task")
        self.assertEqual(context.exception.status_code, 404)

    @patch("app.task_store")
    def test_retry_workflow_409_active_completed(self, mock_task_store):
        from app import retry_workflow
        for invalid_status in ("pending", "processing", "downloading", "merging", "completed", "unknown", "waiting", "running", "done"):
            mock_task_store.get_task.return_value = {
                "task_id": "wf_task",
                "module_id": "workflow",
                "status": invalid_status
            }
            with self.assertRaises(HTTPException) as context:
                retry_workflow("wf_task")
            self.assertEqual(context.exception.status_code, 409)


    @patch("app.task_store")
    def test_retry_workflow_400_missing_config(self, mock_task_store):
        mock_task_store.get_task.return_value = {
            "task_id": "wf_task",
            "module_id": "workflow",
            "status": "failed",
            "workflow_config": None
        }
        from app import retry_workflow
        with self.assertRaises(HTTPException) as context:
            retry_workflow("wf_task")
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Không tìm thấy cấu hình gốc", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
