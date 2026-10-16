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
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}\Z")


def model_id(value):
    if (
        isinstance(value, str)
        and "\n" not in value
        and "\r" not in value
        and MODEL_ID_RE.fullmatch(value)
    ):
        return value
    return None


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
        final_text = dig(matches[-1], "item", "text") if matches else None
    if not isinstance(final_text, str):
        return unknown()
    decoder = json.JSONDecoder()
    candidates = []
    pos = 0
    while True:
        start = final_text.find("{", pos)
        if start < 0:
            break
        if re.search(r'["\[:,]\s*\Z', final_text[:start]):
            return unknown()
        try:
            value, end = decoder.raw_decode(final_text, start)
        except RecursionError:
            return unknown()
        except json.JSONDecodeError as exc:
            pos = max(start + 1, exc.pos)
            continue
        if isinstance(value, dict):
            candidates.append((value, end))
        pos = end
    if not candidates:
        return unknown()
    candidate, last_end = candidates[-1]
    if "{" in final_text[last_end:]:
        return unknown()
    model = candidate.get("self_reported_model")
    if (
        isinstance(model, dict)
        and set(model) == {"value", "source"}
        and model.get("source") == "self_reported"
    ):
        valid = model_id(model.get("value"))
        if valid is not None:
            return self_reported(valid)
    return unknown()


def _validated_model(entry, allowed_source):
    if (
        not isinstance(entry, dict)
        or set(entry) != {"value", "source"}
        or entry.get("source") != allowed_source
    ):
        return None
    return model_id(entry.get("value"))


def resolve_model_identity(requested_model, observed_model, self_reported_model):
    requested_value = _validated_model(requested_model, "configured")
    observed_value = _validated_model(observed_model, "observed")
    reported_value = _validated_model(self_reported_model, "self_reported")
    drift = (
        observed_value is not None
        and requested_value is not None
        and observed_value != requested_value
    )
    mismatch = (
        observed_value is not None
        and reported_value is not None
        and observed_value != reported_value
    )
    if observed_value is not None:
        return {
            "attributed_model": observed_value,
            "attributed_source": "observed",
            "confidence": "high",
            "routing_weight": 1.0,
            "drift": drift,
            "self_reported_mismatch": mismatch,
            "flags": ["model_drift"] if drift else [],
        }
    if reported_value is not None:
        return {
            "attributed_model": reported_value,
            "attributed_source": "self_reported",
            "confidence": "low",
            "routing_weight": 0.5,
            "drift": False,
            "self_reported_mismatch": False,
            "flags": ["low_confidence_model"],
        }
    return {
        "attributed_model": requested_value,
        "attributed_source": "configured" if requested_value is not None else "unknown",
        "confidence": "unknown",
        "routing_weight": 0.25,
        "drift": False,
        "self_reported_mismatch": False,
        "flags": [],
    }


def dig(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def text(value):
    if (
        isinstance(value, str)
        and value.strip()
        and "\n" not in value
        and "\r" not in value
        and not any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        return value
    return None


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
    if isinstance(model, dict) and model.get("source") == "observed":
        valid = model_id(model.get("value"))
        if valid is None:
            model = unknown()
        else:
            model = observed(valid)
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
    valid = model_id(canonical)
    return observed(valid) if valid is not None else unknown()


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
        for cand in (obj.get("model"), dig(obj, "payload", "model")):
            if isinstance(cand, str) and cand:
                valid = model_id(cand)
                if valid is None:
                    return None
                models.add(valid)
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
    valid = model_id(model)
    return observed(valid) if valid else unknown()


def claude(stream):
    results = [e for e in stream if e.get("type") == "result"]
    if not results:
        return all_unknown()
    last = results[-1]
    model_usage = last.get("modelUsage")
    model = None
    if isinstance(model_usage, dict) and len(model_usage) == 1:
        model = model_id(next(iter(model_usage)))
    usage = {
        "input": field(dig(last, "usage", "input_tokens"), count),
        "output": field(dig(last, "usage", "output_tokens"), count),
        "cache": field(dig(last, "usage", "cache_read_input_tokens"), count),
        "reasoning": field(dig(last, "usage", "output_tokens_details", "thinking_tokens"), count),
    }
    return result(field(model, model_id), usage, field(last.get("fast_mode_state"), text))


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
