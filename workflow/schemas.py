from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from core.base_module import ModuleResult


@dataclass
class StepConfig:
    step_id: str
    module_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    on_error: str = "stop"  # "stop" or "skip"


@dataclass
class WorkflowConfig:
    workflow_id: str
    name: str
    steps: List[StepConfig] = field(default_factory=list)
    output_dir: str = "."
    initial_inputs: List[str] = field(default_factory=list)


@dataclass
class StepResult:
    step_id: str
    module_id: str
    result: ModuleResult


@dataclass
class WorkflowResult:
    workflow_id: str
    success: bool = True
    canceled: bool = False
    step_results: Dict[str, ModuleResult] = field(default_factory=dict)
    final_outputs: List[str] = field(default_factory=list)
    error: Optional[str] = None
