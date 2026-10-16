#!/usr/bin/env python3
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("harness_registry", ROOT / "scripts/harness_registry.py")
registry_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry_module)
registry = registry_module.load_registry()
adapter_spec = importlib.util.spec_from_file_location("execute_provider", ROOT / "scripts/execute_provider.py")
adapter_module = importlib.util.module_from_spec(adapter_spec)
adapter_spec.loader.exec_module(adapter_module)

# Golden copy of the fleet_state constants at commit 1345c67.  This must remain
# independent from the registry so the parity proof is not self-referential.
# The one deliberate change since 1345c67 is agy.premium pro -> argon (F009, T-060).
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
    "codex.economy": ("codex", "luna"), "agy.premium": ("agy", "argon"),
    "agy.economy": ("agy", "flash"), "claude.premium": ("claude", "sonnet"),
    "claude.economy": ("claude", "haiku"),
}
class RegistryTests(unittest.TestCase):
    def test_model_encoding_and_door_provider_validation(self):
        for name, provider in registry["providers"].items():
            with self.subTest(provider=name):
                self.assertIn("model_name_encoding", provider)
                if provider["effort_encoding"] == "flag":
                    self.assertIsNone(provider["model_name_encoding"])
                else:
                    encoding = provider["model_name_encoding"]
                    self.assertTrue(encoding["effort_tokens"])
                    self.assertIsInstance(encoding["families_without_effort"], list)
        for name, door in registry["doors"].items():
            with self.subTest(door=name):
                self.assertIn(door["provider"], registry["providers"])

        invalid = copy.deepcopy(registry)
        del invalid["providers"]["agy"]["model_name_encoding"]
        with self.assertRaisesRegex(registry_module.RegistryError, "model_name_encoding"):
            registry_module.validate_registry(invalid)

    def test_structured_output_is_required_and_validated(self):
        cases = (
            ("missing field", lambda broken: broken["providers"]["claude"].pop("structured_output")),
            ("missing flag", lambda broken: broken["providers"]["claude"]["structured_output"].pop("json_schema_flag")),
            ("invalid flag", lambda broken: broken["providers"]["claude"]["structured_output"].update(json_schema_flag="json-schema")),
            ("missing evidence", lambda broken: broken["providers"]["claude"]["structured_output"].update(evidence="  ")),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                broken = copy.deepcopy(registry)
                mutate(broken)
                with self.assertRaises(registry_module.RegistryError):
                    registry_module.validate_registry(broken)
        self.assertEqual({name: item["structured_output"]["json_schema_flag"]
                          for name, item in registry["providers"].items()},
                         {"claude": "--json-schema", "codex": "--output-schema",
                          "cursor": None, "agy": "--json-schema"})
        invalid = copy.deepcopy(registry)
        invalid["providers"]["claude"]["model_name_encoding"] = {}
        with self.assertRaisesRegex(registry_module.RegistryError, "must be null"):
            registry_module.validate_registry(invalid)
        invalid = copy.deepcopy(registry)
        invalid["doors"]["agy"]["provider"] = "missing"
        with self.assertRaisesRegex(registry_module.RegistryError, "provider key"):
            registry_module.validate_registry(invalid)

    def test_model_name_encoding_round_trips(self):
        cases = (
            ("cursor", "grok-4.7", "grok", "medium", False, "grok-4.7-medium"),
            ("cursor", "grok-4.7", "grok", "xhigh", True, "grok-4.7-xhigh-fast"),
            ("cursor", "composer-2.5", "composer", "high", False, "composer-2.5"),
            ("cursor", "composer-2.5", "composer", "medium", True, "composer-2.5-fast"),
            ("agy", "gemini-3.8-flash", "flash", "high", False, "gemini-3.8-flash-high"),
        )
        for provider, base, family, effort, fast, expected in cases:
            with self.subTest(model=expected):
                encoded = registry_module.encode_model(registry, provider, base, family, effort, fast)
                self.assertEqual(encoded, expected)
                self.assertEqual(registry_module.decode_model(registry, provider, encoded),
                                 {"base": base, "effort": None if family == "composer" else effort, "fast": fast})

    def test_encoded_models_are_accepted_by_provider_adapter(self):
        cases = (
            ("claude", "claude-opus-5-5", "opus", "high", False, "unknown"),
            ("codex", "gpt-6-luna", "luna", "xhigh", False, "unknown"),
            ("cursor", "grok-4.7", "grok", "medium", False, "standard"),
            ("cursor", "grok-4.7", "grok", "xhigh", True, "fast"),
            ("cursor", "composer-2.5", "composer", "high", False, "standard"),
            ("agy", "gemini-3.8-flash", "flash", "high", False, "unknown"),
        )
        for provider, base, family, effort, fast, speed in cases:
            with self.subTest(provider=provider, model=base, effort=effort, fast=fast):
                model = registry_module.encode_model(registry, provider, base, family, effort, fast)
                spec = {"provider": "agent" if provider == "cursor" else provider,
                        "model": model, "effort": effort, "speed": speed,
                        "repo": "/tmp/repo", "prompt": "ok", "provider_contract_version": 6}
                argv, _ = adapter_module.provider_contract(spec)
                self.assertIn(model, argv)

        models = {
            "claude": ("claude-opus-5-5", "opus"),
            "codex": ("gpt-6-luna", "luna"),
            "cursor": ("grok-4.7", "grok"),
            "agy": ("gemini-3.8-flash", "flash"),
        }
        for provider, provider_data in registry["providers"].items():
            base, family = models[provider]
            speeds = provider_data["capabilities"]["speeds"]
            families = [family, *provider_data["model_name_encoding"]["families_without_effort"]] if provider_data["model_name_encoding"] else [family]
            for effort in provider_data["capabilities"]["efforts"]:
                for speed in speeds:
                    for model_family in families:
                        fast = speed == "fast"
                        model = registry_module.encode_model(registry, provider, base, model_family, effort, fast)
                        spec = {"provider": "agent" if provider == "cursor" else provider,
                                "model": model, "effort": effort, "speed": speed,
                                "repo": "/tmp/repo", "prompt": "ok", "provider_contract_version": 6}
                        argv, _ = adapter_module.provider_contract(spec)
                        self.assertIn(model, argv)

    def test_encodings_cli_lists_each_provider(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/harness_registry.py"), "encodings"],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), len(registry["providers"]))
        self.assertIn("cursor effort=model-name fast=model-name tokens=none,minimal,low,medium,high,xhigh,max", lines)
        self.assertIn("agy effort=model-name fast=unsupported tokens=low,medium,high", lines)

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

    def test_encodings_capabilities_and_seat_specs(self):
        cases = (
            ("effort encoding", ("providers", "claude", "effort_encoding"), "effort-flag"),
            ("fast encoding", ("providers", "claude", "fast_encoding"), "fast-flag"),
            ("empty efforts", ("providers", "claude", "capabilities", "efforts"), []),
            ("non-list efforts", ("providers", "claude", "capabilities", "efforts"), "low"),
            ("unsupported effort", ("providers", "claude", "capabilities", "efforts"), ["turbo"]),
            ("unsupported speed", ("providers", "claude", "capabilities", "speeds"), ["warp"]),
            ("empty speeds", ("providers", "claude", "capabilities", "speeds"), []),
            ("duplicate effort", ("providers", "claude", "capabilities", "efforts"), ["low", "low"]),
            ("duplicate speed", ("providers", "claude", "capabilities", "speeds"), ["fast", "fast"]),
            ("seat spec wrong length", ("seat_specs", "brain"), ["claude"]),
            ("seat provider missing", ("seat_specs", "brain"), ["missing", "opus"]),
            ("seat family empty", ("seat_specs", "brain"), ["claude", " "]),
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

    def test_sandbox_limits_architect_followup_regressions(self):
        cases = (
            ("required sandbox_limits", lambda broken: broken["providers"]["codex"].pop("sandbox_limits")),
            ("required sandbox subfield", lambda broken: broken["providers"]["codex"]["sandbox_limits"].pop("evidence")),
            ("empty prefix string", lambda broken: broken["providers"]["codex"]["sandbox_limits"].update(write_denied_prefixes="")),
            ("non-text evidence", lambda broken: broken["providers"]["codex"]["sandbox_limits"].update(evidence=7)),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                broken = copy.deepcopy(registry)
                mutate(broken)
                with self.assertRaises(registry_module.RegistryError):
                    registry_module.validate_registry(broken)

    def test_import_fails_closed_on_broken_registry(self):
        with tempfile.TemporaryDirectory(prefix="fleet-state-broken-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            scripts = temp_root / "scripts"
            scripts.mkdir()
            for name in ("fleet_state.py", "harness_registry.py"):
                shutil.copy2(ROOT / "scripts" / name, scripts / name)
            broken = copy.deepcopy(registry)
            broken["schema_version"] = 99
            (temp_root / "harness-registry.json").write_text(
                json.dumps(broken), encoding="utf-8"
            )
            result = subprocess.run(
                ["python3", "-c", "import sys; sys.path.insert(0, 'scripts'); import fleet_state"],
                cwd=temp_root, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("ERROR: registry:", result.stderr)

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

    def test_already_encoded_bases_are_refused(self):
        cases = (
            ("cursor", "grok-4.7-xhigh", "grok", "medium", False),
            ("agy", "gemini-3.8-flash-high", "flash", "high", False),
            ("cursor", "composer-2.5-fast", "composer", "medium", True),
        )
        for provider, base, family, effort, fast in cases:
            with self.subTest(base=base):
                with self.assertRaisesRegex(registry_module.RegistryError, "already encoded"):
                    registry_module.encode_model(registry, provider, base, family, effort, fast)

    def test_flag_providers_keep_effort_out_of_model_name(self):
        with self.assertRaisesRegex(registry_module.RegistryError, "already encoded"):
            registry_module.encode_model(registry, "claude", "claude-opus-5-5-high", "opus", "high", False)
        self.assertEqual(registry_module.encode_model(registry, "claude", "claude-opus-5-5", "opus", "high", False),
                         "claude-opus-5-5")
        self.assertEqual(registry_module.encode_model(registry, "codex", "gpt-6-luna", "luna", "xhigh", False),
                         "gpt-6-luna")

    def test_flag_and_unsupported_fast_providers_refuse_fast(self):
        for provider, base, family in (("agy", "gemini-3.8-flash", "flash"),
                                       ("claude", "claude-opus-5-5", "opus"),
                                       ("codex", "gpt-6-luna", "luna")):
            with self.subTest(provider=provider):
                with self.assertRaisesRegex(registry_module.RegistryError, "does not support fast"):
                    registry_module.encode_model(registry, provider, base, family, "high", True)

    def test_effort_outside_provider_tokens_is_refused(self):
        with self.assertRaisesRegex(registry_module.RegistryError, "does not support model-name effort 'xhigh'"):
            registry_module.encode_model(registry, "agy", "gemini-3.8-flash", "flash", "xhigh", False)

    def test_effort_token_whitelist_is_enforced_by_validator(self):
        broken = copy.deepcopy(registry)
        broken["providers"]["cursor"]["model_name_encoding"]["effort_tokens"].append("turbo")
        with self.assertRaisesRegex(registry_module.RegistryError, "effort_tokens"):
            registry_module.validate_registry(broken)

    def test_fast_suffix_must_agree_with_fast_encoding(self):
        cases = (
            ("model-name encoding without suffix", ("cursor",), None),
            ("suffix without model-name encoding", ("agy",), "-fast"),
        )
        for label, (provider,), suffix in cases:
            with self.subTest(label=label):
                broken = copy.deepcopy(registry)
                broken["providers"][provider]["model_name_encoding"]["fast_suffix"] = suffix
                with self.assertRaisesRegex(registry_module.RegistryError, "must agree with fast_encoding"):
                    registry_module.validate_registry(broken)

    def test_door_without_provider_raises_registry_error(self):
        broken = copy.deepcopy(registry)
        del broken["doors"]["agy"]["provider"]
        with self.assertRaisesRegex(registry_module.RegistryError, "doors.agy missing required field: provider"):
            registry_module.validate_registry(broken)

    def test_door_provider_values_are_pinned(self):
        expected = {
            "claude": "claude",
            "codex": "codex",
            "cursor-composer": "cursor",
            "cursor-grok": "cursor",
            "agy": "agy",
            "agy-argon": "agy",
        }
        self.assertEqual({name: door["provider"] for name, door in registry["doors"].items()}, expected)

    def test_agy_argon_door_pool_and_seat(self):
        self.assertEqual(registry["seat_specs"]["agy.premium"], ["agy", "argon"])
        self.assertEqual(registry["seat_specs"]["agy.economy"], ["agy", "flash"])
        self.assertEqual(registry["doors"]["agy"]["pool"], "google")
        self.assertEqual(registry["doors"]["agy-argon"], {
            "provider": "agy", "billing_class": "included", "pool": "agy-argon", "no_zdr": False, "priority": 2})
        self.assertEqual(registry["pools"]["agy-argon"]["windows"], ["weekly"])
        self.assertEqual(registry["pools"]["google"]["windows"], "unknown")
        self.assertEqual({door["pool"] for door in registry["doors"].values()}, set(registry["pools"]))
        agy = registry["providers"]["agy"]
        self.assertEqual(agy["fast_encoding"], "unsupported")
        self.assertEqual(agy["capabilities"]["speeds"], ["unknown"])
        for base, family in (("gemini-3.8-flash", "flash"), ("gemini-4-argon", "argon")):
            with self.subTest(base=base):
                self.assertEqual(registry_module.encode_model(registry, "agy", base, family, "high", False), f"{base}-high")
                with self.assertRaisesRegex(registry_module.RegistryError, "does not support fast"):
                    registry_module.encode_model(registry, "agy", base, family, "high", True)

    def test_pool_guards(self):
        windows_message = 'pools.google.windows must be "unknown" or distinct values from 5h, weekly'

        def broken(mutate):
            data = copy.deepcopy(registry)
            mutate(data)
            return data

        def drop_pools(data):
            del data["pools"]

        cases = (
            ("pools missing", drop_pools, "registry missing required field: pools"),
            ("pools empty", lambda d: d.update(pools={}), "registry.pools must be a non-empty object"),
            ("pools list", lambda d: d.update(pools=[]), "registry.pools must be a non-empty object"),
            ("pool string", lambda d: d["pools"].update(google="x"), "pools.google must be an object"),
            ("missing field", lambda d: d["pools"]["google"].pop("evidence"), "pools.google missing required field: evidence"),
            ("extra field", lambda d: d["pools"]["google"].update(extra=1), "pools.google has unknown fields"),
            ("windows daily", lambda d: d["pools"]["google"].update(windows=["daily"]), windows_message),
            ("windows nested", lambda d: d["pools"]["google"].update(windows=[["weekly"]]), windows_message),
            ("windows empty", lambda d: d["pools"]["google"].update(windows=[]), windows_message),
            ("windows duplicate", lambda d: d["pools"]["google"].update(windows=["weekly", "weekly"]), windows_message),
            ("windows string", lambda d: d["pools"]["google"].update(windows="weekly"), windows_message),
            ("evidence blank", lambda d: d["pools"]["google"].update(evidence=" "), "pools.google.evidence must be non-empty text"),
            ("evidence number", lambda d: d["pools"]["google"].update(evidence=7), "pools.google.evidence must be non-empty text"),
        )
        for label, mutate, message in cases:
            with self.subTest(label=label):
                with self.assertRaises(registry_module.RegistryError) as raised:
                    registry_module.validate_registry(broken(mutate))
                self.assertEqual(str(raised.exception), message)
        both = broken(lambda d: d["pools"]["google"].update(windows=["5h", "weekly"]))
        self.assertIs(registry_module.validate_registry(both), both)

    def test_door_ids_are_permanent_and_deprecated_is_boolean(self):
        def broken(mutate):
            data = copy.deepcopy(registry)
            mutate(data)
            return data

        ok = broken(lambda d: d["doors"]["agy"].update(deprecated=True))
        self.assertIs(registry_module.validate_registry(ok), ok)

        for bad in ("yes", 1, None, [], {}):
            with self.subTest(deprecated=bad):
                with self.assertRaisesRegex(registry_module.RegistryError,
                                            r"doors\.agy\.deprecated must be boolean"):
                    registry_module.validate_registry(
                        broken(lambda d, value=bad: d["doors"]["agy"].update(deprecated=value)))

        ledger_path = ROOT / "docs/missions/ledger.jsonl"
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines)
        first_door = None
        for line in lines:
            door = json.loads(line)["door"]
            if door == "unknown":
                continue
            self.assertIn(door, registry["doors"])
            if first_door is None:
                first_door = door
        self.assertIsNotNone(first_door)
        renamed = copy.deepcopy(registry)
        renamed["doors"][f"renamed-{first_door}"] = renamed["doors"].pop(first_door)
        self.assertNotIn(first_door, renamed["doors"])

    def test_decode_refuses_empty_base(self):
        for model in ("", "-high", "-fast"):
            with self.subTest(model=model):
                with self.assertRaisesRegex(registry_module.RegistryError, "model"):
                    registry_module.decode_model(registry, "cursor", model)


if __name__ == "__main__":
    unittest.main()
