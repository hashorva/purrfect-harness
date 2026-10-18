# Evidence: what each CLI's JSON output reports (probe P-2, 2026-10-15)

One tiny included call per CLI from a fresh `mktemp -d` directory outside the repository, prompt
"Reply with OK only." Raw outputs stay local (`.tasks/probes/observe/`, gitignored); only field names and
non-identifying values are recorded here. No emails, tokens or account ids were present in the outputs
(checked); session and thread ids are not quoted. This is the input for F003 (observed model, usage and
fast state in receipts). Each call exited 0.

## claude — `claude -p --output-format json --model haiku`
One JSON document. Reports the model that actually ran: `modelUsage` is keyed by the resolved model
(`claude-haiku-5-5` for the alias `haiku`), with `inputTokens`, `outputTokens`, `cacheReadInputTokens`,
`cacheCreationInputTokens`, `costUSD`, `canonicalModel`, `provider`. Top level: `usage.*` (input, output,
cache read, cache creation, thinking tokens), `total_cost_usd`, `session_id`, `num_turns`, `duration_ms`,
`duration_api_ms`, `is_error`, `terminal_reason`, `result`, and **`fast_mode_state`** (`off`) — so fast state
is observed, not guessed.

## codex — `codex exec --skip-git-repo-check --json -s read-only -m gpt-6-luna` (stdin closed)
JSON lines: `thread.started` (`thread_id`), `turn.started`, `item.completed` (`agent_message` with `text`),
`turn.completed` with `usage.input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`,
`output_tokens`, `reasoning_output_tokens`. **No model name and no cost in any event**, and no fast-mode
field: observed model and fast state stay `unknown` for Codex. Note: without `< /dev/null` the CLI waits for
stdin ("Reading additional input from stdin...") and hangs; the launcher must close stdin.

## cursor-agent — `cursor-agent -p --trust --output-format stream-json --model composer-2.5`
JSON lines: `system`/`init` with **`model`** (display name `Composer 2.5`, not the CLI model id),
`session_id`, `permissionMode`, `apiKeySource`; `user`; `thinking` deltas; `assistant`; final `result`
with `usage.inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`, `duration_ms`, `is_error`,
`result`, `session_id`, `request_id`. No cost field, no fast-mode field. This **corrects** the earlier note
that `cursor-agent` JSON gives no model: with `stream-json` the init event reports it (as a display name that
needs mapping to the model id).

## agy — not probed
`agy --help` lists `--output-format text|json|stream-json` and `--json-schema`, but every agy turn hung
tonight (see `agy-model-effort-conflict.md`), so its output is unobserved: observed model, usage and fast
state stay `unknown` for agy.

## Consequences for F003
- claude: model, usage, cost and fast state are all observed from `--output-format json`.
- codex: usage observed from `--json`; model, cost and fast state `unknown` (never guessed).
- cursor-agent: model (display name) and usage observed from `stream-json`; cost and fast state `unknown`.
- agy: everything `unknown` until a probe returns a turn.
