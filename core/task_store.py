import copy
import time
import uuid
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class TaskModel:
    task_id: str
    pipeline_id: Optional[str] = None
    module_id: str = "default"
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    speed: str = "0 KB/s"
    eta: str = "N/A"
    elapsed_time: float = 0.0
    retry_count: int = 1
    filename: str = ""
    error: Optional[str] = None
    target_dir: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def to_snapshot(self) -> Dict[str, Any]:
        """Return defensive dictionary snapshot without cancel_event object."""
        snapshot = {
            "id": self.task_id,
            "task_id": self.task_id,
            "pipeline_id": self.pipeline_id,
            "module_id": self.module_id,
            "status": self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "progress": self.progress,
            "speed": self.speed,
            "eta": self.eta,
            "elapsed_time": self.elapsed_time,
            "retry_count": self.retry_count,
            "filename": self.filename,
            "error": self.error,
            "target_dir": self.target_dir,
            "artifacts": list(self.artifacts),
            "metrics": dict(self.metrics),
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        return copy.deepcopy(snapshot)


class TaskStore:
    def __init__(self):
        self._tasks: Dict[str, TaskModel] = {}
        self._lock = threading.RLock()

    def create_task(self, task_id: Optional[str] = None, module_id: str = "default", **kwargs) -> Dict[str, Any]:
        with self._lock:
            tid = task_id or str(uuid.uuid4())
            now = time.time()
            task = TaskModel(
                task_id=tid,
                module_id=module_id,
                created_at=now,
                updated_at=now
            )
            for key, val in kwargs.items():
                if hasattr(task, key) and key != "cancel_event":
                    if key == "status" and isinstance(val, str):
                        try:
                            val = TaskStatus(val)
                        except ValueError:
                            pass
                    setattr(task, key, val)
            self._tasks[tid] = task
            return task.to_snapshot()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                return task.to_snapshot()
            return None

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t.to_snapshot() for t in self._tasks.values()]

    def get_cancel_event(self, task_id: str) -> Optional[threading.Event]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                return task.cancel_event
            return None

    def update_task(self, task_id: str, **kwargs) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            for key, val in kwargs.items():
                if hasattr(task, key) and key != "cancel_event":
                    if key == "status" and isinstance(val, str):
                        try:
                            val = TaskStatus(val)
                        except ValueError:
                            pass
                    setattr(task, key, val)
            task.updated_at = time.time()
            return True

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            task.cancel_event.set()
            task.status = TaskStatus.CANCELED
            task.updated_at = time.time()
            return True

    def is_canceled(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            return task.cancel_event.is_set() or task.status == TaskStatus.CANCELED

    def clear_idle_tasks(self) -> int:
        with self._lock:
            active_statuses = {TaskStatus.DOWNLOADING, TaskStatus.PROCESSING, TaskStatus.MERGING, TaskStatus.PENDING}
            has_active = any(t.status in active_statuses for t in self._tasks.values())
            if has_active:
                return 0
            count = len(self._tasks)
            self._tasks.clear()
            return count
