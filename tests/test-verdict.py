#!/usr/bin/env python3
"""Focused contract tests for the dependency-free verdict validator."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_verdict.py"
FIXTURES = ROOT / "tests/fixtures/verdicts"


class VerdictValidatorTests(unittest.TestCase):
    def run_validator(self, schema, fixture):
        return subprocess.run([sys.executable, str(SCRIPT), str(ROOT / schema), str(FIXTURES / fixture)],
                              cwd=ROOT, capture_output=True, text=True, check=False)

    def test_good_fixtures_pass(self):
        for schema, fixture in (("schemas/task-plan.schema.json", "good-task-plan.json"),
                                ("schemas/review-verdict.schema.json", "good-review-verdict.json")):
            with self.subTest(fixture=fixture):
                self.assertEqual(self.run_validator(schema, fixture).returncode, 0)

    def test_bad_fixtures_fail(self):
        cases = (("schemas/task-plan.schema.json", "bad-task-plan-missing.json"),
                 ("schemas/task-plan.schema.json", "bad-task-plan-type.json"),
                 ("schemas/task-plan.schema.json", "bad-task-plan-empty-steps.json"),
                 ("schemas/review-verdict.schema.json", "bad-review-missing.json"),
                 ("schemas/review-verdict.schema.json", "bad-review-type.json"),
                 ("schemas/review-verdict.schema.json", "bad-review-empty-evidence.json"))
        for schema, fixture in cases:
            with self.subTest(fixture=fixture):
                result = self.run_validator(schema, fixture)
                self.assertEqual(result.returncode, 1)
                self.assertIn("ERROR: verdict: $", result.stderr)

    def test_blocked_requires_question_and_schema_rejects_unknown_keyword(self):
        plan = json.loads((FIXTURES / "good-task-plan.json").read_text())
        plan["verdict"] = "BLOCKED"
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "plan.json"
            data.write_text(json.dumps(plan))
            result = subprocess.run([sys.executable, str(SCRIPT), str(ROOT / "schemas/task-plan.schema.json"), str(data)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            schema = json.loads((ROOT / "schemas/review-verdict.schema.json").read_text())
            schema["unsupportedExample"] = True
            schema_path = Path(directory) / "schema.json"
            schema_path.write_text(json.dumps(schema))
            result = subprocess.run([sys.executable, str(SCRIPT), "--check-schema", str(schema_path)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)

    def test_schema_checks_and_usage_exit(self):
        for schema in ("schemas/task-plan.schema.json", "schemas/review-verdict.schema.json"):
            with self.subTest(schema=schema):
                result = subprocess.run([sys.executable, str(SCRIPT), "--check-schema", str(ROOT / schema)],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0)
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, check=False).returncode, 2)


if __name__ == "__main__":
    unittest.main()
