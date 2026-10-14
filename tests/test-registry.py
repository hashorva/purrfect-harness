#!/usr/bin/env python3
import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("harness_registry", ROOT / "scripts/harness_registry.py")
registry_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry_module)
registry = registry_module.load_registry()


class RegistryTests(unittest.TestCase):
    def test_parity_with_existing_constants(self):
        fleet_spec = importlib.util.spec_from_file_location("fleet_state", ROOT / "scripts/fleet_state.py")
        fleet = importlib.util.module_from_spec(fleet_spec)
        fleet_spec.loader.exec_module(fleet)
        self.assertEqual(tuple(registry["providers"].keys()), tuple("cursor" if p == "agent" else p for p in fleet.PROVIDERS))
        self.assertEqual({("agent" if p == "cursor" else p): v["capabilities"] for p, v in registry["providers"].items()}, fleet.CAPABILITIES)
        expected_seats = {k: tuple("agent" if p == "cursor" else p for p in v) for k, v in registry["seat_specs"].items()}
        self.assertEqual(expected_seats, fleet.SEAT_SPECS)
        self.assertEqual(registry["fallbacks"], fleet.FALLBACKS)

    def test_each_required_field_is_checked(self):
        cases = [("root." + key, (key,)) for key in registry_module.ROOT_FIELDS]
        cases += [(f"provider.{field}", ("providers", "claude", field)) for field in registry_module.PROVIDER_FIELDS]
        cases += [(f"provider.capabilities.{field}", ("providers", "claude", "capabilities", field)) for field in ("efforts", "speeds")]
        cases += [(f"door.{field}", ("doors", "claude", field)) for field in registry_module.DOOR_FIELDS]
        for label, path in cases:
            with self.subTest(field=label):
                broken = copy.deepcopy(registry)
                cursor = broken
                for key in path[:-1]:
                    cursor = cursor[key]
                del cursor[path[-1]]
                with self.assertRaisesRegex(registry_module.RegistryError, "missing required field"):
                    registry_module.validate_registry(broken)

    def test_agent_is_legacy_only(self):
        self.assertNotIn("agent", registry["providers"])
        self.assertIn("agent", registry["providers"]["cursor"]["legacy_names"])
        broken = copy.deepcopy(registry)
        broken["providers"]["agent"] = copy.deepcopy(broken["providers"]["cursor"])
        with self.assertRaisesRegex(registry_module.RegistryError, "legacy name"):
            registry_module.validate_registry(broken)


if __name__ == "__main__":
    unittest.main()
