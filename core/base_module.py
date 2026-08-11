import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ModuleContext:
    task_id: str
    input_files: List[str] = field(default_factory=list)
    output_dir: str = "."
    params: Dict[str, Any] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    logger: Optional[Any] = None


@dataclass
class ModuleResult:
    success: bool = True
    canceled: bool = False
    output_files: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class BaseModule(ABC):
    @property
    @abstractmethod
    def module_id(self) -> str:
        """Unique module identifier."""
        pass

    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate input parameters."""
        pass

    @abstractmethod
    def run(self, context: ModuleContext) -> ModuleResult:
        """Execute module task."""
        pass
