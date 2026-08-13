import unittest
from unittest.mock import MagicMock, patch
from app import run_module, ModuleRunRequest
from core.base_module import ModuleMetadata, BaseModule

class MockMetadata:
    def __init__(self, requires_output_dir: bool):
        self.requires_output_dir = requires_output_dir
        self.supports_standalone = True
        self.name = "Mock Module"

class MockModule(BaseModule):
    def __init__(self, module_id: str, requires_output_dir: bool):
        self._module_id = module_id
        self._requires_output_dir = requires_output_dir

    @property
    def module_id(self) -> str:
        return self._module_id

    @property
    def metadata(self):
        return MockMetadata(self._requires_output_dir)

    def validate_params(self, params) -> bool:
        return True

    def run(self, context):
        return MagicMock()

class TestModuleRunAPI(unittest.TestCase):
    @patch("app.module_registry")
    @patch("app.executor")
    @patch("app.load_cached_dir")
    @patch("app.get_run_target_dir")
    @patch("app.task_store")
    @patch("app.save_cached_dir")
    @patch("app.os.makedirs")
    def test_run_module_with_output_dir(self, mock_makedirs, mock_save_cached, mock_task_store, mock_target_dir, mock_cached_dir, mock_executor, mock_registry):
        mock_cached_dir.return_value = "/tmp"
        mock_target_dir.return_value = "/tmp/run_downloader"
        
        # Setup mock downloader module (requires output dir)
        m = MockModule("downloader", requires_output_dir=True)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m

        req = ModuleRunRequest(params={}, input_files=[], output_dir=None)
        res = run_module("downloader", req)

        # get_run_target_dir must be called
        mock_target_dir.assert_called_once()
        mock_task_store.create_task.assert_called_once_with(
            task_id=res["task_id"],
            module_id="downloader",
            filename="Standalone: Mock Module",
            target_dir="/tmp/run_downloader"
        )

    @patch("app.module_registry")
    @patch("app.executor")
    @patch("app.load_cached_dir")
    @patch("app.get_run_target_dir")
    @patch("app.task_store")
    @patch("app.save_cached_dir")
    @patch("app.os.makedirs")
    def test_run_module_without_output_dir(self, mock_makedirs, mock_save_cached, mock_task_store, mock_target_dir, mock_cached_dir, mock_executor, mock_registry):
        mock_cached_dir.return_value = "/tmp"
        
        # Setup mock subtitle module (does NOT require output dir)
        m = MockModule("subtitle", requires_output_dir=False)
        mock_registry.has.return_value = True
        mock_registry.get.return_value = m

        req = ModuleRunRequest(params={}, input_files=[], output_dir=None)
        res = run_module("subtitle", req)

        # get_run_target_dir must NOT be called
        mock_target_dir.assert_not_called()
        mock_task_store.create_task.assert_called_once_with(
            task_id=res["task_id"],
            module_id="subtitle",
            filename="Standalone: Mock Module",
            target_dir=None
        )
    @patch("app.module_registry")
    @patch("app.task_store")
    def test_run_standalone_module_task_receives_none_output_dir(self, mock_task_store, mock_registry):
        m = MockModule("subtitle", requires_output_dir=False)
        mock_registry.get.return_value = m
        mock_task_store.get_task.return_value = {"metrics": {}}

        from app import run_standalone_module_task
        
        with patch("core.base_module.ModuleContext") as MockContext:
            run_standalone_module_task("task_123", "subtitle", {}, [], None)
            MockContext.assert_called_once()
            called_args, called_kwargs = MockContext.call_args
            self.assertIsNone(called_kwargs.get("output_dir"))
            mock_task_store.update_task.assert_any_call(
                "task_123",
                status="processing",
                progress=5.0,
                metrics={"phase": "preparing"}
            )


if __name__ == "__main__":
    unittest.main()
