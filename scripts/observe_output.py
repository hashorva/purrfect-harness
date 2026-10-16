#!/usr/bin/env python3
"""Observed model, usage and fast state read from a CLI's own JSON output (F003).

Only values the CLI printed are reported as observed. Everything else is unknown;
nothing is estimated, copied from the spec, or normalized between providers.
"""
import json
import os
import re
import sys
from pathlib import Path

PROVIDERS = ("claude", "codex", "cursor", "agy")
ALIASES = {"agent": "cursor"}
USAGE_FIELDS = ("input", "output", "cache", "reasoning")
REGISTRY_PATH = Path(__file__).resolve().parent.parent / "harness-registry.json"
CODEX_THREAD_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def unknown():
    return {"value": None, "source": "unknown"}


def observed(value):
    return {"value": value, "source": "observed"}


def self_reported(value):
    return {"value": value, "source": "self_reported"}


def observe_self_reported(provider, raw):
    """Read only a well-formed self_reported_model from the final CLI answer."""
    name = ALIASES.get(provider, provider) if isinstance(provider, str) else None
    if name not in PARSERS or not isinstance(raw, bytes):
        return unknown()
    stream = events(raw)
    final_text = None
    if name in ("claude", "cursor"):
        matches = [e for e in stream if e.get("type") == "result"]
        final_text = matches[-1].get("result") if matches else None
    elif name == "agy":
        matches = [e for e in stream if e.get("event") == "result"]
        final_text = dig(matches[-1], "result", "response") if matches else None
    else:
        matches = [e for e in stream if e.get("type") == "item.completed"
                   and dig(e, "item", "type") == "agent_message"]
        if matches:
            final_text = dig(matches[-1], "item", "text")
        elif len(stream) == 1:
            final_text = raw.decode("utf-8", errors="replace")
    if not isinstance(final_text, str):
        return unknown()
    decoder = json.JSONDecoder()
    candidates = []
    pos = 0
    while True:
        start = final_text.find("{", pos)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(final_text, start)
        except (json.JSONDecodeError, RecursionError):
            pos = start + 1
            continue
        if isinstance(value, dict):
            candidates.append(value)
        pos = end
    for candidate in reversed(candidates):
        model = candidate.get("self_reported_model")
        if (isinstance(model, dict) and set(model) == {"value", "source"}
                and model.get("source") == "self_reported"
                and isinstance(model.get("value"), str) and model["value"]):
            return self_reported(model["value"])
    return unknown()


def resolve_model_identity(requested_model, observed_model, self_reported_model):
    requested_value = text(requested_model.get("value")) if isinstance(requested_model, dict) else None
    observed_value = text(observed_model.get("value")) if isinstance(observed_model, dict) else None
    reported_value = text(self_reported_model.get("value")) if isinstance(self_reported_model, dict) else None
    requested_source = requested_model.get("source", "unknown") if isinstance(requested_model, dict) else "unknown"
    observed_source = observed_model.get("source") if isinstance(observed_model, dict) else None
    reported_source = self_reported_model.get("source") if isinstance(self_reported_model, dict) else None
    drift = observed_source == "observed" and observed_value is not None and requested_source == "configured" and requested_value is not None and observed_value != requested_value
    mismatch = observed_source == "observed" and observed_value is not None and reported_source == "self_reported" and reported_value is not None and observed_value != reported_value
    flags = []
    if observed_source == "observed" and observed_value is not None:
        attributed_model, attributed_source, confidence, routing_weight = observed_value, "observed", "high", 1.0
        if drift:
            flags.append("model_drift")
    elif observed_source == "unknown" and reported_source == "self_reported" and reported_value is not None:
        attributed_model, attributed_source, confidence, routing_weight = reported_value, "self_reported", "low", 0.5
        flags.append("low_confidence_model")
    else:
        attributed_model = requested_value
        attributed_source = requested_source if requested_value else "unknown"
        confidence, routing_weight, drift, mismatch = "unknown", 0.25, False, False
    return {"attributed_model": attributed_model, "attributed_source": attributed_source,
            "confidence": confidence, "routing_weight": routing_weight, "drift": drift,
            "self_reported_mismatch": mismatch, "flags": flags}


def dig(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def text(value):
    return value if isinstance(value, str) and value else None


def count(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def field(value, check):
    checked = check(value)
    return observed(checked) if checked is not None else unknown()


def events(raw):
    parsed = []
    if not isinstance(raw, bytes):
        return parsed
    for line in raw.decode("utf-8", errors="replace").split("\n"):
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(event, dict):
            parsed.append(event)
    return parsed


def result(model, usage, fast_state):
    return {
        "observed_model": model,
        "usage": usage,
        "fast_state": fast_state,
    }


def all_unknown():
    return result(unknown(), {name: unknown() for name in USAGE_FIELDS}, unknown())


def _display_models_table(provider):
    try:
        data = json.loads(REGISTRY_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    tables = data.get("display_models")
    if not isinstance(tables, dict):
        return {}
    table = tables.get(provider)
    return table if isinstance(table, dict) else {}


def _map_display_model(provider, raw_model):
    if raw_model is None:
        return unknown()
    canonical = _display_models_table(provider).get(raw_model)
    return observed(canonical) if canonical is not None else unknown()


def _codex_sessions_dir():
    if "CODEX_SESSIONS_DIR" in os.environ:
        value = os.environ["CODEX_SESSIONS_DIR"]
        if value == "":
            return None
        return Path(value)
    return Path.home() / ".codex/sessions"


def _codex_thread_id(stream):
    thread_ids = []
    for event in stream:
        if event.get("type") != "thread.started":
            continue
        thread_id = text(event.get("thread_id"))
        if thread_id and CODEX_THREAD_ID_RE.match(thread_id):
            thread_ids.append(thread_id)
    if len(thread_ids) != 1:
        return None
    return thread_ids[0]


def _codex_session_file(thread_id):
    root = _codex_sessions_dir()
    if root is None or not root.is_dir():
        return None
    matches = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix not in (".jsonl", ".json"):
            continue
        if thread_id in path.name:
            matches.append(path)
    if len(matches) != 1:
        return None
    return matches[0]


def _codex_model_from_session(path):
    models = set()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(obj, dict):
            continue
        model = text(obj.get("model")) or text(dig(obj, "payload", "model"))
        if model:
            models.add(model)
    if len(models) == 1:
        return next(iter(models))
    return None


def _codex_observed_model(stream):
    thread_id = _codex_thread_id(stream)
    if thread_id is None:
        return unknown()
    session_file = _codex_session_file(thread_id)
    if session_file is None:
        return unknown()
    model = _codex_model_from_session(session_file)
    return observed(model) if model else unknown()


def claude(stream):
    results = [e for e in stream if e.get("type") == "result"]
    if not results:
        return all_unknown()
    last = results[-1]
    model_usage = last.get("modelUsage")
    model = None
    if isinstance(model_usage, dict) and len(model_usage) == 1:
        model = text(next(iter(model_usage)))
    usage = {
        "input": field(dig(last, "usage", "input_tokens"), count),
        "output": field(dig(last, "usage", "output_tokens"), count),
        "cache": field(dig(last, "usage", "cache_read_input_tokens"), count),
        "reasoning": field(dig(last, "usage", "output_tokens_details", "thinking_tokens"), count),
    }
    return result(field(model, text), usage, field(last.get("fast_mode_state"), text))


def codex(stream):
    turns = [e for e in stream if e.get("type") == "turn.completed"]

    def total(*keys):
        if not turns:
            return unknown()
        sum_ = 0
        for turn in turns:
            value = count(dig(turn, "usage", *keys))
            if value is None:
                return unknown()
            sum_ += value
        return observed(sum_)

    usage = {
        "input": total("input_tokens"),
        "output": total("output_tokens"),
        "cache": total("cached_input_tokens"),
        "reasoning": total("reasoning_output_tokens"),
    }
    return result(_codex_observed_model(stream), usage, unknown())


def cursor(stream):
    inits = [e for e in stream if e.get("type") == "system" and e.get("subtype") == "init"]
    models = {text(e.get("model")) for e in inits}
    model = unknown()
    if inits and len(models) == 1 and None not in models:
        model = _map_display_model("cursor", models.pop())
    results = [e for e in stream if e.get("type") == "result"]
    last = results[-1] if results else {}
    usage = {
        "input": field(dig(last, "usage", "inputTokens"), count),
        "output": field(dig(last, "usage", "outputTokens"), count),
        "cache": field(dig(last, "usage", "cacheReadTokens"), count),
        "reasoning": unknown(),
    }
    return result(model, usage, unknown())


def agy(stream):
    inits = [e for e in stream if e.get("event") == "init"]
    models = {text(dig(e, "init", "model")) for e in inits}
    model = unknown()
    if inits and len(models) == 1 and None not in models:
        model = _map_display_model("agy", models.pop())
    results = [e for e in stream if e.get("event") == "result"]
    last = results[-1] if results else {}
    usage = {
        "input": field(dig(last, "result", "usage", "input_tokens"), count),
        "output": field(dig(last, "result", "usage", "output_tokens"), count),
        "cache": field(dig(last, "result", "usage", "cache_read_tokens"), count),
        "reasoning": field(dig(last, "result", "usage", "thinking_tokens"), count),
    }
    return result(model, usage, unknown())


PARSERS = {"claude": claude, "codex": codex, "cursor": cursor, "agy": agy}


def observe(provider, raw):
    name = ALIASES.get(provider, provider) if isinstance(provider, str) else None
    if name not in PARSERS:
        raise ValueError(f"unknown provider: {provider!r}")
    return PARSERS[name](events(raw))


def zero_tokens(usage):
    return usage["input"] == observed(0) and usage["output"] == observed(0)


def agy_no_turn(stream):
    """Return whether agy ran no turn; agy reports SUCCESS on a no-turn run, so status alone is not trusted."""
    if not any(e.get("event") == "init" for e in stream):
        return False
    results = [e for e in stream if e.get("event") == "result"]
    if not results:
        return True
    last_result = results[-1].get("result")
    if not isinstance(last_result, dict) or last_result.get("status") != "SUCCESS":
        return True
    turns = last_result.get("num_turns")
    if isinstance(turns, bool) or not isinstance(turns, int) or turns == 0:
        return True
    response = last_result.get("response")
    if not isinstance(response, str) or not response.strip():
        return True
    return zero_tokens(agy(stream)["usage"])


def no_turn(provider, raw):
    """True only on positive evidence in the CLI's own output that no turn ran."""
    name = ALIASES.get(provider, provider) if isinstance(provider, str) else None
    if name not in PARSERS:
        raise ValueError(f"unknown provider: {provider!r}")
    if name == "agy":
        return agy_no_turn(events(raw))
    stream = events(raw)
    if name == "claude":
        results = [e for e in stream if e.get("type") == "result"]
        turns = results[-1].get("num_turns") if results else None
        if isinstance(turns, int) and not isinstance(turns, bool) and turns == 0:
            return True
    if name == "codex" and stream and not any(e.get("type") == "turn.completed" for e in stream):
        return True
    return zero_tokens(PARSERS[name](stream)["usage"])


def main(argv):
    if len(argv) != 3:
        print("usage: observe_output.py <provider> <file>", file=sys.stderr)
        return 2
    try:
        with open(argv[2], "rb") as handle:
            observed_output = observe(argv[1], handle.read())
    except (OSError, ValueError) as exc:
        print(f"observe_output: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(observed_output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
