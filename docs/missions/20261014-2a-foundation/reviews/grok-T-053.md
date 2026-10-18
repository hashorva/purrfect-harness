`scripts/fleet_state.py:209` — `choose(["not-gemini-4-argon-high"], "argon")` returns `not-gemini-4-argon-high`; listed first it also wins the tie against `gemini-4-argon-high`.
`schemas/fleet-inventory.schema.json:9` — pattern matches `argon\n` (ECMA-262 `$` before a trailing newline), `sk-ant-api03-abcdefghijklmnopqrstuvwxyz`, and `ghp_abcdefghijklmnopqrstuvwxyz0123456789`.
`scripts/harness_registry.py:183` — `FAMILY_RE.fullmatch` accepts those same `sk-ant-api03-…` and `ghp_…` family strings.
Verdict: FAIL
