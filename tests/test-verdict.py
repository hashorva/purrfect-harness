#!/usr/bin/env python3
"""Focused contract tests for the dependency-free verdict validator."""
import json
import subprocess
import sys
import tempfile
import time
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

    def run_after_run(self, provider, schema, fixture):
        fixture_path = fixture if isinstance(fixture, Path) else FIXTURES / fixture
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--after-run", provider,
             str(ROOT / schema), str(fixture_path)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )

    def run_after_run_text(self, output_text, provider="cursor", schema="schemas/task-plan.schema.json"):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.txt"
            output.write_text(output_text, encoding="utf-8")
            return self.run_after_run(provider, schema, output)

    @staticmethod
    def plan_text(valid=True):
        plan = json.loads((FIXTURES / "good-task-plan.json").read_text(encoding="utf-8"))
        if not valid:
            plan["tasks"] = []
        return json.dumps(plan)

    @staticmethod
    def envelope(result_text):
        return json.dumps({"type": "result", "result": result_text})

    def test_after_run_extracts_and_validates_envelope_for_provider_without_flag(self):
        result = self.run_after_run("cursor", "schemas/task-plan.schema.json", "cursor-envelope.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=after-run", result.stdout)
        bad = self.run_after_run("cursor", "schemas/task-plan.schema.json", "cursor-envelope-bad.json")
        self.assert_refused(bad, "at least 1 item")

    def test_after_run_with_flag_uses_plain_validation(self):
        result = self.run_after_run("claude", "schemas/task-plan.schema.json", "good-task-plan.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=flag", result.stdout)

    def test_bare_verdicts_without_envelope_are_accepted(self):
        result = self.run_after_run("cursor", "schemas/task-plan.schema.json", "good-task-plan.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=after-run", result.stdout)
        review = self.run_after_run(
            "cursor", "schemas/review-verdict.schema.json", "good-review-verdict.json")
        self.assertEqual(review.returncode, 0, review.stderr)
        self.assertIn("mode=after-run", review.stdout)

    def test_prose_before_verdict_is_accepted(self):
        result = self.run_after_run_text(self.envelope("Here is the plan:\n" + self.plan_text()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=after-run", result.stdout)

    def test_fenced_verdict_is_accepted(self):
        fenced = "Plan:\n```json\n" + self.plan_text() + "\n```\n"
        result = self.run_after_run_text(self.envelope(fenced))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=after-run", result.stdout)

    def test_first_valid_last_invalid_is_refused(self):
        output = self.plan_text() + "\n" + self.plan_text(valid=False)
        self.assert_refused(self.run_after_run_text(output), "at least 1 item")

    def test_first_invalid_last_valid_is_accepted(self):
        output = self.plan_text(valid=False) + "\n" + self.plan_text()
        result = self.run_after_run_text(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=after-run", result.stdout)

    def test_earlier_event_with_valid_plan_is_not_a_fallback(self):
        earlier = json.dumps({"type": "tool_result", "text": self.plan_text()})
        output = earlier + "\n" + self.envelope("I could not produce a plan.")
        self.assert_refused(self.run_after_run_text(output), "no JSON object")

    def test_final_text_without_json_is_refused(self):
        self.assert_refused(self.run_after_run_text(self.envelope("no plan")), "no JSON object")

    def test_stray_brackets_before_verdict_do_not_hide_it(self):
        prefixes = ("Step [1 of 2: ", "Note: {unclosed ", "stray } and ] ")
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                result = self.run_after_run_text(self.envelope(prefix + self.plan_text()))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_deep_nesting_refused_cleanly_in_flag_and_data_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            deep_path = Path(directory) / "deep.json"
            deep_path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
            flagged = self.run_after_run(
                "claude", "schemas/task-plan.schema.json", deep_path)
            data = self.run_validator("schemas/task-plan.schema.json", deep_path)
        self.assert_refused(flagged)
        self.assert_refused(data)

    def test_deep_nesting_is_refused_cleanly(self):
        deep = '{"a":' * 5000 + "1" + "}" * 5000
        self.assert_refused(self.run_after_run_text(deep))

    def test_recursion_error_while_decoding_is_refused_cleanly(self):
        # 2,000,000 nested arrays inside one object: about 4 MB (under the cap), past json's recursion limit.
        deep = '{"a":' + "[" * 2_000_000 + "]" * 2_000_000 + "}"
        self.assert_refused(self.run_after_run_text(deep), "nests too deeply")

    def test_one_mebibyte_of_open_braces_finishes_quickly(self):
        start = time.monotonic()
        result = self.run_after_run_text("{" * (1 << 20))
        elapsed = time.monotonic() - start
        self.assert_refused(result, "no JSON object")
        self.assertLess(elapsed, 5.0)

    def test_oversize_output_is_refused_before_decoding(self):
        oversize = " " * (4 * 1024 * 1024 + 1) + self.plan_text()
        self.assert_refused(self.run_after_run_text(oversize), "exceeds 4194304 bytes")

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
