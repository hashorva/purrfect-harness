#!/usr/bin/env python3
"""Regression tests for scripts/ci_status.py (saved gh run list JSON only)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/ci-status"
SHA = "a" * 40
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def run_ci(sha, runs_path):
    return subprocess.run(
        [sys.executable, "scripts/ci_status.py", "--commit", sha, "--runs-json", str(runs_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=ENV,
    )


def tail_json(stdout):
    return json.loads(stdout.strip().splitlines()[-1])


class CiStatus(unittest.TestCase):
    def _case(self, runs, code, result, failing, label="case"):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(runs, tmp)
            path = Path(tmp.name)
        try:
            proc = run_ci(SHA, path)
            self.assertEqual(proc.returncode, code, (label, proc.stdout, proc.stderr))
            self.assertEqual(tail_json(proc.stdout), {"commit": SHA, "result": result, "failing": failing}, label)
        finally:
            path.unlink(missing_ok=True)

    def test_green_fixture(self):
        proc = run_ci(SHA, FIXTURES / "green.json")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(tail_json(proc.stdout), {"commit": SHA, "result": "pass", "failing": []})
        self.assertIn("CI PASS: 2 runs for aaaaaaaaaaaa", proc.stdout)

    def test_red_fixture(self):
        proc = run_ci(SHA, FIXTURES / "red.json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(tail_json(proc.stdout), {"commit": SHA, "result": "fail", "failing": ["macos"]})

    def test_in_progress_fixture(self):
        proc = run_ci(SHA, FIXTURES / "in_progress.json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(tail_json(proc.stdout), {"commit": SHA, "result": "fail", "failing": ["ubuntu"]})

    def test_other_commit_filtered(self):
        other = [{"databaseId": 1, "name": "ubuntu", "workflowName": "CI", "status": "completed",
                  "conclusion": "success", "headSha": "b" * 40}]
        self._case(other, 1, "fail", [], "other")

    def test_empty_runs(self):
        self._case([], 1, "fail", [], "empty")

    def test_bad_inputs_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bad = d / "bad.json"
            bad.write_text("{}")
            green = FIXTURES / "green.json"
            for argv in (
                ["--commit", SHA, "--runs-json", str(bad)],
                ["--commit", "xyz", "--runs-json", str(green)],
                ["--commit", SHA, "--runs-json", str(d / "missing.json")],
            ):
                proc = subprocess.run(
                    [sys.executable, "scripts/ci_status.py", *argv],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    env=ENV,
                )
                self.assertEqual(proc.returncode, 2, argv)


if __name__ == "__main__":
    unittest.main()
