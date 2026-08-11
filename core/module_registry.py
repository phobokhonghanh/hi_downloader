import copy
from typing import Dict, List, Any
from core.base_module import BaseModule, ModuleMetadata


class ModuleRegistry:
    def __init__(self):
        self._modules: Dict[str, BaseModule] = {}

    def register(self, module: BaseModule) -> None:
        if not module:
            raise ValueError("Module cannot be None")
        module_id = module.module_id
        if not module_id or not isinstance(module_id, str) or not module_id.strip():
            raise ValueError("Module ID cannot be empty")
        if module_id in self._modules:
            raise ValueError(f"Module ID '{module_id}' is already registered")
        self._modules[module_id] = module

    def get(self, module_id: str) -> BaseModule:
        if not module_id:
            raise KeyError("Module ID cannot be empty")
        if module_id not in self._modules:
            raise KeyError(f"Module '{module_id}' not found")
        return self._modules[module_id]

    def has(self, module_id: str) -> bool:
        if not module_id:
            return False
        return module_id in self._modules

    def list_modules(self) -> List[ModuleMetadata]:
        return [copy.deepcopy(m.metadata) for m in self._modules.values()]

    def list_module_dicts(self) -> List[Dict[str, Any]]:
        result = []
        for m in self._modules.values():
            meta = m.metadata
            result.append({
                "module_id": meta.module_id,
                "name": meta.name,
                "description": meta.description,
                "input_schema": copy.deepcopy(meta.input_schema),
                "output_schema": copy.deepcopy(meta.output_schema),
                "supports_standalone": meta.supports_standalone,
                "supports_workflow": meta.supports_workflow
            })
        return copy.deepcopy(result)
