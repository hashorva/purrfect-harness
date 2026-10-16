#!/usr/bin/env python3
"""Observed model, usage and fast state: expected results are literal, not computed by the parser."""
import inspect
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/observe"
sys.path.insert(0, str(ROOT / "scripts"))
from observe_output import no_turn, observe


UNKNOWN = {"value": None, "source": "unknown"}

ALL_UNKNOWN = {
    "observed_model": {"value": None, "source": "unknown"},
    "usage": {
        "input": {"value": None, "source": "unknown"},
        "output": {"value": None, "source": "unknown"},
        "cache": {"value": None, "source": "unknown"},
        "reasoning": {"value": None, "source": "unknown"},
    },
    "fast_state": {"value": None, "source": "unknown"},
}

CLAUDE = {
    "observed_model": {"value": "claude-haiku-5-5", "source": "observed"},
    "usage": {
        "input": {"value": 2, "source": "observed"},
        "output": {"value": 33, "source": "observed"},
        "cache": {"value": 19995, "source": "observed"},
        "reasoning": {"value": 29, "source": "observed"},
    },
    "fast_state": {"value": "off", "source": "observed"},
}

CLAUDE_TWO_MODELS = {
    "observed_model": {"value": None, "source": "unknown"},
    "usage": CLAUDE["usage"],
    "fast_state": {"value": "off", "source": "observed"},
}

CODEX = {
    "observed_model": {"value": None, "source": "unknown"},
    "usage": {
        "input": {"value": 17685, "source": "observed"},
        "output": {"value": 5, "source": "observed"},
        "cache": {"value": 12032, "source": "observed"},
        "reasoning": {"value": 0, "source": "observed"},
    },
    "fast_state": {"value": None, "source": "unknown"},
}

CODEX_TWO_TURNS = {
    "observed_model": {"value": None, "source": "unknown"},
    "usage": {
        "input": {"value": 35370, "source": "observed"},
        "output": {"value": 10, "source": "observed"},
        "cache": {"value": 24064, "source": "observed"},
        "reasoning": {"value": 0, "source": "observed"},
    },
    "fast_state": {"value": None, "source": "unknown"},
}

CURSOR = {
    "observed_model": {"value": "Composer 2.5", "source": "observed"},
    "usage": {
        "input": {"value": 8961, "source": "observed"},
        "output": {"value": 23, "source": "observed"},
        "cache": {"value": 3878, "source": "observed"},
        "reasoning": {"value": None, "source": "unknown"},
    },
    "fast_state": {"value": None, "source": "unknown"},
}

CURSOR_NO_INIT_MODEL = {
    "observed_model": {"value": None, "source": "unknown"},
    "usage": CURSOR["usage"],
    "fast_state": {"value": None, "source": "unknown"},
}

EXPECTED = {
    ("claude", "claude.json"): CLAUDE,
    ("claude", "claude-log.txt"): CLAUDE,
    ("claude", "claude-two-models.json"): CLAUDE_TWO_MODELS,
    ("codex", "codex.jsonl"): CODEX,
    ("codex", "codex-two-turns.jsonl"): CODEX_TWO_TURNS,
    ("cursor", "cursor.jsonl"): CURSOR,
    ("cursor", "cursor-no-init-model.jsonl"): CURSOR_NO_INIT_MODEL,
}

ALL_FIXTURES = [
    "claude.json", "claude-log.txt", "claude-two-models.json",
    "codex.jsonl", "codex-two-turns.jsonl",
    "cursor.jsonl", "cursor-no-init-model.jsonl",
    "wrong-types.jsonl", "empty.txt", "garbage.txt",
]

HOSTILE = ["wrong-types.jsonl", "empty.txt", "garbage.txt"]


def read(name):
    return (FIXTURES / name).read_bytes()


class ObserveOutputTest(unittest.TestCase):
    def test_provider_fixtures_match_literal_expectations(self):
        for (provider, name), expected in EXPECTED.items():
            with self.subTest(provider=provider, fixture=name):
                self.assertEqual(observe(provider, read(name)), expected)

    def test_agy_is_all_unknown_on_every_fixture(self):
        for name in ALL_FIXTURES:
            with self.subTest(fixture=name):
                self.assertEqual(observe("agy", read(name)), ALL_UNKNOWN)

    def test_every_provider_is_all_unknown_on_hostile_input(self):
        for provider in ("claude", "codex", "cursor", "agy"):
            for name in HOSTILE:
                with self.subTest(provider=provider, fixture=name):
                    self.assertEqual(observe(provider, read(name)), ALL_UNKNOWN)

    def test_deleted_model_usage_gives_unknown_model(self):
        doc = json.loads(read("claude.json"))
        del doc["modelUsage"]
        raw = json.dumps(doc).encode()
        self.assertEqual(observe("claude", raw), {**CLAUDE, "observed_model": UNKNOWN})

    def test_no_turn_needs_positive_evidence_from_the_cli_output(self):
        for provider, name in (("claude", "claude-zero-turns.json"), ("codex", "codex-no-turn.jsonl"),
                               ("cursor", "cursor-zero-tokens.jsonl"), ("agent", "cursor-zero-tokens.jsonl")):
            with self.subTest(provider=provider, fixture=name):
                self.assertIs(no_turn(provider, read(name)), True)
        for provider, name in (("claude", "claude.json"), ("claude", "claude-log.txt"),
                               ("codex", "codex.jsonl"), ("codex", "codex-two-turns.jsonl"),
                               ("cursor", "cursor.jsonl")):
            with self.subTest(provider=provider, fixture=name):
                self.assertIs(no_turn(provider, read(name)), False)
        for name in ALL_FIXTURES + ["claude-zero-turns.json", "codex-no-turn.jsonl", "cursor-zero-tokens.jsonl"]:
            with self.subTest(provider="agy", fixture=name):
                self.assertIs(no_turn("agy", read(name)), False)
        for provider in ("claude", "codex", "cursor", "agent", "agy"):
            for name in HOSTILE:
                with self.subTest(provider=provider, fixture=name):
                    self.assertIs(no_turn(provider, read(name)), False)
        with self.assertRaises(ValueError):
            no_turn("gemini", b"")

    def test_agent_alias_matches_cursor(self):
        self.assertEqual(observe("agent", read("cursor.jsonl")), CURSOR)
        self.assertEqual(observe("agent", read("cursor.jsonl")), observe("cursor", read("cursor.jsonl")))

    def test_unknown_provider_raises(self):
        for provider in ("gemini", "Claude", None):
            with self.subTest(provider=provider):
                with self.assertRaises(ValueError):
                    observe(provider, read("claude.json"))

    def test_signature_is_provider_and_raw(self):
        self.assertEqual(list(inspect.signature(observe).parameters), ["provider", "raw"])

    def test_cli_prints_canonical_json_for_cursor(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/observe_output.py"), "cursor", str(FIXTURES / "cursor.jsonl")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            json.dumps(CURSOR, sort_keys=True, separators=(",", ":")) + "\n",
        )


if __name__ == "__main__":
    unittest.main()
