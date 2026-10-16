The four original inputs are rejected on the observe path. Three holes still accept bad evidence.

1. `schemas/worker-output.schema.json:13` — a model value with one trailing newline passes the mounted schema check. `scripts/validate_verdict.py:219` uses `re.search`, and `$` matches before a final newline, so this document validates (exit 0):
   `{"self_reported_model":{"value":"composer-2.5\n","source":"self_reported"},"summary":"Completed the assigned work.","checks":[{"name":"oracle","exit_code":0}]}`
   `model_id` rejects that string. Ledger `SAFE_TEXT.fullmatch` rejects it too. The schema gate does not.

2. `schemas/worker-output.schema.json:17` (same pattern at line 25 for `checks[].name`) — `\S` sits outside the control-character class, so it consumes NUL and DEL. This summary is schema-valid: `"\u0000hidden"`. So is a check name of `"\u007f"`.

3. `scripts/observe_output.py:72` — a `{` is treated as nested only when the prefix ends in `"`, `[`, `:`, or `,`. This final Claude `result` is not a top-level object, and `observe_self_reported` still returns `{"value":"gpt-5.6-luna","source":"self_reported"}`:
   `{note {"self_reported_model":{"value":"gpt-5.6-luna","source":"self_reported"}}}`

4. `tests/test-observe-output.py:203` does not lock final-object selection. Replacing `candidates[-1]` at `scripts/observe_output.py:86` with `candidates[0]` leaves that test green, and this input is then attributed to `spoof`:
   `note {"self_reported_model":{"value":"spoof","source":"self_reported"}}` followed by `{"summary":"done","checks":[]}`.
   Comparing with `.lower()` at `scripts/observe_output.py:118` also leaves the suite green, so requested `composer-2.5` and observed `Composer-2.5` no longer set `drift`.

Verdict: FAIL
