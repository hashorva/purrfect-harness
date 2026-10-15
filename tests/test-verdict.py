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
        schema_path = schema if isinstance(schema, Path) else ROOT / schema
        fixture_path = fixture if isinstance(fixture, Path) else FIXTURES / fixture
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(schema_path), str(fixture_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def run_check_schema(self, schema_path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--check-schema", str(schema_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_refused(self, result, reason_substring=None):
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: verdict:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        if reason_substring is not None:
            self.assertIn(reason_substring, result.stderr)

    def test_good_fixtures_pass(self):
        for schema, fixture in (
            ("schemas/task-plan.schema.json", "good-task-plan.json"),
            ("schemas/review-verdict.schema.json", "good-review-verdict.json"),
        ):
            with self.subTest(fixture=fixture):
                self.assertEqual(self.run_validator(schema, fixture).returncode, 0)

    def test_bad_fixtures_fail_with_specific_reasons(self):
        cases = (
            ("schemas/task-plan.schema.json", "bad-task-plan-missing.json", "required property is missing"),
            ("schemas/task-plan.schema.json", "bad-task-plan-string-field.json", "expected string"),
            ("schemas/task-plan.schema.json", "bad-task-plan-empty-steps.json", "at least 1 item"),
            ("schemas/review-verdict.schema.json", "bad-review-missing.json", "required property is missing"),
            ("schemas/review-verdict.schema.json", "bad-review-empty-evidence.json", "at least 1 item"),
            ("schemas/task-plan.schema.json", "bad-task-plan-type.json", "value is not an allowed enum member"),
            ("schemas/review-verdict.schema.json", "bad-review-type.json", "value is not an allowed enum member"),
        )
        for schema, fixture, reason in cases:
            with self.subTest(fixture=fixture):
                self.assert_refused(self.run_validator(schema, fixture), reason)

    def test_blocked_with_blocking_question_passes(self):
        plan = json.loads((FIXTURES / "good-task-plan.json").read_text())
        plan["verdict"] = "BLOCKED"
        plan["blocking_question"] = "Which seat should run the next task?"
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "plan.json"
            data.write_text(json.dumps(plan))
            result = self.run_validator("schemas/task-plan.schema.json", data)
            self.assertEqual(result.returncode, 0)

    def test_blocked_without_blocking_question_fails(self):
        plan = json.loads((FIXTURES / "good-task-plan.json").read_text())
        plan["verdict"] = "BLOCKED"
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "plan.json"
            data.write_text(json.dumps(plan))
            self.assert_refused(self.run_validator("schemas/task-plan.schema.json", data), "required property is missing")

    def test_non_object_top_level_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "data.json"
            data.write_text("[1]")
            self.assert_refused(
                self.run_validator("schemas/task-plan.schema.json", data),
                "expected object",
            )

    def test_boolean_where_integer_expected_refused(self):
        schema = {
            "type": "object",
            "required": ["count"],
            "properties": {"count": {"type": "integer"}},
            "additionalProperties": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "schema.json"
            data_path = Path(directory) / "data.json"
            schema_path.write_text(json.dumps(schema))
            data_path.write_text(json.dumps({"count": True}))
            self.assert_refused(self.run_validator(schema_path, data_path), "expected integer")

    def test_schema_refusals_in_check_schema_and_data_mode(self):
        base = {"type": "object", "properties": {"name": {"type": "string"}}, "additionalProperties": False}
        cases = (
            (
                "nested properties keyword",
                {
                    **base,
                    "properties": {"name": {"type": "string", "nestedBad": True}},
                },
                "$schema.properties.name: unsupported keyword nestedBad",
            ),
            (
                "nested items keyword",
                {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "$schema.items: unsupported keyword format",
            ),
            (
                "nested if keyword",
                {
                    **base,
                    "if": {"properties": {"x": {"type": "string"}}, "not": {}},
                },
                "$schema.if: unsupported keyword not",
            ),
            (
                "nested then keyword",
                {
                    **base,
                    "if": {"properties": {"x": {"type": "string"}}},
                    "then": {"required": ["y"], "else": {}},
                },
                "$schema.then: unsupported keyword else",
            ),
            (
                "additionalProperties schema object",
                {**base, "additionalProperties": {"type": "string"}},
                "additionalProperties: must be boolean true or false",
            ),
            (
                "non-list enum",
                {"type": "string", "enum": "READY"},
                ".enum: must be a non-empty array",
            ),
            (
                "boolean minItems",
                {"type": "array", "minItems": True, "items": {"type": "string"}},
                ".minItems: must be a non-negative integer",
            ),
            (
                "invalid pattern",
                {"type": "string", "pattern": "("},
                ".pattern: invalid regular expression",
            ),
        )
        for label, schema, reason in cases:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as directory:
                    schema_path = Path(directory) / "schema.json"
                    data_path = Path(directory) / "data.json"
                    schema_path.write_text(json.dumps(schema))
                    data_path.write_text("{}")
                    check = self.run_check_schema(schema_path)
                    self.assert_refused(check, reason)
                    self.assert_refused(self.run_validator(schema_path, data_path), reason)

    def test_top_level_unknown_keyword_refused(self):
        schema = json.loads((ROOT / "schemas/review-verdict.schema.json").read_text())
        schema["unsupportedExample"] = True
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "schema.json"
            data_path = Path(directory) / "data.json"
            schema_path.write_text(json.dumps(schema))
            data_path.write_text("{}")
            self.assert_refused(self.run_check_schema(schema_path), "unsupported keyword")
            self.assert_refused(self.run_validator(schema_path, data_path), "unsupported keyword")

    def test_schema_checks_and_usage_exit(self):
        for schema in ("schemas/task-plan.schema.json", "schemas/review-verdict.schema.json"):
            with self.subTest(schema=schema):
                result = self.run_check_schema(ROOT / schema)
                self.assertEqual(result.returncode, 0)
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, check=False).returncode, 2)


if __name__ == "__main__":
    unittest.main()
