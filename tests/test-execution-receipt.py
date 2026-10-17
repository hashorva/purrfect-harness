#!/usr/bin/env python3
"""ExecutionReceipt v1 compatibility and v2 observation block validation (F003)."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import execution_receipt
from execution_receipt import ReceiptError, canonical_bytes, load_receipt

SCHEMA_PATH = ROOT / "schemas" / "execution-receipt.schema.json"

ALL_UNKNOWN = {
    "observed_model": {"value": None, "source": "unknown"},
    "usage": {
        "input": {"value": None, "source": "unknown"},
        "output": {"value": None, "source": "unknown"},
        "cache": {"value": None, "source": "unknown"},
        "reasoning": {"value": None, "source": "unknown"},
    },
    "fast_state": {"value": None, "source": "unknown"},
}


def schema_drift(schema):
    """Return how the JSON Schema disagrees with execution_receipt.py's field lists (empty when they agree)."""
    drift = []
    body = schema["$defs"]["receiptBody"]
    if set(body["properties"]) != execution_receipt.FIELDS:
        drift.append("receiptBody.properties != FIELDS")
    if len(body["required"]) != len(set(body["required"])) or set(body["required"]) != execution_receipt.FIELDS_V1:
        drift.append("receiptBody.required != FIELDS_V1")
    observation = schema["$defs"]["observation"]
    if set(observation["required"]) != set(execution_receipt.OBSERVATION_FIELDS):
        drift.append("observation.required != OBSERVATION_FIELDS")
    if set(observation["properties"]) != set(execution_receipt.OBSERVATION_FIELDS):
        drift.append("observation.properties != OBSERVATION_FIELDS")
    usage = observation["properties"]["usage"]
    if set(usage["properties"]) != set(execution_receipt.USAGE_FIELDS):
        drift.append("usage.properties != USAGE_FIELDS")
    return drift


class ExecutionReceiptObservation(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp())
        self.root = self.parent / "repo"
        self.root.mkdir()
        (self.root / "scripts").mkdir()
        for name in (
            "execution_spec.py", "execution_receipt.py", "execution_runner.py",
            "execute_provider.py", "observe_output.py", "fleet_state.py", "dispatch_policy.py",
            "harness_registry.py", "spawn-worker.sh", "spawn-brain.sh",
        ):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        shutil.copy2(ROOT / "harness-registry.json", self.root / "harness-registry.json")
        task = self.root / "docs/missions/fixture/tasks/T-001.md"
        task.parent.mkdir(parents=True)
        mission = task.parent.parent
        task.write_text(
            "---\ntask_id: T-001\nfeature: F001\n---\n# Task\n\n"
            "## Files you MAY touch\n- `allowed.txt`\n\n"
            "## Verification commands\n\n- `[\"true\"]`\n"
        )
        (mission / "GOAL.md").write_text("---\nstatus: in-progress\n---\n# Goal\n")
        (mission / "features.json").write_text(
            json.dumps({"goal": "fixture", "features": [
                {"id": "F001", "description": "one", "bootstrap": False, "steps": [], "passes": False, "priority": 1},
            ]}, indent=2) + "\n"
        )
        fleet = mission / "fleet.json"
        fleet.write_text(json.dumps({
            "schema_version": 1,
            "mission": {"path": "docs/missions/fixture"},
            "inventory": {"sha256": "0" * 64, "probed_at": "2026-08-21T00:00:00Z"},
            "approval": {"status": "approved", "approved_by": "human", "approved_at": "2026-08-21T00:00:00Z"},
            "seats": {
                "codex.economy": {
                    "provider": "codex", "model": "model", "family": "luna",
                    "effort": "medium", "speed": "unknown", "health": "healthy",
                    "source": "observed",
                    "capabilities": {"efforts": ["low", "medium", "high", "xhigh"], "speeds": ["unknown"]},
                },
            },
        }, sort_keys=True, separators=(",", ":")) + "\n"
        )
        fleet.chmod(0o444)
        (self.root / ".gitignore").write_text(".tasks/\nbin/\n")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "t@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "fixture"], check=True)
        self.physical_root = subprocess.run(
            ["bash", "-c", "pwd -P"], cwd=self.root, check=True, text=True, capture_output=True,
        ).stdout.strip()
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        provider_stub = '''#!/usr/bin/env python3
import json, os, pathlib, sys
spec = json.loads(next(pathlib.Path('.tasks/specs').glob('*.json')).read_text())
action = os.environ.get('PROVIDER_ACTION')
if action == 'protected-volatile':
    cj = pathlib.Path.home() / '.claude.json'
    cj.write_text(json.dumps({'numStartups': 2, 'caches': {'gate': False}, 'projects': {'/tmp/p': {'lastCost': 0.9, 'mcpServers': {}}, '/tmp/q': {'history': ['hi']}}}))
    (pathlib.Path.home() / '.claude/sessions').mkdir(parents=True, exist_ok=True)
    (pathlib.Path.home() / '.claude/sessions/67107.abc.key').write_text('session')
    p = pathlib.Path.home() / '.claude/plugins/synced/p/.in_use'
    p.mkdir(parents=True, exist_ok=True); (p / '67107').write_text('active')
    p = pathlib.Path.home() / '.claude/projects/p'; p.mkdir(parents=True, exist_ok=True)
    (p / 'transcript.jsonl').write_text('{}\\n')
if action == 'protected-tamper':
    (pathlib.Path.home() / '.claude/settings.json').write_text('{}')
    (pathlib.Path('.tasks/specs') / (spec['run_id'] + '.protected')).unlink()
pathlib.Path('.tasks/invoked.json').write_text(json.dumps({'provider': pathlib.Path(sys.argv[0]).name}))
raise SystemExit(0)
'''
        (bin_dir / "codex").write_text(provider_stub)
        (bin_dir / "codex").chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.parent)

    def invoke(self, args, extra_env=None):
        env = dict(os.environ, PATH=f"{self.root / 'bin'}:{os.environ['PATH']}",
                   PYTHONDONTWRITEBYTECODE="1", SPAWN_WORKER_TIMEOUT_SECS="0")
        if extra_env:
            env.update(extra_env)
        return subprocess.run(args, cwd=self.root, env=env, text=True, capture_output=True)

    def spawn_receipt(self):
        result = self.invoke([
            "bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
            "--model", "model", "--feature", "F001",
        ])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        receipts = list((self.root / ".tasks/receipts").glob("*.json"))
        self.assertEqual(len(receipts), 1)
        path = receipts[0]
        receipt = json.loads(path.read_text())
        return path, receipt

    def test_protected_snapshot_in_memory_baseline_allowlist_and_tamper_detection(self):
        home = self.parent / "fake-home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude.json").write_text(json.dumps({"numStartups": 1, "caches": {"gate": True}, "projects": {"/tmp/p": {"lastCost": 0.1, "mcpServers": {}}}}))
        args = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                "--model", "model", "--feature", "F001"]
        for action, expected in (
            ("protected-volatile", ("pass", [])),
            ("protected-tamper", ("fail", None)),
        ):
            with self.subTest(action=action):
                result = self.invoke(args, {"HOME": str(home), "PROVIDER_ACTION": action})
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                receipt_path = next((self.root / ".tasks/receipts").glob("*.json"))
                receipt = json.loads(receipt_path.read_text())
                self.assertEqual(receipt["scope"]["result"], expected[0])
                if expected[1] is not None:
                    self.assertEqual(receipt["scope"]["violations"], expected[1])
                else:
                    run_id = receipt["run_id"]
                    self.assertIn(f"<protected:.tasks/specs/{run_id}.protected>", receipt["scope"]["violations"])
                    self.assertIn("<protected:~/.claude/settings.json>", receipt["scope"]["violations"])
                shutil.rmtree(self.root / ".tasks")

    def test_claude_json_protects_only_mcp_and_hooks_configuration(self):
        home = self.parent / "claude-json-home"
        home.mkdir()
        path = home / ".claude.json"
        spec = {"repo": str(self.root), "run_id": "claude-json-test"}

        def check(before_value, after_value=None, *, before_raw=None, after_raw=None, symlink=False):
            protected_file = execution_receipt._protected_snapshot_file(spec, create=True)
            if protected_file.exists():
                protected_file.chmod(0o600)
                protected_file.unlink()
            if path.is_symlink() or path.exists():
                path.unlink()
            target = home / "target.json"
            if target.exists():
                target.unlink()
            if before_raw is not None:
                target.write_bytes(before_raw)
            else:
                target.write_text(json.dumps(before_value))
            if symlink:
                path.symlink_to(target)
            else:
                if before_raw is not None:
                    path.write_bytes(before_raw)
                else:
                    path.write_text(json.dumps(before_value))
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                baseline = execution_receipt.protected_snapshot(str(self.root))
                protected_file.write_bytes(canonical_bytes({"before": baseline}))
                if after_raw is not None:
                    (target if symlink else path).write_bytes(after_raw)
                elif after_value is not None:
                    (target if symlink else path).write_text(json.dumps(after_value))
                violations = execution_receipt.protected_violations(spec, protected_before=baseline, finalize=True)
            return {"result": "pass" if not violations else "fail", "violations": violations}

        base = {"numStartups": 1, "caches": {"gate": True}, "projects": {"X": {"lastCost": 1, "mcpServers": {}}}}
        changed_runtime = {"numStartups": 9, "caches": {"gate": False}, "projects": {"X": {"lastCost": 8}, "Y": {"history": ["x"]}}}
        self.assertEqual(check(base, changed_runtime), {"result": "pass", "violations": []})
        top = {"numStartups": 1, "mcpServers": {"s": {"command": "a"}}}
        self.assertEqual(check(top, {"mcpServers": {"s": {"command": "a"}, "new": {"command": "b"}}}), {"result": "fail", "violations": ["<protected:~/.claude.json>"]})
        proj = {"projects": {"X": {"mcpServers": {}}}}
        self.assertEqual(check(proj, {"projects": {"X": {"mcpServers": {"p": {"command": "c"}}}}}), {"result": "fail", "violations": ["<protected:~/.claude.json>"]})
        hooks = {"projects": {"X": {}}}
        for value in ({"hooks": {"PreToolUse": ["x"]}}, {"projects": {"X": {"hooks": {"Stop": ["x"]}}}}):
            self.assertEqual(check(hooks, value), {"result": "fail", "violations": ["<protected:~/.claude.json>"]})
        invalid = b"{invalid"
        self.assertEqual(check(None, before_raw=invalid, after_raw=invalid), {"result": "pass", "violations": []})
        self.assertEqual(check(None, before_raw=invalid, after_raw=b"{other"), {"result": "fail", "violations": ["<protected:~/.claude.json>"]})
        self.assertEqual(check({}, after_raw=invalid), {"result": "fail", "violations": ["<protected:~/.claude.json>"]})
        self.assertEqual(check(None, before_raw=invalid, after_raw=b"{}"), {"result": "fail", "violations": ["<protected:~/.claude.json>"]})
        self.assertEqual(check(base, {"numStartups": 2, "projects": {"X": {}}}, symlink=True), {"result": "pass", "violations": []})
        self.assertEqual(check(base, {"mcpServers": {"s": {"command": "a"}}}, symlink=True), {"result": "fail", "violations": ["<protected:~/.claude.json>"]})

    def write_canonical(self, path, receipt):
        path.chmod(0o600)
        path.write_bytes(canonical_bytes(receipt))
        path.chmod(0o400)

    def test_symlinked_claude_and_projects_roots_record_link_target_only(self):
        home = self.parent / "home"
        claude = self.parent / "dotfiles/claude"
        projects = self.parent / "dotfiles/projects"
        for path in (claude / "sessions", claude / "plugins/synced/x/.in_use",
                     claude / "commands", projects / "p/memory"):
            path.mkdir(parents=True, exist_ok=True)
        (claude / "settings.json").write_text("{}")
        (projects / "p/memory/notes.md").write_text("notes")
        (claude / "projects").symlink_to(projects)
        home.mkdir()
        (home / ".claude").symlink_to(claude)
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            baseline = execution_receipt.protected_snapshot(self.root)
            for path, label in ((home / ".claude", "~/.claude"),
                                 (claude / "projects", "~/.claude/projects")):
                link_hash = hashlib.sha256(os.readlink(path).encode("utf-8", "surrogateescape")).hexdigest()
                expected = hashlib.sha256(f"symlink:{link_hash}".encode("ascii")).hexdigest()
                self.assertEqual(baseline[label], expected)
            (home / ".claude/sessions/1.key").write_text("volatile")
            (home / ".claude/plugins/synced/x/.in_use/1").write_text("volatile")
            (home / ".claude/projects/p/transcript.jsonl").write_text("{}\n")
            self.assertEqual(execution_receipt.protected_snapshot(self.root), baseline)
            for rel, expected in (
                (".claude/settings.json", "<protected:~/.claude/settings.json>"),
                (".claude/commands/c.md", "<protected:~/.claude/commands/c.md>"),
                (".claude/projects/p/memory/notes.md", "<protected:~/.claude/projects/p/memory/notes.md>"),
            ):
                target = home / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("changed")
                after = execution_receipt.protected_snapshot(self.root)
                self.assertIn(expected, [f"<protected:{key}>" for key in set(baseline) | set(after)
                                         if baseline.get(key) != after.get(key)])
                target.write_text("{}" if rel.endswith("settings.json") else "notes")
            old_target = os.readlink(home / ".claude")
            (home / ".claude").unlink()
            (home / ".claude").symlink_to(self.parent / "dotfiles/other-claude")
            after = execution_receipt.protected_snapshot(self.root)
            self.assertNotEqual(baseline["~/.claude"], after["~/.claude"])
            (home / ".claude").unlink()
            (home / ".claude").symlink_to(old_target)
            (claude / "projects").unlink()
            (claude / "projects").symlink_to(self.parent / "dotfiles/other-projects")
            after = execution_receipt.protected_snapshot(self.root)
            self.assertNotEqual(baseline["~/.claude/projects"], after["~/.claude/projects"])

    def test_untracked_scope_ignores_local_gitignore_and_flags_ignore_and_stdlib_shadowing(self):
        base = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                              check=True, text=True, capture_output=True).stdout.strip()
        (self.root / "scripts/.gitignore").write_text(".gitignore\njson.py\n")
        (self.root / "scripts/json.py").write_text("x = 1\n")
        dirty = execution_receipt.dirty_paths(self.root, base_commit=base)
        self.assertIn("scripts/.gitignore", dirty)
        self.assertIn("scripts/json.py", dirty)
        for path in (".gitignore", "scripts/.gitignore", "scripts/json.py", "scripts/os.py",
                     "scripts/sys.py", "scripts/re.py", "tests/json.py"):
            self.assertFalse(execution_receipt.in_scope(path, ["scripts/**", "tests/**", ".gitignore"]))
        (self.root / ".gitignore").write_text("planted.txt\n")
        (self.root / "planted.txt").write_text("visible")
        self.assertIn("planted.txt", execution_receipt.dirty_paths(self.root, base_commit=base))
        self.assertIn(".gitignore", execution_receipt.dirty_paths(self.root, base_commit=base))
        with mock.patch.dict(os.environ, {"HOME": str(self.parent / "fake-home")}):
            (self.root / ".git/info/exclude").write_text("hidden-info\n")
            config_home = self.parent / "fake-home/.config/git"
            config_home.mkdir(parents=True)
            (config_home / "ignore").write_text("hidden-global\n")
            (config_home / "attributes").write_text("*.x test\n")
            subprocess.run(["git", "-C", str(self.root), "config", "--local", "core.excludesFile",
                            str(config_home / "ignore")], check=True)
            baseline = execution_receipt.protected_snapshot(self.root)
            (self.root / ".git/info/exclude").write_text("changed\n")
            (config_home / "ignore").write_text("changed-global\n")
            (config_home / "attributes").write_text("*.x changed\n")
            after = execution_receipt.protected_snapshot(self.root)
            changed = {key for key in set(baseline) | set(after) if baseline.get(key) != after.get(key)}
            violations = {f"<protected:{key}>" for key in changed}
            self.assertIn("<protected:.git/info/exclude>", violations)
            self.assertIn("<protected:~/.config/git/ignore>", violations)
            self.assertIn("<protected:~/.config/git/attributes>", violations)
            self.assertIn("<protected:core.excludesFile>", violations)
            (self.root / "hidden-info").write_text("caught")
            (self.root / "hidden-global").write_text("caught")
            dirty = execution_receipt.dirty_paths(self.root, base_commit=base)
            self.assertIn("hidden-info", dirty)
            self.assertIn("hidden-global", dirty)

    def test_v1_fixture_validates(self):
        path, receipt = self.spawn_receipt()
        legacy = dict(receipt)
        legacy["schema_version"] = 1
        legacy.pop("observation", None)
        self.write_canonical(path, legacy)
        load_receipt(path)

    def test_v2_all_unknown_validates(self):
        path, receipt = self.spawn_receipt()
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["observation"], ALL_UNKNOWN)
        load_receipt(path)

    def test_observation_negatives_rejected(self):
        path, receipt = self.spawn_receipt()
        base_obs = copy.deepcopy(receipt["observation"])
        cases = [
            ("bad source", lambda o: o["observed_model"].update({"source": "guessed"})),
            ("value with source unknown", lambda o: o["usage"]["input"].update({"value": 1})),
            ("observed with value null", lambda o: o["fast_state"].update({"source": "observed", "value": None})),
            ("negative usage", lambda o: o["usage"]["output"].update({"source": "observed", "value": -1})),
            ("extra key", lambda o: o.__setitem__("extra", {"value": None, "source": "unknown"})),
        ]
        for label, mutate in cases:
            bad = copy.deepcopy(receipt)
            mutate(bad["observation"])
            self.write_canonical(path, bad)
            with self.assertRaises(ReceiptError, msg=label):
                load_receipt(path)
            self.write_canonical(path, receipt)
        self.assertEqual(receipt["observation"], base_obs)

    def assert_rejected(self, path, receipt, label):
        self.write_canonical(path, receipt)
        with self.assertRaises(ReceiptError, msg=label):
            load_receipt(path)

    def test_schema_agrees_with_code(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        self.assertEqual(schema_drift(schema), [])

    def test_schema_and_code_drift_is_detected(self):
        base = json.loads(SCHEMA_PATH.read_text())
        schema_mutations = {
            "receipt property removed": lambda s: s["$defs"]["receiptBody"]["properties"].pop("observation"),
            "receipt property added": lambda s: s["$defs"]["receiptBody"]["properties"].update({"bogus": {"type": "string"}}),
            "required field removed": lambda s: s["$defs"]["receiptBody"]["required"].remove("scope"),
            "required field added": lambda s: s["$defs"]["receiptBody"]["required"].append("observation"),
            "observation property added": lambda s: s["$defs"]["observation"]["properties"].update({"extra": {}}),
            "usage property removed": lambda s: s["$defs"]["observation"]["properties"]["usage"]["properties"].pop("reasoning"),
        }
        for label, mutate in schema_mutations.items():
            mutated = copy.deepcopy(base)
            mutate(mutated)
            self.assertTrue(schema_drift(mutated), msg=f"schema drift not detected: {label}")
        for name, mutated in (
            ("FIELDS", execution_receipt.FIELDS | {"bogus"}),
            ("FIELDS_V1", execution_receipt.FIELDS_V1 - {"scope"}),
            ("OBSERVATION_FIELDS", tuple(execution_receipt.OBSERVATION_FIELDS) + ("extra",)),
            ("USAGE_FIELDS", tuple(execution_receipt.USAGE_FIELDS)[:-1]),
        ):
            with mock.patch.object(execution_receipt, name, mutated):
                self.assertTrue(schema_drift(base), msg=f"code drift not detected: {name}")

    def test_guessed_source_with_value_rejected(self):
        path, receipt = self.spawn_receipt()
        bad = copy.deepcopy(receipt)
        bad["observation"]["observed_model"] = {"source": "guessed", "value": "x"}
        self.assert_rejected(path, bad, "guessed source")

    def test_v1_receipt_with_observation_rejected(self):
        path, receipt = self.spawn_receipt()
        legacy = copy.deepcopy(receipt)
        legacy["schema_version"] = 1
        self.assert_rejected(path, legacy, "v1 with observation")

    def test_true_usage_count_rejected(self):
        path, receipt = self.spawn_receipt()
        bad = copy.deepcopy(receipt)
        bad["observation"]["usage"]["input"] = {"value": True, "source": "observed"}
        self.assert_rejected(path, bad, "boolean usage count")

    def test_numeric_model_rejected(self):
        path, receipt = self.spawn_receipt()
        bad = copy.deepcopy(receipt)
        bad["model"] = 7
        self.assert_rejected(path, bad, "numeric model")

    def test_numeric_observed_model_rejected(self):
        path, receipt = self.spawn_receipt()
        bad = copy.deepcopy(receipt)
        bad["observation"]["observed_model"] = {"source": "observed", "value": 7}
        self.write_canonical(path, bad)
        with self.assertRaisesRegex(ReceiptError, r"observation\.observed_model must be non-empty text"):
            load_receipt(path)

    def test_v2_without_observation_rejected(self):
        path, receipt = self.spawn_receipt()
        bad = copy.deepcopy(receipt)
        bad.pop("observation")
        self.assert_rejected(path, bad, "v2 without observation")


if __name__ == "__main__":
    unittest.main()
