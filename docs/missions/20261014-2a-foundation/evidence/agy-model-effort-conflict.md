# Evidence: agy rejects a model name that already encodes effort plus `--effort` (2026-10-15)

Source: night 2 real seat smoke S1 (`bash scripts/fleet-doctor.sh --smoke ... --seat agy.economy`),
run id `3e16e5ea-3102-47fb-b6f4-c769b012f4d8` in the scratch clone. Frozen seat `agy.economy`:
model `gemini-3.8-flash-high`, effort `medium`, speed `unknown`.

The v3 adapter builds `agy ... --model gemini-3.8-flash-high --effort medium`. `agy` exits 1 before
any work, with this message (verbatim, from the kept transcript):

```text
error: invalid model selection (--model "gemini-3.8-flash-high" --effort "medium"): --model gemini-3.8-flash-high conflicts with --effort=medium
```

Conclusion: for agy, effort is part of the model name (`gemini-3.8-flash-low|medium|high`); sending
`--effort` as well is rejected, even when the values differ from the name. Same class of bug as
`evidence/F004-cursor-model-argument.md`: a harness adapter bug, not a Gemini failure. Not tested:
`--model gemini-3.8-flash-high` alone, and `--model gemini-3.8-flash --effort medium`.

## 2. P-3 probe: inconclusive (the turn did not complete)

The task `T-039` asks for one included Flash request with the model name and no `--effort`. Night 2,
2026-10-15, from fresh `mktemp -d` directories outside the repository:

1. The probe exactly as T-039 gives it (with `--dangerously-skip-permissions`) was **not run**: the
   Claude Code auto-mode classifier denied it ("Safety Bypass Flag"). It was not worked around.
2. Same probe without the bypass flag:
   `agy --print-timeout 5m --model gemini-3.8-flash-medium -p "Reply with OK only."`
   exit 0; stdout empty; stderr `[agy] print timeout after 5m0s with turn in progress; returning partial output`.
3. With a non-bypass mode and a shorter limit:
   `agy --mode plan --print-timeout 90s --model gemini-3.8-flash-medium -p "Reply with OK only."`
   exit 0; stdout empty; stderr `[agy] print timeout after 1m30s with turn in progress; returning partial output`.
4. `agy models` (non-billable) lists `gemini-3.8-flash-high`, `gemini-3.8-flash-medium`, `gemini-3.8-flash-low`
   (and the Claude and GPT-OSS models seen before).

Conclusion: `agy` accepts the model name without `--effort` (no "conflicts with --effort" error), but no
turn completed in 5 minutes or 90 seconds, so the form is **not proven to work end to end**. The cause is
unknown (no error text; possibly the account, quota, or the service). F004 step 7 forbids shipping an
unproven format, so `T-039` stays blocked until a probe returns `OK`. `agy --help` shows `--mode
accept-edits|auto|plan`, `--output-format text|json|stream-json`, `--json-schema`, `--sandbox`. Not tested:
`--model gemini-3.8-flash-high` alone, another agy model, or a retry later.
