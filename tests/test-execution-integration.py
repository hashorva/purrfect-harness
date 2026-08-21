#!/usr/bin/env python3
"""Mounted real-wrapper contracts for immutable execution specs and receipts."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WrapperIntegration(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / "repo"
        self.root.mkdir(parents=True)
        for name in ("execution_spec.py", "execute_provider.py", "spawn-worker.sh", "spawn-brain.sh", "write-receipt.sh"):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name) if (self.root / "scripts").exists() else None
        (self.root / "scripts").mkdir(exist_ok=True)
        for name in ("execution_spec.py", "execute_provider.py", "spawn-worker.sh", "spawn-brain.sh", "write-receipt.sh"):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        task = self.root / "docs/missions/fixture/tasks/T-001.md"
        task.parent.mkdir(parents=True)
        task.write_text("task\n")
        task.parent.parent.joinpath("GOAL.md").write_text("goal\n")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.root, check=True)
        self.bin = self.root / "bin"; self.bin.mkdir()
        for provider in ("codex", "claude", "agent", "agy"):
            p = self.bin / provider
            p.write_text('#!/usr/bin/env bash\nset -eu\nfind .tasks/specs -name "*.json" | grep -q .\nprintf "%s\\n" "$*" > .tasks/invoked\n')
            p.chmod(0o755)

    def tearDown(self): shutil.rmtree(self.root.parent)

    def invoke(self, args):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(args, cwd=self.root, env=env, text=True, capture_output=True)

    def assert_linked(self):
        specs = list((self.root / ".tasks/specs").glob("*.json")); self.assertEqual(len(specs), 1)
        receipts = [p for p in (self.root / ".tasks/receipts").glob("*.json") if not p.name.startswith("latest-")]
        self.assertEqual(len(receipts), 1)
        spec = json.loads(specs[0].read_text()); receipt = json.loads(receipts[0].read_text())
        self.assertEqual(receipt["run_id"], spec["run_id"])
        self.assertEqual(receipt["observed_configuration"], {"model":"unknown","effort":"unknown","speed":"unknown"})
        self.assertTrue((self.root / ".tasks/invoked").exists())

    def test_every_provider_through_real_wrappers(self):
        for provider in ("codex", "claude", "agent", "agy"):
            with self.subTest(role="worker", provider=provider):
                result = self.invoke(["bash", "scripts/spawn-worker.sh", provider, "docs/missions/fixture/tasks/T-001.md", "--model", "test", "--feature", "F001"])
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout); self.assert_linked()
                shutil.rmtree(self.root / ".tasks")
            with self.subTest(role="brain", provider=provider):
                result = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review", "--provider", provider, "--model", "test"])
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout); self.assert_linked()
                shutil.rmtree(self.root / ".tasks")

    def test_unsupported_config_never_reaches_sentinel(self):
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--model", "test", "--feature", "F001", "--speed", "fast"])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / ".tasks/invoked").exists())


if __name__ == "__main__": unittest.main()
