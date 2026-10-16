#!/usr/bin/env python3
"""Observed model, usage and fast state: expected results are literal, not computed by the parser."""
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/observe"
sys.path.insert(0, str(ROOT / "scripts"))
from observe_output import no_turn, observe, observe_self_reported, resolve_model_identity


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
    "observed_model": {"value": "composer-2.5", "source": "observed"},
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

AGY = {
    "observed_model": {"value": "gemini-3.8-flash-low", "source": "observed"},
    "usage": {
        "input": {"value": 15015, "source": "observed"},
        "output": {"value": 1, "source": "observed"},
        "cache": {"value": 0, "source": "observed"},
        "reasoning": {"value": 0, "source": "observed"},
    },
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
    def setUp(self):
        self._codex_sessions_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._codex_sessions_dir.cleanup)
        prev_codex_sessions_dir = os.environ.get("CODEX_SESSIONS_DIR")
        os.environ["CODEX_SESSIONS_DIR"] = self._codex_sessions_dir.name

        def restore_codex_sessions_dir():
            if prev_codex_sessions_dir is None:
                os.environ.pop("CODEX_SESSIONS_DIR", None)
            else:
                os.environ["CODEX_SESSIONS_DIR"] = prev_codex_sessions_dir

        self.addCleanup(restore_codex_sessions_dir)

    def test_provider_fixtures_match_literal_expectations(self):
        for (provider, name), expected in EXPECTED.items():
            with self.subTest(provider=provider, fixture=name):
                self.assertEqual(observe(provider, read(name)), expected)

    def test_observe_self_reported_never_accepts_observed_source(self):
        payload = {"self_reported_model": {"value": "gpt-5.6-luna", "source": "self_reported"}}
        for provider, event in (
            ("claude", {"type": "result", "result": json.dumps(payload)}),
            ("cursor", {"type": "result", "result": "```json\n" + json.dumps(payload) + "\n```"}),
            ("agy", {"event": "result", "result": {"response": json.dumps(payload)}}),
            ("codex", {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(payload)}}),
            ("codex", payload),
        ):
            with self.subTest(provider=provider):
                raw = json.dumps(event).encode()
                self.assertEqual(observe_self_reported(provider, raw),
                                 {"value": "gpt-5.6-luna", "source": "self_reported"})
                for source in ("observed", "configured", "estimated", "unknown"):
                    bad = json.loads(json.dumps(payload))
                    bad["self_reported_model"]["source"] = source
                    wrapped = dict(event)
                    if provider in ("claude", "cursor"):
                        wrapped["result"] = json.dumps(bad)
                    elif provider == "agy":
                        wrapped["result"]["response"] = json.dumps(bad)
                    elif provider == "codex" and "item" in wrapped:
                        wrapped["item"]["text"] = json.dumps(bad)
                    else:
                        wrapped = bad
                    self.assertEqual(observe_self_reported(provider, json.dumps(wrapped).encode()), UNKNOWN)
        empty = {"self_reported_model": {"value": "", "source": "self_reported"}}
        raw = json.dumps({"type": "result", "result": json.dumps(empty)}).encode()
        self.assertEqual(observe_self_reported("claude", raw), UNKNOWN)

    def test_resolve_model_identity_four_rules(self):
        req = {"value": "claude-haiku-5-5", "source": "configured"}
        obs_diff = {"value": "claude-sonnet-5-5", "source": "observed"}
        obs_same = {"value": "claude-haiku-5-5", "source": "observed"}
        unk = dict(UNKNOWN)
        sr = {"value": "gpt-5.6-luna", "source": "self_reported"}
        inputs = json.loads(json.dumps([req, obs_diff, obs_same, unk, sr]))
        self.assertEqual(resolve_model_identity(req, obs_diff, unk), {
            "attributed_model": "claude-sonnet-5-5", "attributed_source": "observed",
            "confidence": "high", "routing_weight": 1.0, "drift": True,
            "self_reported_mismatch": False, "flags": ["model_drift"]})
        self.assertEqual(resolve_model_identity(req, unk, sr), {
            "attributed_model": "gpt-5.6-luna", "attributed_source": "self_reported",
            "confidence": "low", "routing_weight": 0.5, "drift": False,
            "self_reported_mismatch": False, "flags": ["low_confidence_model"]})
        self.assertEqual(resolve_model_identity(req, unk, unk), {
            "attributed_model": "claude-haiku-5-5", "attributed_source": "configured",
            "confidence": "unknown", "routing_weight": 0.25, "drift": False,
            "self_reported_mismatch": False, "flags": []})
        mismatch = resolve_model_identity(req, obs_same, sr)
        self.assertEqual(mismatch["attributed_model"], "claude-haiku-5-5")
        self.assertEqual(mismatch["confidence"], "high")
        self.assertEqual(mismatch["routing_weight"], 1.0)
        self.assertFalse(mismatch["drift"])
        self.assertTrue(mismatch["self_reported_mismatch"])
        self.assertEqual(mismatch["flags"], [])
        self.assertEqual([req, obs_diff, obs_same, unk, sr], inputs)

    def test_agy_is_all_unknown_on_every_fixture(self):
        for name in ALL_FIXTURES:
            with self.subTest(fixture=name):
                self.assertEqual(observe("agy", read(name)), ALL_UNKNOWN)

    def test_agy_observes_recorded_stream_and_last_result(self):
        raw = read("agy.jsonl")
        self.assertEqual(observe("agy", raw), AGY)
        self.assertFalse(no_turn("agy", raw))
        for provider in ("claude", "codex", "cursor"):
            with self.subTest(provider=provider):
                self.assertEqual(observe(provider, raw), ALL_UNKNOWN)
        lines = raw.decode().splitlines()
        last = json.loads(lines[-1])
        last["result"]["usage"] = {"input_tokens": 4, "output_tokens": 3,
                                     "cache_read_tokens": 2, "thinking_tokens": 1}
        stream = "\n".join(lines + [json.dumps(last)]).encode()
        self.assertEqual(
            {key: value["value"] for key, value in observe("agy", stream)["usage"].items()},
            {"input": 4, "output": 3, "cache": 2, "reasoning": 1},
        )

    def test_agy_model_requires_one_nonempty_init_model(self):
        raw = read("agy.jsonl").decode().splitlines()
        no_model = json.loads(raw[0])
        del no_model["init"]["model"]
        self.assertEqual(observe("agy", (json.dumps(no_model) + "\n" + raw[-1]).encode())["observed_model"], UNKNOWN)
        other = json.loads(raw[0])
        other["init"]["model"] = "gemini-3.8-flash-high"
        stream = (raw[0] + "\n" + json.dumps(other) + "\n" + raw[-1]).encode()
        self.assertEqual(observe("agy", stream)["observed_model"], UNKNOWN)

    def test_agy_no_turn_failure_shapes(self):
        init, result = read("agy.jsonl").decode().splitlines()[0], json.loads(read("agy.jsonl").decode().splitlines()[-1])
        cases = {
            "no result": init + "\n",
            "result not object": init + "\n" + json.dumps({"event": "result", "result": []}) + "\n",
            "not success": init + "\n" + json.dumps({"event": "result", "result": {"status": "FAILURE"}}) + "\n",
            "bad turns": init + "\n" + json.dumps({"event": "result", "result": {"status": "SUCCESS", "num_turns": True, "response": "OK"}}) + "\n",
            "zero turns": init + "\n" + json.dumps({"event": "result", "result": {"status": "SUCCESS", "num_turns": 0, "response": "OK"}}) + "\n",
            "empty response": init + "\n" + json.dumps({"event": "result", "result": {"status": "SUCCESS", "num_turns": 1, "response": " "}}) + "\n",
            "zero tokens": init + "\n" + json.dumps({"event": "result", "result": {"status": "SUCCESS", "num_turns": 1, "response": "OK", "usage": {"input_tokens": 0, "output_tokens": 0}}}) + "\n",
        }
        for name, raw in cases.items():
            with self.subTest(shape=name):
                self.assertTrue(no_turn("agy", raw.encode()))

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

    def test_no_turn_zero_tokens_and_turns_combinations(self):
        raw = read("claude-zero-turns.json")
        doc = json.loads(raw)
        self.assertEqual(doc["num_turns"], 0)
        observed_claude = observe("claude", raw)
        self.assertEqual(observed_claude["usage"]["input"], {"value": 2, "source": "observed"})
        self.assertEqual(observed_claude["usage"]["output"], {"value": 33, "source": "observed"})
        self.assertTrue(no_turn("claude", raw))

        def r(data):
            return (json.dumps(data) + "\n").encode()

        # claude
        self.assertTrue(no_turn("claude", r({"type": "result", "num_turns": 1, "usage": {"input_tokens": 0, "output_tokens": 0}})))
        self.assertTrue(no_turn("claude", r({"type": "result", "num_turns": 0, "usage": {"input_tokens": 2, "output_tokens": 33}})))
        self.assertFalse(no_turn("claude", r({"type": "result", "num_turns": 1, "usage": {"input_tokens": 0, "output_tokens": 5}})))
        self.assertFalse(no_turn("claude", r({"type": "result", "num_turns": 1, "usage": {"input_tokens": 5, "output_tokens": 0}})))
        self.assertFalse(no_turn("claude", r({"type": "result", "num_turns": False, "usage": {"input_tokens": 5, "output_tokens": 5}})))

        # codex
        self.assertTrue(no_turn("codex", r({"type": "turn.completed", "usage": {"input_tokens": 0, "output_tokens": 0}})))
        self.assertFalse(no_turn("codex", r({"type": "turn.completed", "usage": {"input_tokens": 0, "output_tokens": 5}})))
        self.assertFalse(no_turn("codex", r({"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 0}})))

        # cursor and agent
        for provider in ("cursor", "agent"):
            with self.subTest(provider=provider):
                self.assertTrue(no_turn(provider, r({"type": "result", "usage": {"inputTokens": 0, "outputTokens": 0}})))
                self.assertFalse(no_turn(provider, r({"type": "result", "usage": {"inputTokens": 0, "outputTokens": 5}})))
                self.assertFalse(no_turn(provider, r({"type": "result", "usage": {"inputTokens": 5, "outputTokens": 0}})))

        # agy
        def agy_stream(num_turns, inp, out):
            init = {"event": "init"}
            res = {
                "event": "result",
                "result": {
                    "status": "SUCCESS",
                    "num_turns": num_turns,
                    "response": "OK",
                    "usage": {"input_tokens": inp, "output_tokens": out},
                },
            }
            return (json.dumps(init) + "\n" + json.dumps(res) + "\n").encode()

        self.assertTrue(no_turn("agy", agy_stream(1, 0, 0)))
        self.assertFalse(no_turn("agy", agy_stream(1, 0, 1)))
        self.assertFalse(no_turn("agy", agy_stream(1, 15015, 0)))
        self.assertTrue(no_turn("agy", agy_stream(0, 15015, 1)))

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
            env={**os.environ, "CODEX_SESSIONS_DIR": self._codex_sessions_dir.name},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            json.dumps(CURSOR, sort_keys=True, separators=(",", ":")) + "\n",
        )

    def test_codex_session_record_reads_only_model_from_fake_sessions_dir(self):
        tid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        raw = (
            json.dumps({"type": "thread.started", "thread_id": tid})
            + "\n"
            + json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cached_input_tokens": 0,
                        "reasoning_output_tokens": 0,
                    },
                }
            )
            + "\n"
        ).encode()
        sessions = Path(self._codex_sessions_dir.name)
        sub = sessions / "2026" / "10" / "16"
        sub.mkdir(parents=True)
        rollout = sub / f"rollout-{tid}.jsonl"
        for bad in (
            {
                "model": "gpt-5.6-luna\n/Users/secret\u0000sk-abcdefghijklmnopqrstuvwxyz",
                "cwd": "/Users/secret",
                "instructions": "do not leak",
            },
            {"model": "a" * 200},
            {"model": "gpt-5.6-luna\n"},
        ):
            with self.subTest(bad=bad):
                rollout.write_text(json.dumps(bad) + "\n", encoding="utf-8")
                obs = observe("codex", raw)
                self.assertEqual(obs["observed_model"], UNKNOWN)
                dumped = json.dumps(obs)
                self.assertNotIn("/Users/secret", dumped)
                self.assertNotIn("sk-", dumped)
                self.assertNotIn("do not leak", dumped)

        rollout.write_text(
            json.dumps(
                {
                    "type": "turn_context",
                    "payload": {
                        "model": "gpt-5.6-luna",
                        "cwd": "/Users/secret",
                        "instructions": "do not leak",
                        "rollout_path": "/secret/path",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        obs = observe("codex", raw)
        self.assertEqual(obs["observed_model"], {"value": "gpt-5.6-luna", "source": "observed"})
        self.assertNotIn("/Users/secret", json.dumps(obs))
        self.assertNotIn("do not leak", json.dumps(obs))

        top_level = sub / f"session-{tid}.jsonl"
        top_level.write_text(json.dumps({"model": "gpt-5.6-luna"}) + "\n", encoding="utf-8")
        rollout.unlink()
        self.assertEqual(
            observe("codex", raw)["observed_model"],
            {"value": "gpt-5.6-luna", "source": "observed"},
        )

        top_level.unlink()
        self.assertEqual(observe("codex", raw)["observed_model"], UNKNOWN)

        other = sub / f"other-{tid}-copy.jsonl"
        rollout.write_text(
            json.dumps({"payload": {"model": "gpt-5.6-luna"}}) + "\n", encoding="utf-8"
        )
        other.write_text(json.dumps({"payload": {"model": "gpt-5.6-luna"}}) + "\n", encoding="utf-8")
        self.assertEqual(observe("codex", raw)["observed_model"], UNKNOWN)
        other.unlink()

        rollout.write_text(
            json.dumps({"payload": {"model": "gpt-5.6-luna"}})
            + "\n"
            + json.dumps({"payload": {"model": "gpt-5.6-other"}})
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(observe("codex", raw)["observed_model"], UNKNOWN)

        rollout.unlink()
        other.unlink(missing_ok=True)
        backing = sub / "backing.jsonl"
        backing.write_text(json.dumps({"payload": {"model": "gpt-5.6-luna"}}) + "\n", encoding="utf-8")
        rollout.symlink_to(backing)
        self.assertEqual(observe("codex", raw)["observed_model"], UNKNOWN)

        bad_tid = (
            json.dumps({"type": "thread.started", "thread_id": "not-a-uuid"})
            + "\n"
            + json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cached_input_tokens": 0,
                        "reasoning_output_tokens": 0,
                    },
                }
            )
            + "\n"
        ).encode()
        rollout.unlink(missing_ok=True)
        backing.unlink(missing_ok=True)
        self.assertEqual(observe("codex", bad_tid)["observed_model"], UNKNOWN)

    def test_cursor_and_agy_map_display_names_and_refuse_unknown_display_names(self):
        cursor_ok = json.dumps(
            {"type": "system", "subtype": "init", "model": "Composer 2.5"}
        ).encode()
        self.assertEqual(
            observe("cursor", cursor_ok)["observed_model"],
            {"value": "composer-2.5", "source": "observed"},
        )
        grok_ok = json.dumps(
            {"type": "system", "subtype": "init", "model": "Grok 4.7 256K High"}
        ).encode()
        self.assertEqual(
            observe("cursor", grok_ok)["observed_model"],
            {"value": "grok-4.7-high", "source": "observed"},
        )
        for unknown_name in ("Composer 9.9", "Grok Mystery"):
            raw = json.dumps(
                {"type": "system", "subtype": "init", "model": unknown_name}
            ).encode()
            self.assertEqual(observe("cursor", raw)["observed_model"], UNKNOWN)

        agy_ok = json.dumps(
            {"event": "init", "init": {"model": "Gemini 4 Argon (High)"}}
        ).encode()
        self.assertEqual(
            observe("agy", agy_ok)["observed_model"],
            {"value": "gemini-4-argon-high", "source": "observed"},
        )
        agy_unk = json.dumps({"event": "init", "init": {"model": "Unknown Agy Display"}}).encode()
        self.assertEqual(observe("agy", agy_unk)["observed_model"], UNKNOWN)

    def test_codex_sessions_dir_isolation_and_home_fallback(self):
        fixture_bytes = read("codex.jsonl")
        fixture_tid = [
            json.loads(line)["thread_id"]
            for line in fixture_bytes.decode().splitlines()
            if json.loads(line).get("type") == "thread.started"
        ][0]
        prev_home = os.environ.get("HOME")
        prev_sessions = os.environ.get("CODEX_SESSIONS_DIR")
        try:
            with tempfile.TemporaryDirectory() as fake_home, tempfile.TemporaryDirectory() as empty_dir:
                home_sessions = Path(fake_home) / ".codex" / "sessions"
                home_sessions.mkdir(parents=True)
                (home_sessions / f"rollout-{fixture_tid}.jsonl").write_text(
                    json.dumps({"model": "SHOULD-NOT-BE-READ"}) + "\n",
                    encoding="utf-8",
                )
                os.environ["HOME"] = fake_home

                # Variant 1 (production fallback): with HOME pointing at fake_home and CODEX_SESSIONS_DIR unset
                os.environ.pop("CODEX_SESSIONS_DIR", None)
                obs_fallback = observe("codex", fixture_bytes)
                self.assertEqual(
                    obs_fallback["observed_model"],
                    {"value": "SHOULD-NOT-BE-READ", "source": "observed"},
                )

                # Variant 2 (test isolation): with HOME still pointing at fake_home and CODEX_SESSIONS_DIR set to empty dir
                os.environ["CODEX_SESSIONS_DIR"] = empty_dir
                obs_isolated = observe("codex", fixture_bytes)
                self.assertEqual(obs_isolated["observed_model"], UNKNOWN)
                self.assertNotIn("SHOULD-NOT-BE-READ", json.dumps(obs_isolated))
        finally:
            if prev_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = prev_home
            if prev_sessions is None:
                os.environ.pop("CODEX_SESSIONS_DIR", None)
            else:
                os.environ["CODEX_SESSIONS_DIR"] = prev_sessions

    def test_claude_model_id_validation(self):
        doc = json.loads(read("claude.json"))
        for bad_model in ("claude-haiku-5-5\n/secret", "a" * 200, "claude-haiku-5-5\n"):
            with self.subTest(bad_model=bad_model):
                doc["modelUsage"] = {bad_model: {"inputTokens": 2, "outputTokens": 33}}
                raw = json.dumps(doc).encode()
                obs = observe("claude", raw)
                self.assertEqual(obs["observed_model"], UNKNOWN)
                self.assertNotIn("/secret", json.dumps(obs))


if __name__ == "__main__":
    unittest.main()
