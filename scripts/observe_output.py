#!/usr/bin/env python3
"""Observed model, usage and fast state read from a CLI's own JSON output (F003).

Only values the CLI printed are reported as observed. Everything else is unknown;
nothing is estimated, copied from the spec, or normalized between providers.
"""
import json
import sys

PROVIDERS = ("claude", "codex", "cursor", "agy")
ALIASES = {"agent": "cursor"}
USAGE_FIELDS = ("input", "output", "cache", "reasoning")


def unknown():
    return {"value": None, "source": "unknown"}


def observed(value):
    return {"value": value, "source": "observed"}


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
    return result(unknown(), usage, unknown())


def cursor(stream):
    inits = [e for e in stream if e.get("type") == "system" and e.get("subtype") == "init"]
    models = {text(e.get("model")) for e in inits}
    model = unknown()
    if inits and len(models) == 1 and None not in models:
        model = observed(models.pop())
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
        model = observed(models.pop())
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
