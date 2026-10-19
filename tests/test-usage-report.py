import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/usage-report"
SCRIPT = ROOT / "scripts/usage_report.py"


class UsageReportTest(unittest.TestCase):
    def test_harness_runs_ranked_by_role_step_seat_and_prompt_version(self):
        tasks = next(FIXTURES.rglob("events.jsonl")).parent
        base = [
            sys.executable,
            str(SCRIPT),
            "--projects",
            str(FIXTURES / "projects"),
            "--tasks-dir",
            str(tasks),
            "--ledger-dir",
            str(FIXTURES / "ledger"),
            "--repo",
            "/fixture/repo",
            "--json",
        ]
        run = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        harness = json.loads(run.stdout)["harness"]

        def entry(key, runs, total, without_cache, unknown_runs):
            return {"key": key, "runs": runs, "total": total, "without_cache": without_cache, "unknown_runs": unknown_runs}

        expected = {
            "by_role": [
                entry("worker", 1, 3000, 300, 0),
                entry("plan", 1, 1000, 100, 0),
                entry("untagged", 1, 0, 0, 1),
            ],
            "by_step": [
                entry("T-001", 2, 3000, 300, 1),
                entry("plan", 1, 1000, 100, 0),
            ],
            "by_seat": [
                entry("codex.economy", 1, 3000, 300, 0),
                entry("claude", 1, 1000, 100, 0),
                entry("cursor.economy", 1, 0, 0, 1),
            ],
            "by_prompt_version": [
                entry("scripts/spawn-worker.sh:bbbbbbbbbbbb", 1, 3000, 300, 0),
                entry("scripts/brain_prompt.py:aaaaaaaaaaaa", 1, 1000, 100, 0),
                entry("unknown", 1, 0, 0, 1),
            ],
        }
        self.assertEqual(harness, expected)
        future = subprocess.run(base + ["--since", "2099-01-01"], capture_output=True, text=True)
        self.assertEqual(future.returncode, 0, future.stderr)
        empty = {"by_role": [], "by_step": [], "by_seat": [], "by_prompt_version": []}
        self.assertEqual(json.loads(future.stdout)["harness"], empty)
        table = subprocess.run(base[:-1], capture_output=True, text=True)
        self.assertEqual(table.returncode, 0, table.stderr)
        self.assertIn("| role | runs | total | without cache | unknown |", table.stdout)
        self.assertIn("| worker | 1 | 3000 | 300 | 0 |", table.stdout)


if __name__ == "__main__":
    unittest.main()
