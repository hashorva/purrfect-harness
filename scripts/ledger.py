#!/usr/bin/env python3
"""Ledger v1 row: field contract and dependency-free validator (F005).

One row summarises one run, failed runs included. Every number carries a source flag:
observed (measured), estimated, or unknown (value null). A value is never copied from
the spec or guessed. Unknown keys are rejected, so a new field needs a schema change.

Usage: ledger.py validate <file>   (exit 0 valid, 1 invalid, 2 usage)
"""
import json
import math
import re
import sys

SCHEMA_VERSION = 1
SOURCES = ("observed", "estimated", "unknown")
# Privacy rule, applied to every text value at every nesting level (lists included).
# Not covered, on purpose: a secret split across several fields. Each part alone looks harmless,
# and the validator checks one value at a time.
SECRET_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_",
    r"AKIA[0-9A-Z]{16}", r"xox[abpr]-", r"-----BEGIN", r"eyJ[A-Za-z0-9_-]{20,}\.",
    r"(?i:Bearer)[ \t]\S", r"[0-9A-Fa-f]{32,}", r"[A-Za-z0-9+/=]{40,}",
))
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+")
ABSOLUTE_PATH = re.compile(r"/Users/|/private/|/var/folders/|/home/|[A-Za-z]:\\")
SENSITIVE_PATH = re.compile(r"/tmp/|/etc/|~/|\$HOME")
UUID_SHAPE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
# Hidden format characters, bidi controls, full-width @ and /, and line separators.
HIDDEN_CHARS = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff\uff20\uff0f\u2028\u2029]")
PROMPT_PREFIX = "Read docs/missions/"
PROMPT_PREFIXES = re.compile(r"^\s*(?:Read \S*[/\\.]|You are |Follow AGENTS\.md)")
OUTCOMES = ("completed", "failed", "timed_out", "interrupted", "launch_failed")
SCOPE_RESULTS = ("pass", "fail", "not_checked")
RUN_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

FIELDS = (
    "schema_version", "mission", "feature", "task", "run_id", "parent_run", "group_id",
    "attempt", "repair_round",
    "cli", "cli_version", "door", "pool", "billing_class",
    "requested_model", "resolved_model", "observed_model", "effort", "fast_state",
    "task_class_tags", "allow_list_size", "task_text_tokens", "ste_flag", "active_lesson_ids",
    "experiment_id",
    "wall_time_s", "turns", "tool_calls", "tokens_input", "tokens_output", "tokens_cache",
    "tokens_reasoning", "cost", "quota_share", "checks", "diff_size", "scope_result",
    "anti_gaming_flags", "failure_class", "escalation_reason", "outcome",
)
# The row's own id fields: the only text fields that may hold a UUID shape.
ID_FIELDS = ("run_id", "parent_run", "group_id")
# Key names the privacy walk may print. Any other key is shown as "<unknown key>".
KNOWN_KEYS = frozenset(FIELDS) | {"value", "source", "currency", "name", "exit_code", "files", "lines"}


class LedgerError(Exception):
    def __init__(self, field, reason):
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


def fail(field, reason):
    raise LedgerError(field, reason)


def sub(path, key):
    return f"{path}.{key}" if path else key


def is_count(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def check_object(path, value, keys):
    if not isinstance(value, dict):
        fail(path or "row", "must be an object")
    for key in keys:
        if key not in value:
            fail(sub(path, key), "is required")
    for key in value:
        if key not in keys:
            # The key name is not printed: it could itself be an email address or a secret.
            fail(path or "row", "unknown key; name not printed")


def check_privacy(path, value, id_field=False):
    """Reject raw prompt, transcript, contact, path, or secret-like string values.

    Unknown key names are not printed either: they are shown as "<unknown key>".
    """
    if isinstance(value, dict):
        for key, item in value.items():
            name = key if key in KNOWN_KEYS else "<unknown key>"
            check_privacy(sub(path, name), item, id_field=(path == "" and key in ID_FIELDS))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_privacy(f"{path}[{index}]", item)
    elif isinstance(value, str):
        if (len(value) > 200 or "\n" in value or "\r" in value
                or PROMPT_PREFIX in value or PROMPT_PREFIXES.search(value) or EMAIL.search(value)
                or ABSOLUTE_PATH.search(value) or SENSITIVE_PATH.search(value) or HIDDEN_CHARS.search(value)
                or (not id_field and UUID_SHAPE.search(value))
                or any(pattern.search(value) for pattern in SECRET_PATTERNS)):
            fail(path or "row", "privacy")


def check_text(path, value, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value.strip():
        fail(path, "must be a non-empty string" + (" or null" if nullable else ""))


def check_run_id(path, value, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not RUN_ID.match(value):
        fail(path, "must be a run id (UUID v1-8)" + (" or null" if nullable else ""))


def check_count(path, value, minimum, maximum=None):
    if not is_count(value) or value < minimum or (maximum is not None and value > maximum):
        fail(path, f"must be an integer >= {minimum}" + (f" and <= {maximum}" if maximum is not None else ""))


def check_number(path, value):
    if not is_number(value) or value < 0:
        fail(path, "must be a finite number >= 0")


def check_list(path, value, check_item):
    if not isinstance(value, list):
        fail(path, "must be an array")
    for index, item in enumerate(value):
        check_item(f"{path}[{index}]", item)
    if len(set(map(repr, value))) != len(value):
        fail(path, "must not contain duplicate items")


def check_flag(path, value, check_value, extra=()):
    check_object(path, value, ("value", "source") + extra)
    if value["source"] not in SOURCES:
        fail(sub(path, "source"), "must be one of observed, estimated, unknown")
    if value["source"] == "unknown":
        if value["value"] is not None:
            fail(sub(path, "value"), "must be null when source is unknown")
    elif value["value"] is None:
        fail(sub(path, "value"), f"must not be null when source is {value['source']}")
    else:
        check_value(sub(path, "value"), value["value"])


def number_flag(path, value):
    check_flag(path, value, check_number)


def text_flag(path, value):
    check_flag(path, value, check_text)


def check_cost(path, value):
    check_flag(path, value, check_number, extra=("currency",))
    check_text(sub(path, "currency"), value["currency"])


def check_checks(path, value):
    def check_item(item_path, item):
        check_object(item_path, item, ("name", "exit_code"))
        check_text(sub(item_path, "name"), item["name"])
        check_count(sub(item_path, "exit_code"), item["exit_code"], 0, 255)

    if not isinstance(value, list):
        fail(path, "must be an array")
    for index, item in enumerate(value):
        check_item(f"{path}[{index}]", item)


def check_diff_size(path, value):
    check_object(path, value, ("files", "lines"))
    number_flag(sub(path, "files"), value["files"])
    number_flag(sub(path, "lines"), value["lines"])


def check_enum(allowed):
    def check(path, value):
        if value not in allowed:
            fail(path, "must be one of " + ", ".join(allowed))
    return check


def check_text_list(path, value):
    check_list(path, value, check_text)


def check_schema_version(path, value):
    if not is_count(value) or value != SCHEMA_VERSION:
        fail(path, f"must be {SCHEMA_VERSION}")


def check_bool(path, value):
    if not isinstance(value, bool):
        fail(path, "must be true or false")


CHECKS = {
    "schema_version": check_schema_version,
    "mission": check_text,
    "feature": check_text,
    "task": check_text,
    "run_id": check_run_id,
    "parent_run": lambda path, value: check_run_id(path, value, nullable=True),
    "group_id": lambda path, value: check_text(path, value, nullable=True),
    "attempt": lambda path, value: check_count(path, value, 1),
    "repair_round": lambda path, value: check_count(path, value, 0),
    "cli": check_text,
    "cli_version": text_flag,
    "door": check_text,
    "pool": check_text,
    "billing_class": check_text,
    "requested_model": text_flag,
    "resolved_model": text_flag,
    "observed_model": text_flag,
    "effort": text_flag,
    "fast_state": text_flag,
    "task_class_tags": check_text_list,
    "allow_list_size": number_flag,
    "task_text_tokens": number_flag,
    "ste_flag": check_bool,
    "active_lesson_ids": check_text_list,
    "experiment_id": lambda path, value: check_text(path, value, nullable=True),
    "wall_time_s": number_flag,
    "turns": number_flag,
    "tool_calls": number_flag,
    "tokens_input": number_flag,
    "tokens_output": number_flag,
    "tokens_cache": number_flag,
    "tokens_reasoning": number_flag,
    "cost": check_cost,
    "quota_share": number_flag,
    "checks": check_checks,
    "diff_size": check_diff_size,
    "scope_result": check_enum(SCOPE_RESULTS),
    "anti_gaming_flags": check_text_list,
    "failure_class": lambda path, value: check_text(path, value, nullable=True),
    "escalation_reason": lambda path, value: check_text(path, value, nullable=True),
    "outcome": check_enum(OUTCOMES),
}


def validate_row(row):
    """Raise LedgerError on the first contract violation; return None for a valid row."""
    check_privacy("", row)
    check_object("", row, FIELDS)
    for name in FIELDS:
        CHECKS[name](name, row[name])


def main(argv):
    if len(argv) != 2 or argv[0] != "validate":
        print("usage: ledger.py validate <file>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as handle:
            row = json.load(handle)
    except (OSError, ValueError) as error:
        print(f"ERROR: ledger: document: not readable as JSON: {error}", file=sys.stderr)
        return 1
    try:
        validate_row(row)
    except LedgerError as error:
        print(f"ERROR: ledger: {error}", file=sys.stderr)
        return 1
    print("OK: ledger row valid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
