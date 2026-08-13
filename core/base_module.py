import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable


@dataclass
class ModuleContext:
    task_id: str
    input_files: List[str] = field(default_factory=list)
    output_dir: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    logger: Optional[Any] = None
    progress_callback: Optional[Callable[[float, str], None]] = None


@dataclass
class ModuleResult:
    success: bool = True
    canceled: bool = False
    output_files: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class ModuleMetadata:
    module_id: str
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    supports_standalone: bool = True
    supports_workflow: bool = True
    requires_output_dir: bool = False


class BaseModule(ABC):
    @property
    @abstractmethod
    def module_id(self) -> str:
        """Unique module identifier."""
        pass

    @property
    def metadata(self) -> ModuleMetadata:
        """Returns the module metadata. Default implementation for backward compatibility."""
        return ModuleMetadata(
            module_id=self.module_id,
            name=self.module_id.capitalize(),
            description="",
            input_schema={},
            output_schema={},
            supports_standalone=True,
            supports_workflow=True
        )

    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate input parameters."""
        pass

    @abstractmethod
    def run(self, context: ModuleContext) -> ModuleResult:
        """Execute module task."""
        pass
