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
