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
TASKS = FIXTURES / "tasks"


def fixture_files():
    return sorted(p for p in FIXTURES.rglob("*") if p.is_file())


def snapshot():
    return {str(p): p.read_bytes() for p in fixture_files()}


class UsageReportTest(unittest.TestCase):
    def test_frozen_fixtures(self):
        before = snapshot()
        base = [
            sys.executable,
            str(SCRIPT),
            "--projects",
            str(FIXTURES / "projects"),
            "--tasks-dir",
            str(TASKS),
            "--repo",
            "/fixture/repo",
            "--since",
            "2026-10-19",
            "--until",
            "2026-10-20",
        ]
        run = subprocess.run(base + ["--json"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        data = json.loads(run.stdout)
        rows = {
            (r["class"], r["model"]): (
                r["input_tokens"],
                r["output_tokens"],
                r["cache_creation_input_tokens"],
                r["cache_read_input_tokens"],
                r["total"],
                r["messages"],
            )
            for r in data["rows"]
        }
        self.assertEqual(
            rows,
            {
                ("front_desk", "claude-opus"): (16, 11, 100, 1000, 1127, 6),
                ("front_desk", "claude-haiku"): (1, 1, 0, 0, 2, 1),
                ("harness", "claude-opus"): (7, 3, 0, 0, 10, 1),
                ("harness", "claude-sonnet"): (2, 2, 0, 0, 4, 1),
                ("other", "claude-opus"): (50, 50, 0, 0, 100, 1),
            },
        )
        self.assertEqual(
            data["front_desk"],
            {
                "turns": 6,
                "polling_calls": 4,
                "accepted_tasks": 2,
                "tokens_per_accepted_task": 564,
            },
        )
        table = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(table.returncode, 0, table.stderr)
        self.assertIn("| front_desk | claude-opus | 16 | 11 | 100 | 1000 | 1127 | 6 |", table.stdout)
        self.assertIn(
            "Front Desk: 6 turns, 4 polling calls, 2 accepted tasks, 564 tokens per accepted task",
            table.stdout,
        )
        bad = subprocess.run(base + ["--since", "yesterday"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "HOME": tmp, "PYTHONDONTWRITEBYTECODE": "1"}
            empty = subprocess.run(
                [sys.executable, str(SCRIPT), "--tasks-dir", str(TASKS), "--repo", "/fixture/repo", "--json"],
                capture_output=True,
                text=True,
                env=env,
                cwd=tmp,
            )
            self.assertEqual(empty.returncode, 0, empty.stderr)
            self.assertEqual(json.loads(empty.stdout)["rows"], [])
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
