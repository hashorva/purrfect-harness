#!/usr/bin/env python3
import copy
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("harness_registry", ROOT / "scripts/harness_registry.py")
registry_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry_module)
registry = registry_module.load_registry()

# Golden copy of the fleet_state constants at commit 1345c67.  This must remain
# independent from the registry so the parity proof is not self-referential.
GOLDEN_PROVIDERS = ("claude", "codex", "agent", "agy")
GOLDEN_CAPABILITIES = {
    "claude": {"efforts": ["low", "medium", "high", "xhigh", "max"], "speeds": ["unknown"]},
    "codex": {"efforts": ["low", "medium", "high", "xhigh"], "speeds": ["unknown"]},
    "agent": {"efforts": ["low", "medium", "high", "xhigh"], "speeds": ["standard", "fast"]},
    "agy": {"efforts": ["low", "medium", "high"], "speeds": ["unknown"]},
}
GOLDEN_SEAT_SPECS = {
    "brain": ("claude", "opus"), "brain_fable": ("claude", "fable"),
    "brain_codex": ("codex", "sol"), "cursor.premium": ("agent", "grok"),
    "cursor.economy": ("agent", "composer"), "codex.premium": ("codex", "terra"),
    "codex.economy": ("codex", "luna"), "agy.premium": ("agy", "pro"),
    "agy.economy": ("agy", "flash"), "claude.premium": ("claude", "sonnet"),
    "claude.economy": ("claude", "haiku"),
}
GOLDEN_FALLBACKS = {"grok":"cursor-grok-4.5-high", "composer":"composer-2.5", "sol":"gpt-5.6-sol", "terra":"gpt-5.6-terra", "luna":"gpt-5.6-luna", "pro":"gemini-3.1-pro-high", "flash":"gemini-3.6-flash-high"}


class RegistryTests(unittest.TestCase):
    def test_parity_with_existing_constants(self):
        fleet_spec = importlib.util.spec_from_file_location("fleet_state", ROOT / "scripts/fleet_state.py")
        fleet = importlib.util.module_from_spec(fleet_spec)
        fleet_spec.loader.exec_module(fleet)
        providers, capabilities, seat_specs, executables = registry_module.legacy_view(registry)
        self.assertEqual(providers, GOLDEN_PROVIDERS)
        self.assertEqual(capabilities, GOLDEN_CAPABILITIES)
        self.assertEqual(seat_specs, GOLDEN_SEAT_SPECS)
        self.assertEqual(fleet.PROVIDERS, GOLDEN_PROVIDERS)
        self.assertEqual(fleet.CAPABILITIES, GOLDEN_CAPABILITIES)
        self.assertEqual(fleet.SEAT_SPECS, GOLDEN_SEAT_SPECS)
        self.assertEqual(fleet.EXECUTABLES, executables)
        self.assertEqual(registry["fallbacks"], GOLDEN_FALLBACKS)
        self.assertEqual(fleet.FALLBACKS, GOLDEN_FALLBACKS)

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

    def test_registry_type_and_legacy_name_guards(self):
        cases = (
            ("invalid billing class", ("doors", "claude", "billing_class"), "invalid"),
            ("non-boolean no_zdr", ("doors", "claude", "no_zdr"), "false"),
            ("boolean priority", ("doors", "claude", "priority"), True),
            ("text priority", ("doors", "claude", "priority"), "1"),
            ("two legacy names", ("providers", "cursor", "legacy_names"), ["agent", "old-agent"]),
            ("legacy name equals provider key", ("providers", "cursor", "legacy_names"), ["codex"]),
        )
        for label, path, value in cases:
            with self.subTest(label=label):
                broken = copy.deepcopy(registry)
                target = broken
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(registry_module.RegistryError):
                    registry_module.validate_registry(broken)

    def test_identity_pattern_and_login_check_validation(self):
        for field, value in (("identity_pattern", "["), ("login_check", [])):
            with self.subTest(field=field):
                broken = copy.deepcopy(registry)
                broken["providers"]["claude"][field] = value
                with self.assertRaises(registry_module.RegistryError):
                    registry_module.validate_registry(broken)

    def test_sandbox_limits_type_guards(self):
        cases = (
            ("prefix without trailing slash", ("write_denied_prefixes", [".agents"])),
            ("absolute prefix", ("write_denied_prefixes", ["/.agents/"])),
            ("parent traversal prefix", ("write_denied_prefixes", [".agents/../x/"])),
            ("non-text prefix", ("write_denied_prefixes", [3])),
            ("prefixes not an array", ("write_denied_prefixes", ".agents/")),
            ("text login value other than unknown", ("login_state_visible", "yes")),
            ("integer login value", ("login_state_visible", 0)),
            ("empty evidence", ("evidence", "  ")),
        )
        for label, (field, value) in cases:
            with self.subTest(label=label):
                broken = copy.deepcopy(registry)
                broken["providers"]["codex"]["sandbox_limits"][field] = value
                with self.assertRaisesRegex(registry_module.RegistryError, "sandbox_limits"):
                    registry_module.validate_registry(broken)

    def test_sandbox_limits_accepts_documented_values(self):
        for login in (True, False, "unknown"):
            with self.subTest(login=login):
                valid = copy.deepcopy(registry)
                valid["providers"]["codex"]["sandbox_limits"]["login_state_visible"] = login
                valid["providers"]["codex"]["sandbox_limits"]["write_denied_prefixes"] = [".agents/", "docs/x/"]
                registry_module.validate_registry(valid)

    def test_canonical_provider_rejects_unknown_name(self):
        self.assertEqual(registry_module.canonical_provider(registry, "cursor"), "cursor")
        self.assertEqual(registry_module.canonical_provider(registry, "agent"), "cursor")
        with self.assertRaisesRegex(registry_module.RegistryError, "unknown provider"):
            registry_module.canonical_provider(registry, "missing")

    def test_persisted_name_cli(self):
        for name in (*registry["providers"], "agent"):
            with self.subTest(name=name):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/harness_registry.py"), "persisted-name", name],
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "agent" if name in ("cursor", "agent") else name)
        unknown = subprocess.run(
            [sys.executable, str(ROOT / "scripts/harness_registry.py"), "persisted-name", "grok"],
            text=True, capture_output=True,
        )
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("ERROR:", unknown.stderr)

    def test_fleet_state_fails_closed_when_registry_is_missing(self):
        with tempfile.TemporaryDirectory(prefix="fleet-state-no-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            scripts = temp_root / "scripts"
            scripts.mkdir()
            for name in ("fleet_state.py", "harness_registry.py"):
                shutil.copy2(ROOT / "scripts" / name, scripts / name)
            fleet = temp_root / "fleet.json"
            shutil.copy2(ROOT / "docs/missions/20261014-2a-foundation/fleet.json", fleet)
            result = subprocess.run(
                ["python3", "scripts/fleet_state.py", "validate-fleet", str(fleet)],
                cwd=temp_root, text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ERROR: registry:", result.stderr)
            self.assertIn("harness-registry.json", result.stderr)


if __name__ == "__main__":
    unittest.main()
