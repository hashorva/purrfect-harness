#!/usr/bin/env python3
"""Ledger row v1: every section-8 field, a source flag on every number, real CLI entry point.

Expected field names are literal (proposal section 8), not read from the code under test.
Negative cases run scripts/ledger.py as a subprocess and build every mutation in a temp dir.
"""
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "scripts/ledger.py"
SCHEMA = ROOT / "schemas/ledger-row.schema.json"
FIXTURES = ROOT / "tests/fixtures/ledger"
sys.path.insert(0, str(ROOT / "scripts"))
from ledger import FIELDS, SECRET_PATTERNS, UUID_SHAPE, HIDDEN_CHARS, canonical_drift_line, canonical_row_line


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


def run_cli(*args, ledger=LEDGER, cwd=None, timeout=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, str(ledger), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or ROOT,
        timeout=timeout,
    )


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


UNKNOWN_KEY_MESSAGE = "row: unknown key; name not printed"


def hostile_values():
    """Fake secret-, path-, contact- and prompt-shaped values. Each is built at run time from fragments."""
    uuid = "0f1e2d3c" + "-4b5a-4968-8778-" + "6a5b4c3d2e1f"
    classic = "ghp_" + "Zq9A" * 4 + "xB7c" * 5
    fine_grained = "github_pat_" + "Zq9A" * 4 + "xB7c" * 5
    return [
        ("github token", "ghp_" + "A" * 36),
        ("github fine-grained token", "github_pat_" + "11" + "A" * 20),
        ("mixed github token", classic),
        ("mixed fine-grained token", fine_grained),
        ("zero-width non-joiner", "left" + "\u200c" + "right"),
        ("zero-width joiner", "left" + "\u200d" + "right"),
        ("left-to-right mark", "left" + "\u200e" + "right"),
        ("right-to-left mark", "left" + "\u200f" + "right"),
        ("uppercase foreign uuid", "0F1E2D3C" + "-4B5A-4968-8778-" + "6A5B4C3D2E1F"),
        ("aws key id", "AKIA" + "IOSFODNN7EXAMPLE"),
        ("slack token", "xox" + "b-" + "000000000000-0000000000000-" + "A" * 24),
        ("pem header", "-----" + "BEGIN FAKE TEST KEY-----"),
        ("jwt", "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "eyJzdWIiOiJmYWtlLXRlc3Qtc3ViamVjdCJ9." + "fakeSignatureSegment"),
        ("bearer token", "Bear" + "er " + "Tk9t" * 3),
        ("hex token", "0123456789abcdef" + "0123456789abcdef"),
        ("base64 token", "Qm9iZXhh" * 5),
        ("users path", "/Users/" + "example/project"),
        ("private path", "/private/" + "var/tmp/example"),
        ("var folders path", "/var/folders/" + "ab/cd/example"),
        ("home path", "/home/" + "example/work"),
        ("windows drive path", "C:" + "\\" + "work\\example"),
        ("foreign uuid", uuid),
        ("email", "user" + "@" + "example.invalid"),
        ("full-width at sign", "user" + "\uff20" + "example.invalid"),
        ("zero-width space", "T-0" + "\u200b" + "28"),
        ("word joiner", "T-0" + "\u2060" + "28"),
        ("byte order mark", "\ufeff" + "T-028"),
        ("full-width solidus", "docs" + "\uff0f" + "missions"),
        ("line separator", "first" + "\u2028" + "second"),
        ("paragraph separator", "first" + "\u2029" + "second"),
        ("prompt read", "Read " + "AGENTS.md first"),
        ("prompt role", "You are " + "a reviewer"),
        ("prompt follow", "Follow " + "AGENTS.md and go"),
        ("carriage return", "T-028" + "\r" + "slice"),
        ("alternate users path", "/Users/" + "another/project"),
        ("alternate private path", "/private/" + "tmp/another"),
        ("alternate home path", "/home/" + "another/work"),
        ("alternate windows path", "D:" + "\\" + "repo\\another"),
        ("alternate email", "dev" + "@" + "example.invalid"),
        ("alternate bearer", "Bear" + "er " + "YWJj" * 4),
        ("alternate long hex", "fedcba9876543210" + "fedcba9876543210"),
        ("alternate base64", "YWJjZGVm" * 5),
        ("alternate prompt", "Follow " + "AGENTS.md carefully"),
        ("alternate word joiner", "task" + "\u2060" + "name"),
        ("alternate byte order mark", "\ufeff" + "secret-like"),
        ("alternate full-width at", "dev" + "\uff20" + "example.invalid"),
        ("alternate line separator", "one" + "\u2028" + "two"),
    ]


def hostile_locations():
    """Places a hostile value can go in a good row: (error path, edit). group_id is tested on its own."""
    return [
        ("task", lambda row, v: row.__setitem__("task", v)),
        ("failure_class", lambda row, v: row.__setitem__("failure_class", v)),
        ("escalation_reason", lambda row, v: row.__setitem__("escalation_reason", v)),
        ("mission", lambda row, v: row.__setitem__("mission", v)),
        ("feature", lambda row, v: row.__setitem__("feature", v)),
        ("cli", lambda row, v: row.__setitem__("cli", v)),
        ("door", lambda row, v: row.__setitem__("door", v)),
        ("pool", lambda row, v: row.__setitem__("pool", v)),
        ("billing_class", lambda row, v: row.__setitem__("billing_class", v)),
        ("experiment_id", lambda row, v: row.__setitem__("experiment_id", v)),
        ("task_class_tags[0]", lambda row, v: row.__setitem__("task_class_tags", [v])),
        ("active_lesson_ids[0]", lambda row, v: row.__setitem__("active_lesson_ids", [v])),
        ("anti_gaming_flags[0]", lambda row, v: row.__setitem__("anti_gaming_flags", [v])),
        ("checks[0].name", lambda row, v: row["checks"][0].__setitem__("name", v)),
        ("cost.currency", lambda row, v: row["cost"].__setitem__("currency", v)),
        ("requested_model.value", lambda row, v: row["requested_model"].__setitem__("value", v)),
        ("resolved_model.value", lambda row, v: row["resolved_model"].__setitem__("value", v)),
        ("observed_model.value", lambda row, v: row["observed_model"].__setitem__("value", v)),
        ("effort.value", lambda row, v: row["effort"].__setitem__("value", v)),
        ("cli_version.value", lambda row, v: row["cli_version"].__setitem__("value", v)),
    ]


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
            "bad-extra-key.json": f"ERROR: ledger: {UNKNOWN_KEY_MESSAGE}",
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

    def expect_privacy_rejection(self, row, field_message, hostile):
        self.count += 1
        path = Path(self.tmp.name) / f"case-{self.count}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        result = run_cli("validate", str(path))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stderr.strip(), f"ERROR: ledger: {field_message}")
        self.assertNotIn(hostile, result.stderr)
        self.assertNotIn(hostile, result.stdout)

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
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("prompt_text", "x")), UNKNOWN_KEY_MESSAGE)
        self.expect_invalid(
            self.mutated(lambda row: row["cost"].__setitem__("note", "x")),
            "cost: unknown key; name not printed",
        )
        self.expect_invalid(
            self.mutated(lambda row: row["checks"][0].__setitem__("stdout", "x")),
            "checks[0]: unknown key; name not printed",
        )
        self.expect_invalid(
            self.mutated(lambda row: row["diff_size"].__setitem__("hunks", {"value": 1, "source": "observed"})),
            "diff_size: unknown key; name not printed",
        )

    def test_unknown_key_name_is_never_printed(self):
        # Point 6: the level is named, the key name (which could be an email or a secret) is not.
        for key in ("user" + "@" + "example.invalid", "ghp_" + "A" * 36, "debug" + "_" + "notes"):
            with self.subTest(key_kind=key[:4], level="top"):
                self.expect_hidden_key_rejection(
                    self.mutated(lambda row, k=key: row.__setitem__(k, "x")), UNKNOWN_KEY_MESSAGE, key
                )
            with self.subTest(key_kind=key[:4], level="nested"):
                self.expect_hidden_key_rejection(
                    self.mutated(lambda row, k=key: row["cost"].__setitem__(k, "x")),
                    "cost: unknown key; name not printed",
                    key,
                )
        # A hostile key with a hostile value is refused by the privacy walk, which shows "<unknown key>".
        hostile_key = "user" + "@" + "example.invalid"
        hostile_value = "ghp_" + "A" * 36
        self.expect_hidden_key_rejection(
            self.mutated(lambda row: row.__setitem__(hostile_key, hostile_value)),
            "<unknown key>: privacy",
            hostile_key,
        )
        self.assertNotIn(hostile_value, self.check_row(self.mutated(lambda row: row.__setitem__(hostile_key, hostile_value))).stderr)

    def expect_hidden_key_rejection(self, row, message, hidden):
        self.count += 1
        path = Path(self.tmp.name) / f"case-{self.count}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        result = run_cli("validate", str(path))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stderr.strip(), f"ERROR: ledger: {message}")
        self.assertNotIn(hidden, result.stderr)
        self.assertNotIn(hidden, result.stdout)

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


    def assert_rule_is_load_bearing(self, rule, hostile, field="task"):
        """Remove one rule in a temporary validator copy and prove its negative fails."""
        source = LEDGER.read_text(encoding="utf-8")
        if rule == "paths":
            mutant = source.replace(" or SENSITIVE_PATH.search(value)", "")
        elif rule == "bidi":
            mutant = source.replace("\\u202a-\\u202e", "").replace("\\u2066-\\u2069", "")
        else:
            mutant = source.replace('r"(?i:Bearer)[ \\t]\\S"', 'r"Bearer \\S"')
        self.assertNotEqual(mutant, source, rule)
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "ledger.py"
            copy.write_text(mutant, encoding="utf-8")
            row_path = Path(temp) / "row.json"
            row = json.loads(json.dumps(load(GOOD)))
            row[field] = hostile
            row_path.write_text(json.dumps(row), encoding="utf-8")
            result = run_cli("validate", str(row_path), ledger=copy)
            self.assertEqual(result.returncode, 0, f"{rule} mutant did not admit hostile value: {result.stderr}")

    def test_added_sensitive_paths_are_rejected_in_two_fields_and_load_bearing(self):
        values = ("/" + "tmp/" + "x", "~" + "/x", "$" + "HOME/x", "/" + "etc/" + "passwd")
        for hostile in values:
            for field in ("task", "failure_class"):
                with self.subTest(value=hostile, field=field):
                    self.expect_privacy_rejection(
                        self.mutated(lambda row, n=field, v=hostile: row.__setitem__(n, v)),
                        f"{field}: privacy", hostile,
                    )
        self.assert_rule_is_load_bearing("paths", values[0])

    def test_added_bidi_controls_are_rejected_in_two_fields_and_load_bearing(self):
        controls = tuple(chr(codepoint) for codepoint in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))
        for control in controls:
            hostile = "left" + control + "right"
            for field in ("task", "failure_class"):
                with self.subTest(codepoint=ord(control), field=field):
                    self.expect_privacy_rejection(
                        self.mutated(lambda row, n=field, v=hostile: row.__setitem__(n, v)),
                        f"{field}: privacy", hostile,
                    )
        self.assert_rule_is_load_bearing("bidi", "left" + controls[0] + "right")

    def test_bearer_case_and_tab_are_rejected_in_two_fields_and_load_bearing(self):
        values = ("bearer " + "abc", "BEARER " + "abc", "BeArEr " + "abc", "bearer\t" + "abc")
        for hostile in values:
            for field in ("task", "failure_class"):
                with self.subTest(value=hostile, field=field):
                    self.expect_privacy_rejection(
                        self.mutated(lambda row, n=field, v=hostile: row.__setitem__(n, v)),
                        f"{field}: privacy", hostile,
                    )
        self.assert_rule_is_load_bearing("bearer", values[0])

    def test_relative_repository_path_is_allowed_in_check_label(self):
        row = self.mutated(lambda r: r["checks"][0].__setitem__("name", "scripts/ledger.py"))
        self.assertEqual(self.check_row(row).returncode, 0)

    def test_privacy_rules_reject_long_or_multiline_text(self):
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("task", "x" * 201)), "task: privacy")
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("task", "first\nsecond")), "task: privacy")

    def test_privacy_rule_rejects_launcher_prompt_prefix(self):
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("task", "Read docs/missions/example")), "task: privacy")

    def test_privacy_rule_rejects_secret_like_values(self):
        self.expect_invalid(
            self.mutated(lambda row: row["checks"][0].__setitem__("name", "sk-" + "a" * 20)),
            "checks[0].name: privacy",
        )

    def test_privacy_rule_rejects_email_addresses(self):
        self.expect_invalid(self.mutated(lambda row: row.__setitem__("task", "owner@example.com")), "task: privacy")

    def test_privacy_rule_rejects_carriage_return(self):
        hostile = "T-028\rslice"
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row.__setitem__("task", v)),
            "task: privacy",
            hostile,
        )

    def test_privacy_rule_rejects_classic_github_token(self):
        hostile = "ghp_" + "A" * 36
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row.__setitem__("failure_class", v)),
            "failure_class: privacy",
            hostile,
        )

    def test_github_tokens_are_caught_only_by_their_own_pattern(self):
        values = (
            ("classic", "ghp_" + "Zq9A" * 4 + "xB7c" * 5, r"ghp_[A-Za-z0-9]{20,}"),
            ("fine_grained", "github_pat_" + "Zq9A" * 4 + "xB7c" * 5, r"github_pat_"),
        )
        patterns = {pattern.pattern: pattern for pattern in SECRET_PATTERNS}
        for label, hostile, expected in values:
            with self.subTest(token=label):
                self.assertEqual(sum(pattern.search(hostile) is not None for pattern in SECRET_PATTERNS), 1)
                self.assertIsNotNone(patterns[expected].search(hostile))
                self.expect_privacy_rejection(
                    self.mutated(lambda row, v=hostile: row.__setitem__("task", v)), "task: privacy", hostile,
                )

    def test_privacy_rule_rejects_each_zero_width_and_directional_mark(self):
        for codepoint in ("\u200c", "\u200d", "\u200e", "\u200f"):
            hostile = "left" + codepoint + "right"
            with self.subTest(codepoint=ord(codepoint)):
                self.assertIsNotNone(HIDDEN_CHARS.search(hostile))
                self.expect_privacy_rejection(
                    self.mutated(lambda row, v=hostile: row.__setitem__("task", v)), "task: privacy", hostile,
                )

    def test_privacy_rule_rejects_uppercase_uuid_in_text_field(self):
        hostile = "0F1E2D3C" + "-4B5A-4968-8778-" + "6A5B4C3D2E1F"
        self.assertIsNotNone(UUID_SHAPE.search(hostile))
        for field in ("task", "escalation_reason"):
            with self.subTest(field=field):
                self.expect_privacy_rejection(
                    self.mutated(lambda row, n=field, v=hostile: row.__setitem__(n, v)),
                    f"{field}: privacy", hostile,
                )

    def test_privacy_rule_rejects_fine_grained_github_token(self):
        hostile = "github_pat_" + "11AAAAAA0000000000000000000000000000000000"
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row.__setitem__("escalation_reason", v)),
            "escalation_reason: privacy",
            hostile,
        )

    def test_privacy_rule_rejects_akia_key_id(self):
        hostile = "AKIA" + "IOSFODNN7EXAMPLE"
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row.__setitem__("group_id", v)),
            "group_id: privacy",
            hostile,
        )

    def test_privacy_rule_rejects_slack_token(self):
        hostile = "xox" + "b-000000000000-0000000000000-" + "A" * 24
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row.__setitem__("experiment_id", v)),
            "experiment_id: privacy",
            hostile,
        )

    def test_privacy_rule_rejects_pem_begin_header(self):
        hostile = "-----" + "BEGIN FAKE TEST KEY-----"
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row.__setitem__("mission", v)),
            "mission: privacy",
            hostile,
        )

    def test_privacy_rule_rejects_jwt_shaped_value(self):
        hostile = (
            "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJmYWtlLXRlc3Qtc3ViamVjdCJ9."
            "fakeSignatureSegmentForPrivacyTestOnly"
        )
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row["requested_model"].__setitem__("value", v)),
            "requested_model.value: privacy",
            hostile,
        )

    def test_hostile_values_are_rejected_in_every_field_family(self):
        # Distinct hostile values each go in two different fields; every case must be refused.
        cases = 0
        locations = hostile_locations()
        values = hostile_values()
        self.assertGreaterEqual(len(values), 40)
        for index, (label, hostile) in enumerate(values):
            for offset in (0, 9):
                path, edit = locations[(index + offset) % len(locations)]
                cases += 1
                with self.subTest(value=label, field=path):
                    self.expect_privacy_rejection(
                        self.mutated(lambda row, e=edit, v=hostile: e(row, v)),
                        f"{path}: privacy",
                        hostile,
                    )
        self.assertEqual(cases, len(values) * 2)

    def test_privacy_rule_rejects_absolute_paths(self):
        # Point 1.
        for label, hostile in hostile_values():
            if label.endswith("path"):
                with self.subTest(value=label):
                    self.expect_privacy_rejection(
                        self.mutated(lambda row, v=hostile: row.__setitem__("task", v)), "task: privacy", hostile,
                    )

    def test_privacy_rule_rejects_foreign_uuid_in_text_fields(self):
        # Point 2: a UUID is refused in a text field, and accepted in the three id fields.
        hostile = "0f1e2d3c" + "-4b5a-4968-8778-" + "6a5b4c3d2e1f"
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row.__setitem__("task", v)), "task: privacy", hostile,
        )
        self.expect_privacy_rejection(
            self.mutated(lambda row, v=hostile: row.__setitem__("escalation_reason", v)),
            "escalation_reason: privacy",
            hostile,
        )

    def test_id_fields_accept_run_ids(self):
        # Point 2 (the other half): the row's own id fields legitimately hold UUIDs.
        other = "0f1e2d3c-4b5a-4968-8778-6a5b4c3d2e1f"
        for name in ("parent_run", "run_id"):
            with self.subTest(field=name):
                row = self.mutated(lambda r, n=name: r.__setitem__(n, other))
                self.assertEqual(self.check_row(row).returncode, 0)
        row = self.mutated(lambda r: r.__setitem__("group_id", other))
        self.assertEqual(self.check_row(row).returncode, 0)

    def test_privacy_rule_rejects_bearer_and_long_tokens(self):
        # Point 3: a bearer token, 32+ hex characters, or 40+ base64-alphabet characters.
        for label, hostile in hostile_values():
            if label in ("bearer token", "hex token", "base64 token"):
                with self.subTest(value=label):
                    self.expect_privacy_rejection(
                        self.mutated(lambda row, v=hostile: row.__setitem__("task", v)), "task: privacy", hostile,
                    )

    def test_legitimate_values_still_pass(self):
        # Point 3, the other half: model names, seat names, run ids and short reasons are not caught.
        row = self.mutated(lambda r: r.__setitem__("escalation_reason", "budget reached after 2 turns"))
        row["requested_model"]["value"] = "Composer 2.5"
        row["group_id"] = "claude.economy-night-2"
        row["parent_run"] = "0f1e2d3c-4b5a-4968-8778-6a5b4c3d2e1f"
        row["task_class_tags"] = ["ledger", "validator", "privacy-rule"]
        self.assertEqual(self.check_row(row).returncode, 0)
        self.assertEqual(self.check_row(self.base).returncode, 0)

    def test_privacy_rule_rejects_hidden_characters(self):
        # Point 4.
        for label, hostile in hostile_values():
            if label in ("zero-width space", "word joiner", "byte order mark", "full-width at sign",
                         "full-width solidus", "line separator", "paragraph separator"):
                with self.subTest(value=label):
                    self.expect_privacy_rejection(
                        self.mutated(lambda row, v=hostile: row.__setitem__("failure_class", v)),
                        "failure_class: privacy",
                        hostile,
                    )

    def test_privacy_rule_rejects_prompt_prefix_variants(self):
        # Point 5.
        for label, hostile in hostile_values():
            if label.startswith("prompt "):
                with self.subTest(value=label):
                    self.expect_privacy_rejection(
                        self.mutated(lambda row, v=hostile: row.__setitem__("task", v)), "task: privacy", hostile,
                    )

    def check_row(self, row):
        self.count += 1
        path = Path(self.tmp.name) / f"case-{self.count}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        return run_cli("validate", str(path))

    def test_invalid_json_is_rejected(self):
        path = Path(self.tmp.name) / "broken.json"
        path.write_text("{", encoding="utf-8")
        result = run_cli("validate", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("ERROR: ledger: document: not readable as JSON"), result.stderr)


class LedgerFoldTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp())
        self.root = self.parent / "repo"
        self.root.mkdir()
        (self.root / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEDGER, self.root / "scripts/ledger.py")
        self.mission_path = "docs/missions/fixture"
        mission = self.root / self.mission_path
        mission.mkdir(parents=True)
        (self.root / "docs/missions").mkdir(parents=True, exist_ok=True)
        (self.root / ".gitignore").write_text(".tasks/\n")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.root, check=True)

    def tearDown(self):
        shutil.rmtree(self.parent)

    def fold(self, *extra, timeout=None):
        return run_cli("fold", self.mission_path, ledger=self.root / "scripts/ledger.py", cwd=self.root, timeout=timeout, *extra)

    def write_row(self, row, *, run_id=None):
        run_id = run_id or row["run_id"]
        row = dict(row)
        row["mission"] = "fixture"
        row["run_id"] = run_id
        directory = self.root / ".tasks/ledger"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{run_id}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        return row

    def test_fold_appends_rows_once_in_run_id_order(self):
        base = load(GOOD)
        first_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        second_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        self.write_row(base, run_id=second_id)
        self.write_row(base, run_id=first_id)
        first = self.fold()
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(first.stdout.strip(), "folded rows=2 drift=0")
        lines = (self.root / "docs/missions/ledger.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["run_id"], first_id)
        self.assertEqual(json.loads(lines[1])["run_id"], second_id)
        second = self.fold()
        self.assertEqual(second.stdout.strip(), "folded rows=0 drift=0")
        self.assertEqual(len((self.root / "docs/missions/ledger.jsonl").read_text().splitlines()), 2)

    def test_fold_appends_to_existing_history_and_rows_are_canonical(self):
        first = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        second = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        row1 = self.write_row(load(GOOD), run_id=first)
        result = self.fold()
        self.assertEqual(result.returncode, 0, result.stderr)
        ledger = self.root / "docs/missions/ledger.jsonl"
        old = ledger.read_bytes()
        row2 = self.write_row(load(GOOD), run_id=second)
        event = self.good_drift()
        source = self.root / ".tasks/drift/fixture.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(canonical_drift_line(event), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = ledger.read_bytes()
        self.assertTrue(after.startswith(old))
        self.assertEqual(after[len(old):], canonical_row_line(row2).encode())
        self.assertEqual(ledger.read_text().splitlines()[0] + "\n", canonical_row_line(row1))
        self.assertEqual((self.root / self.mission_path / "drift.jsonl").read_text(), canonical_drift_line(event))
        self.assertEqual(self.fold().stdout.strip(), "folded rows=0 drift=0")

    @staticmethod
    def good_drift():
        return {
            "at": "2026-08-21T00:00:00Z", "mission": "docs/missions/fixture", "seat": "codex.economy",
            "from": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "medium", "speed": "unknown"},
            "to": {"provider": "codex", "model": "gpt-5.7-luna", "effort": "medium", "speed": "unknown"},
            "inventory_sha256": "0" * 64,
        }

    def test_fold_refuses_invalid_row(self):
        base = load(GOOD)
        run_id = str(uuid.uuid4())
        row = self.write_row(base, run_id=run_id)
        row["outcome"] = "not-an-outcome"
        path = self.root / ".tasks/ledger" / f"{run_id}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: ledger:", result.stderr)
        self.assertFalse((self.root / "docs/missions/ledger.jsonl").exists())

    def test_fold_appends_drift_events_once(self):
        event = self.good_drift()
        drift_dir = self.root / ".tasks/drift"
        drift_dir.mkdir(parents=True, exist_ok=True)
        (drift_dir / "fixture.jsonl").write_text(canonical_drift_line(event), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stdout.strip(), "folded rows=0 drift=1")
        committed = (self.root / self.mission_path / "drift.jsonl").read_text(encoding="utf-8")
        self.assertEqual(committed, canonical_drift_line(event))
        again = self.fold()
        self.assertEqual(again.stdout.strip(), "folded rows=0 drift=0")

    def test_fold_appends_drift_preserving_existing_drift_bytes(self):
        first_event = self.good_drift()
        source = self.root / ".tasks/drift/fixture.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(canonical_drift_line(first_event), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 0, result.stderr)
        drift_path = self.root / self.mission_path / "drift.jsonl"
        old = drift_path.read_bytes()
        second_event = dict(first_event, inventory_sha256="1" * 64, to=dict(first_event["to"], model="gpt-5.8-luna"))
        source.write_text(canonical_drift_line(second_event), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = drift_path.read_bytes()
        self.assertTrue(after.startswith(old))
        self.assertEqual(after[len(old):], canonical_drift_line(second_event).encode())

    def test_fold_refuses_missing_and_extra_resolution_keys(self):
        source = self.root / ".tasks/drift/fixture.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        missing = self.good_drift()
        del missing["from"]["speed"]
        source.write_text(json.dumps(missing) + "\n", encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("speed", result.stderr)
        source.unlink()
        extra = self.good_drift()
        extra["from"]["door"] = "codex"
        source.write_text(json.dumps(extra) + "\n", encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown key", result.stderr)

    def test_fold_refuses_bad_inventory_sha256(self):
        source = self.root / ".tasks/drift/fixture.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        for bad in ("G" * 64, "a" * 63, "A" * 64):
            event = self.good_drift()
            event["inventory_sha256"] = bad
            source.write_text(json.dumps(event) + "\n", encoding="utf-8")
            result = self.fold()
            self.assertEqual(result.returncode, 1, bad)
            self.assertIn("inventory_sha256", result.stderr)
            source.unlink()

    def test_fold_refuses_secret_shaped_resolution_key_without_echoing_name(self):
        source = self.root / ".tasks/drift/fixture.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        event = self.good_drift()
        secret_key = "ghp_" + "K" * 20
        path_value = "/Users/" + "private"
        event["from"] = {secret_key: path_value, **event["from"]}
        source.write_text(json.dumps(event) + "\n", encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1, result.stdout)
        combined = result.stdout + result.stderr
        self.assertNotIn(secret_key, combined)
        self.assertIn("unknown key", combined)

    def test_fold_reads_large_committed_ledger_jsonl(self):
        ledger = self.root / "docs/missions/ledger.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        pad = "x" * 2500
        lines = []
        for index in range(500):
            run_id = f"{index:08x}-0000-4000-8000-000000000000"
            lines.append(json.dumps({"run_id": run_id, "_pad": pad}) + "\n")
        ledger.write_text("".join(lines), encoding="utf-8")
        self.assertGreater(ledger.stat().st_size, 1024 * 1024)
        row = self.write_row(load(GOOD), run_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        result = self.fold()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "folded rows=1 drift=0")
        self.assertIn(canonical_row_line(row).strip(), ledger.read_text())

    def test_fold_dedupes_drift_within_batch_and_skips_other_mission(self):
        event = self.good_drift()
        other = dict(event, mission="docs/missions/other")
        source = self.root / ".tasks/drift/fixture.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(canonical_drift_line(event) + canonical_drift_line(event) + canonical_drift_line(other), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "folded rows=0 drift=1")

    def test_fold_enforces_run_id_identity_and_canonical_duplicates(self):
        row = self.write_row(load(GOOD), run_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        other = dict(row, feature="F004")
        (self.root / ".tasks/ledger/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb.json").write_text(json.dumps(other), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("run_id", result.stderr)
        (self.root / ".tasks/ledger/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb.json").unlink()
        duplicate = self.root / ".tasks/ledger/cccccccc-cccc-4ccc-8ccc-cccccccccccc.json"
        duplicate.write_text(json.dumps(row), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1, "filename/run_id mismatch must be refused")

    def test_fold_skips_only_byte_identical_existing_run_id(self):
        row = self.write_row(load(GOOD), run_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        ledger = self.root / "docs/missions/ledger.jsonl"
        ledger.write_text(canonical_row_line(row), encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "folded rows=0 drift=0")
        ledger.write_text(json.dumps(dict(row, feature="F004"), separators=(",", ":")) + "\n", encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("run_id", result.stderr)

    def test_fold_rejects_malformed_objects_without_tracebacks(self):
        row_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        (self.root / ".tasks/ledger").mkdir(parents=True, exist_ok=True)
        (self.root / ".tasks/ledger" / f"{row_id}.json").write_text("[]", encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        (self.root / ".tasks/ledger" / f"{row_id}.json").unlink()
        source = self.root / ".tasks/drift/fixture.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("[]\n", encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        source.unlink()
        committed = self.root / "docs/missions/ledger.jsonl"
        committed.write_text("{}\n", encoding="utf-8")
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("run_id", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_fold_validates_drift_privacy_keys_and_paths_without_echoing_values(self):
        variants = []
        secret = "ghp_" + "A" * 36
        variants.append((lambda event: event["to"].__setitem__("model", secret), secret))
        variants.append((lambda event: event.__setitem__("unrecognized", "safe"), "unrecognized"))
        path_value = "/Users/" + "private/project"
        variants.append((lambda event: event["to"].__setitem__("model", path_value), path_value))
        for edit, hidden in variants:
            source = self.root / ".tasks/drift/fixture.jsonl"
            source.parent.mkdir(parents=True, exist_ok=True)
            event = self.good_drift()
            edit(event)
            source.write_text(json.dumps(event) + "\n", encoding="utf-8")
            result = self.fold()
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertNotIn(hidden, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            source.unlink()

    def test_fold_refuses_unsafe_input_files_and_target_symlinks(self):
        directory = self.root / ".tasks/ledger"
        directory.mkdir(parents=True, exist_ok=True)
        huge = directory / "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.json"
        huge.write_bytes(b" " * (1024 * 1024 + 1))
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("size limit", result.stderr)
        huge.unlink()
        if hasattr(os, "mkfifo"):
            fifo = directory / "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb.json"
            os.mkfifo(fifo)
            result = self.fold(timeout=3)
            self.assertEqual(result.returncode, 1)
            self.assertIn("regular file", result.stderr)
            fifo.unlink()
        link = directory / "cccccccc-cccc-4ccc-8ccc-cccccccccccc.json"
        outside = self.parent / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        link.symlink_to(outside)
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink", result.stderr)
        link.unlink()
        target = self.root / "docs/missions/ledger.jsonl"
        target.symlink_to(outside)
        result = self.fold()
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink", result.stderr)

    def test_fold_skips_other_missions(self):
        base = load(GOOD)
        foreign = dict(base)
        foreign["mission"] = "other-mission"
        foreign["run_id"] = str(uuid.uuid4())
        directory = self.root / ".tasks/ledger"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{foreign['run_id']}.json").write_text(json.dumps(foreign), encoding="utf-8")
        local_id = str(uuid.uuid4())
        self.write_row(base, run_id=local_id)
        result = self.fold()
        self.assertEqual(result.stdout.strip(), "folded rows=1 drift=0")
        lines = (self.root / "docs/missions/ledger.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["run_id"], local_id)


class LedgerTestsLeaveNoBytecode(unittest.TestCase):
    def test_no_bytecode_folder_in_the_tree(self):
        self.assertFalse((ROOT / "scripts/__pycache__").exists())
        self.assertFalse((ROOT / "tests/__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
