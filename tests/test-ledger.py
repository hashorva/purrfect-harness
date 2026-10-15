#!/usr/bin/env python3
"""Ledger row v1: every section-8 field, a source flag on every number, real CLI entry point.

Expected field names are literal (proposal section 8), not read from the code under test.
Negative cases run scripts/ledger.py as a subprocess and build every mutation in a temp dir.
"""
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "scripts/ledger.py"
SCHEMA = ROOT / "schemas/ledger-row.schema.json"
FIXTURES = ROOT / "tests/fixtures/ledger"
sys.path.insert(0, str(ROOT / "scripts"))
from ledger import FIELDS


SECTION_8_FIELDS = [
    "mission", "feature", "task", "run_id", "parent_run", "group_id", "attempt", "repair_round",
    "cli", "cli_version", "door", "pool", "billing_class",
    "requested_model", "resolved_model", "observed_model", "effort", "fast_state",
    "task_class_tags", "allow_list_size", "task_text_tokens", "ste_flag", "active_lesson_ids",
    "experiment_id", "wall_time_s", "turns", "tool_calls", "tokens_input", "tokens_output",
    "tokens_cache", "tokens_reasoning", "cost", "quota_share", "checks", "diff_size",
    "scope_result", "anti_gaming_flags", "failure_class", "escalation_reason", "outcome",
]
# Literal list of every field that is a number and therefore needs a source flag.
NUMBER_FIELDS = [
    "allow_list_size", "task_text_tokens", "wall_time_s", "turns", "tool_calls",
    "tokens_input", "tokens_output", "tokens_cache", "tokens_reasoning", "quota_share",
]
TEXT_FLAG_FIELDS = ["cli_version", "requested_model", "resolved_model", "observed_model", "effort", "fast_state"]
GOOD = FIXTURES / "good-completed.json"


def run_cli(*args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(LEDGER), *args], capture_output=True, text=True, env=env)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class LedgerContract(unittest.TestCase):
    def test_every_section_8_field_is_in_the_validator_and_schema(self):
        schema = load(SCHEMA)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        properties = set(schema["properties"])
        self.assertEqual(set(schema["required"]), properties)
        self.assertEqual(properties, set(FIELDS))
        self.assertEqual(set(SECTION_8_FIELDS) - properties, set(), "section 8 field missing from schema")
        self.assertEqual(properties - set(SECTION_8_FIELDS) - {"schema_version"}, set(), "unexpected schema field")

    def test_every_number_and_model_field_references_a_source_flag(self):
        properties = load(SCHEMA)["properties"]
        for name in NUMBER_FIELDS:
            self.assertEqual(properties[name]["$ref"], "#/$defs/numberFlag", name)
        for name in TEXT_FLAG_FIELDS:
            self.assertEqual(properties[name]["$ref"], "#/$defs/textFlag", name)
        self.assertEqual(properties["cost"]["required"], ["value", "source", "currency"])

    def test_good_fixtures_are_valid_through_the_cli(self):
        good = sorted(FIXTURES.glob("good-*.json"))
        self.assertGreaterEqual(len(good), 2)
        for path in good:
            with self.subTest(fixture=path.name):
                result = run_cli("validate", str(path))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("OK: ledger row valid", result.stdout)

    def test_bad_fixtures_are_rejected_through_the_cli(self):
        expected = {
            "bad-missing-field.json": "ERROR: ledger: wall_time_s: is required",
            "bad-number-without-source.json": "ERROR: ledger: wall_time_s: must be an object",
            "bad-observed-null.json": "ERROR: ledger: turns.value: must not be null when source is observed",
            "bad-extra-key.json": "ERROR: ledger: debug_notes: unknown key",
        }
        for name, message in expected.items():
            with self.subTest(fixture=name):
                result = run_cli("validate", str(FIXTURES / name))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr.strip(), message)

    def test_usage_error_exits_2(self):
        self.assertEqual(run_cli().returncode, 2)


class LedgerMutations(unittest.TestCase):
    """Each case writes one mutated copy of the good row into a temp dir and runs the CLI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = load(GOOD)
        self.count = 0

    def expect_invalid(self, row, message):
        self.count += 1
        path = Path(self.tmp.name) / f"case-{self.count}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        result = run_cli("validate", str(path))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stderr.strip(), f"ERROR: ledger: {message}")

    def mutated(self, edit):
        row = json.loads(json.dumps(self.base))
        edit(row)
        return row

    def test_every_top_level_field_is_required(self):
        for name in FIELDS:
            with self.subTest(field=name):
                self.expect_invalid(self.mutated(lambda row, n=name: row.pop(n)), f"{name}: is required")

    def test_number_without_source_is_rejected(self):
        for name in NUMBER_FIELDS:
            with self.subTest(field=name):
                self.expect_invalid(self.mutated(lambda row, n=name: row.__setitem__(n, 3)), f"{name}: must be an object")

    def test_source_flag_must_match_the_value(self):
        for name in NUMBER_FIELDS:
            with self.subTest(field=name, case="observed null"):
                self.expect_invalid(
                    self.mutated(lambda row, n=name: row.__setitem__(n, {"value": None, "source": "observed"})),
                    f"{name}.value: must not be null when source is observed",
                )
            with self.subTest(field=name, case="unknown with value"):
                self.expect_invalid(
                    self.mutated(lambda row, n=name: row.__setitem__(n, {"value": 1, "source": "unknown"})),
                    f"{name}.value: must be null when source is unknown",
                )
            with self.subTest(field=name, case="bad source"):
                self.expect_invalid(
                    self.mutated(lambda row, n=name: row.__setitem__(n, {"value": 1, "source": "measured"})),
                    f"{name}.source: must be one of observed, estimated, unknown",
                )
            with self.subTest(field=name, case="boolean value"):
                self.expect_invalid(
                    self.mutated(lambda row, n=name: row.__setitem__(n, {"value": True, "source": "observed"})),
                    f"{name}.value: must be a finite number >= 0",
                )

    def test_model_fields_need_a_source_flag(self):
        for name in TEXT_FLAG_FIELDS:
            with self.subTest(field=name):
                self.expect_invalid(
                    self.mutated(lambda row, n=name: row.__setitem__(n, "claude-haiku-5-5")),
                    f"{name}: must be an object",
                )

    def test_cost_needs_currency_and_a_source_flag(self):
        self.expect_invalid(
            self.mutated(lambda row: row["cost"].pop("currency")),
            "cost.currency: is required",
        )
        self.expect_invalid(
            self.mutated(lambda row: row.__setitem__("cost", 0.5)),
            "cost: must be an object",
        )

    def test_unknown_keys_are_rejected_at_every_level(self):
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("prompt_text", "x")), "prompt_text: unknown key")
        self.expect_invalid(
            self.mutated(lambda row: row["cost"].__setitem__("note", "x")), "cost.note: unknown key"
        )
        self.expect_invalid(
            self.mutated(lambda row: row["checks"][0].__setitem__("stdout", "x")),
            "checks[0].stdout: unknown key",
        )
        self.expect_invalid(
            self.mutated(lambda row: row["diff_size"].__setitem__("hunks", {"value": 1, "source": "observed"})),
            "diff_size.hunks: unknown key",
        )

    def test_identity_and_enum_fields_are_checked(self):
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("schema_version", 2)), "schema_version: must be 1")
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("attempt", 0)), "attempt: must be an integer >= 1")
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("run_id", "not-a-run")), "run_id: must be a run id (UUID v1-8)")
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("outcome", "done")), "outcome: must be one of completed, failed, timed_out, interrupted, launch_failed")
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("scope_result", "ok")), "scope_result: must be one of pass, fail, not_checked")
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("ste_flag", "no")), "ste_flag: must be true or false")

    def test_lists_reject_duplicates_and_bad_checks(self):
        self.expect_invalid(
            self.mutated(lambda row: row.__setitem__("task_class_tags", ["ledger", "ledger"])),
            "task_class_tags: must not contain duplicate items",
        )
        self.expect_invalid(
            self.mutated(lambda row: row.__setitem__("checks", [{"name": "shellcheck"}])),
            "checks[0].exit_code: is required",
        )

    def test_row_must_be_an_object(self):
        self.expect_invalid([], "row: must be an object")

    def test_invalid_json_is_rejected(self):
        path = Path(self.tmp.name) / "broken.json"
        path.write_text("{", encoding="utf-8")
        result = run_cli("validate", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("ERROR: ledger: document: not readable as JSON"), result.stderr)


class LedgerTestsLeaveNoBytecode(unittest.TestCase):
    def test_no_bytecode_folder_in_the_tree(self):
        self.assertFalse((ROOT / "scripts/__pycache__").exists())
        self.assertFalse((ROOT / "tests/__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
