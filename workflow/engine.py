import threading
from typing import Optional, Dict, Any
from core.task_store import TaskStore, TaskStatus
from core.base_module import BaseModule, ModuleContext, ModuleResult
from workflow.schemas import WorkflowConfig, WorkflowResult


class WorkflowEngine:
    def __init__(self, task_store: Optional[TaskStore] = None, module_registry: Optional[Any] = None, logger=None):
        self.task_store = task_store
        self.module_registry = module_registry
        self.modules: Dict[str, BaseModule] = {}
        self.logger = logger

    def register_module(self, module: BaseModule):
        self.modules[module.module_id] = module

    def _get_module(self, module_id: str) -> Optional[BaseModule]:
        if self.module_registry and self.module_registry.has(module_id):
            return self.module_registry.get(module_id)
        return self.modules.get(module_id)

    def execute_workflow(self, workflow_task_id: str, config: WorkflowConfig) -> WorkflowResult:
        if self.task_store:
            # Ensure task exists in task_store
            existing = self.task_store.get_task(workflow_task_id)
            if not existing:
                self.task_store.create_task(
                    task_id=workflow_task_id,
                    module_id="workflow",
                    filename=config.name,
                    target_dir=config.output_dir
                )
            cancel_event = self.task_store.get_cancel_event(workflow_task_id) or threading.Event()
        else:
            cancel_event = threading.Event()

        current_inputs = list(config.initial_inputs)
        total_steps = len(config.steps)
        step_results: Dict[str, ModuleResult] = {}

        if total_steps == 0:
            if self.task_store:
                self.task_store.update_task(workflow_task_id, status=TaskStatus.COMPLETED, progress=100.0)
            return WorkflowResult(
                workflow_id=config.workflow_id,
                success=True,
                canceled=False,
                step_results={},
                final_outputs=current_inputs
            )

        for step_index, step_cfg in enumerate(config.steps):
            # Check cancellation event
            if cancel_event.is_set() or (self.task_store and self.task_store.is_canceled(workflow_task_id)):
                if self.task_store:
                    self.task_store.update_task(workflow_task_id, status=TaskStatus.CANCELED)
                return WorkflowResult(
                    workflow_id=config.workflow_id,
                    success=False,
                    canceled=True,
                    step_results=step_results,
                    error="Workflow canceled before step execution"
                )

            module = self._get_module(step_cfg.module_id)
            if not module:
                err_msg = f"Module '{step_cfg.module_id}' is not registered."
                if self.task_store:
                    self.task_store.update_task(workflow_task_id, status=TaskStatus.FAILED, error=err_msg)
                return WorkflowResult(
                    workflow_id=config.workflow_id,
                    success=False,
                    canceled=False,
                    step_results=step_results,
                    error=err_msg
                )

            # Validate module parameters before execution
            if not module.validate_params(step_cfg.params):
                err_msg = f"Invalid parameters for step '{step_cfg.step_id}' (module '{step_cfg.module_id}')."
                if self.task_store:
                    self.task_store.update_task(workflow_task_id, status=TaskStatus.FAILED, error=err_msg)
                return WorkflowResult(
                    workflow_id=config.workflow_id,
                    success=False,
                    canceled=False,
                    step_results=step_results,
                    error=err_msg
                )

            progress_val = round((step_index / total_steps) * 100.0, 1)
            step_filename = f"Step {step_index + 1}/{total_steps}: {step_cfg.step_id}"
            if self.task_store:
                self.task_store.update_task(
                    workflow_task_id,
                    status=TaskStatus.PROCESSING,
                    progress=progress_val,
                    filename=step_filename
                )

            context = ModuleContext(
                task_id=f"{workflow_task_id}_{step_cfg.step_id}",
                input_files=current_inputs,
                output_dir=config.output_dir,
                params=step_cfg.params,
                cancel_event=cancel_event,
                progress_callback=self._make_progress_callback(
                    workflow_task_id, step_index, total_steps, step_cfg.step_id
                ),
                logger=self.logger,
            )

            if self.logger:
                self.logger(f"Workflow {workflow_task_id}: bắt đầu bước {step_index + 1}/{total_steps} ({step_cfg.step_id}).")

            result = module.run(context)
            step_results[step_cfg.step_id] = result

            if result.canceled or cancel_event.is_set():
                if self.task_store:
                    self.task_store.update_task(workflow_task_id, status=TaskStatus.CANCELED)
                return WorkflowResult(
                    workflow_id=config.workflow_id,
                    success=False,
                    canceled=True,
                    step_results=step_results,
                    error=f"Canceled during step '{step_cfg.step_id}'"
                )

            if not result.success:
                if step_cfg.on_error == "skip":
                    continue
                else:
                    err = result.error or f"Failed at step '{step_cfg.step_id}'"
                    if self.task_store:
                        self.task_store.update_task(workflow_task_id, status=TaskStatus.FAILED, error=err)
                    return WorkflowResult(
                        workflow_id=config.workflow_id,
                        success=False,
                        canceled=False,
                        step_results=step_results,
                        error=err
                    )

            if self.logger:
                self.logger(f"Workflow {workflow_task_id}: hoàn tất bước {step_index + 1}/{total_steps} ({step_cfg.step_id}).")

            # Data piping: pass output of previous step as input to next step
            current_inputs = list(result.output_files)

        if self.task_store:
            self.task_store.update_task(
                workflow_task_id,
                status=TaskStatus.COMPLETED,
                progress=100.0,
                artifacts=current_inputs
            )

        return WorkflowResult(
            workflow_id=config.workflow_id,
            success=True,
            canceled=False,
            step_results=step_results,
            final_outputs=current_inputs
        )

    def _make_progress_callback(self, task_id: str, step_index: int, total_steps: int, step_id: str):
        def report(step_progress: float, phase: str = ""):
            if not self.task_store:
                return
            bounded = max(0.0, min(100.0, float(step_progress)))
            progress = round(((step_index + bounded / 100.0) / total_steps) * 100.0, 1)
            label = f"Step {step_index + 1}/{total_steps}: {step_id}"
            self.task_store.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=progress,
                filename=f"{label} - {phase}" if phase else label,
            )
        return report
