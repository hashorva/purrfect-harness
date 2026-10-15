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
pathlib.Path('.tasks/invoked.json').write_text(json.dumps({'provider': pathlib.Path(sys.argv[0]).name}))
raise SystemExit(0)
'''
        (bin_dir / "codex").write_text(provider_stub)
        (bin_dir / "codex").chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.parent)

    def invoke(self, args):
        env = dict(os.environ, PATH=f"{self.root / 'bin'}:{os.environ['PATH']}",
                   PYTHONDONTWRITEBYTECODE="1", SPAWN_WORKER_TIMEOUT_SECS="0")
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

    def write_canonical(self, path, receipt):
        path.chmod(0o600)
        path.write_bytes(canonical_bytes(receipt))
        path.chmod(0o400)

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
