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
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from execution_receipt import ReceiptError, canonical_bytes, load_receipt

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


if __name__ == "__main__":
    unittest.main()
