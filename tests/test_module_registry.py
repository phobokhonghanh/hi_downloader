import unittest
from unittest.mock import MagicMock
from core.base_module import BaseModule, ModuleContext, ModuleResult, ModuleMetadata
from core.module_registry import ModuleRegistry


class DummyModule(BaseModule):
    def __init__(self, module_id: str):
        self._module_id = module_id

    @property
    def module_id(self) -> str:
        return self._module_id

    @property
    def metadata(self) -> ModuleMetadata:
        return ModuleMetadata(
            module_id=self.module_id,
            name=self.module_id.capitalize(),
            description=f"Dummy module {self.module_id}",
            input_schema={},
            output_schema={},
            supports_standalone=True,
            supports_workflow=True
        )

    def validate_params(self, params) -> bool:
        return True

    def run(self, context) -> ModuleResult:
        return ModuleResult(success=True)


class TestModuleRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry()

    def test_register_and_get_and_has(self):
        module = DummyModule("test_module")
        self.assertFalse(self.registry.has("test_module"))
        
        self.registry.register(module)
        self.assertTrue(self.registry.has("test_module"))
        self.assertEqual(self.registry.get("test_module"), module)

    def test_register_empty_module_id(self):
        module_empty = DummyModule("")
        with self.assertRaises(ValueError):
            self.registry.register(module_empty)
            
        module_none = DummyModule(None)
        with self.assertRaises(ValueError):
            self.registry.register(module_none)

    def test_register_duplicate_module_id(self):
        module1 = DummyModule("dup")
        module2 = DummyModule("dup")
        
        self.registry.register(module1)
        with self.assertRaises(ValueError):
            self.registry.register(module2)

    def test_get_missing_module(self):
        with self.assertRaises(KeyError):
            self.registry.get("non_existent")

    def test_list_modules_and_dicts(self):
        m1 = DummyModule("mod1")
        m2 = DummyModule("mod2")
        self.registry.register(m1)
        self.registry.register(m2)
        
        modules = self.registry.list_modules()
        self.assertEqual(len(modules), 2)
        self.assertEqual(modules[0].module_id, "mod1")
        self.assertEqual(modules[1].module_id, "mod2")
        
        dicts = self.registry.list_module_dicts()
        self.assertEqual(len(dicts), 2)
        self.assertEqual(dicts[0]["module_id"], "mod1")
        self.assertEqual(dicts[0]["name"], "Mod1")
        self.assertEqual(dicts[1]["module_id"], "mod2")

    def test_defensive_copies_mutation(self):
        m = DummyModule("defensive_test")
        self.registry.register(m)
        
        # Mutating listed metadata does not mutate registry output
        modules = self.registry.list_modules()
        modules[0].name = "Mutated Name"
        
        refetched_modules = self.registry.list_modules()
        self.assertEqual(refetched_modules[0].name, "Defensive_test")

        # Mutating listed dicts does not mutate registry output
        dicts = self.registry.list_module_dicts()
        dicts[0]["name"] = "Mutated Dict Name"
        dicts[0]["input_schema"]["extra"] = True
        
        refetched_dicts = self.registry.list_module_dicts()
        self.assertEqual(refetched_dicts[0]["name"], "Defensive_test")
        self.assertNotIn("extra", refetched_dicts[0]["input_schema"])


if __name__ == "__main__":
    unittest.main()
