# Plan: seat probe, stall watchdog, MCP isolation (F008, owner item 3)

Architect: Opus brain run a9e69754-3c78-46f6-a040-24b29a630779, 2026-10-16. Planning only; no diff reviewed; no worker or provider CLI run (fake CLIs in scratch clones only).

## Order (dependency, not numbering)

| Order | Task | What | Guard? / review | Seat | Size |
| --- | --- | --- | --- | --- | --- |
| 1 | T-050 | provider contract 7: claude `--output-format stream-json --verbose --strict-mcp-config`, worker and brain | guard-adjacent (provider argv) / Opus | claude.economy (alt codex.economy) | S |
| 2 | T-049 | runner stall watchdog (`stalled`, exit 123) and zero-turn failure (exit 122) | GUARD (runner, receipt and ledger enums) / Opus | claude.premium (alt codex.premium) | M |
| 3 | T-048 | `scripts/probe-seat.sh` + `probe_seat.py` | not guard / grok (privacy pinned by oracle + test) | codex.premium (alt claude.premium) | M |

T-050 first: with contract 6 Claude prints nothing until the end, so T-049's startup watchdog would stop every Claude run at 90 s. T-048 imports T-049's `no_turn` and prints contract-7 argv.

## Rule 6 evidence (reference patches outside the repo, scratch clones of 76137fc)

Patch folder: `/private/tmp/claude-501/-Users-zamirhashorva-dev-purrfect-harness/328f4d8a-89b9-4b4b-b52b-b094eef7f79e/scratchpad/` (session scratchpad; copy it if you want to keep it).

| Task | Patch | sha256 | Base | Oracle on base | Oracle after patch | Other checks after patch |
| --- | --- | --- | --- | --- | --- | --- |
| T-050 | `T-050.patch` (5 files, +33 -11) | 346a3e10d52bf16071222597cfdf5d2d4a925d35f59523a42583223df1a05317 | 76137fc | exit 1 | exit 0 | spec tests 13 OK, integration 46 OK |
| T-049 | `T-049.patch` (14 files) | 1c5c9017b2a99c9dd1373c74cf600b0060cf4ff74f1aa9560750b5effa9b5a82 | 76137fc + T-050 | exit 1 (named tests also exit 1) | exit 0 | full suite `bash tests/run-tests.sh` exit 0 (117 ok lines, ALL TESTS PASSED), shellcheck exit 0, no `__pycache__` (T-050 and T-049 together) |
| T-048 | `T-048.patch` (5 files, +367) | c2c862859f1a1e4dd3d86b94a5efa2b8b3cdedba05968535fa2b59fd6e642302 | + T-049 | exit 1 | exit 0 | probe tests 5 OK; full suite: see the line at the end of this block |

## Mutants (each made the named test fail, exit 1, in the scratch clone)

- T-050: the oracle itself rejects: no `--strict-mcp-config`; a role branch (brain only or worker only); contract 6 claude argv changed; any codex/agy/cursor argv change at 7.
- T-049 (`scripts/execution_runner.py`, `scripts/observe_output.py`): stall check `if limit and` -> `if False and` (stall test); idle limit ignored, `limit = args.stall_seconds` (stall test); no clock reset on output (ticking case, stall test); zero-turn check disabled `if False and no_turn(` (zero-turn test); codex branch disabled (zero-turn test); claude `num_turns` branch disabled (observer no_turn test). Every silent case sets a 5 s wrapper timeout, so a broken watchdog fails with 124 instead of hanging.
- T-048 (`scripts/probe_seat.py`): `mcp_names` keeps the whole line (names-only test); wait-class branch removed (class test); fresh folder replaced by cwd (argv test); `no_turn` branch removed (class test).

## Decisions for the owner

1. **Idle limit.** The request says 90 s without output stops the run. A silent tool call is normal: in this run `tests/test-execution-integration.py` alone took 133 s with no provider output, and the full suite takes longer. A plain 90 s limit would stop healthy workers. The plan uses 90 s since launch (no byte at all: the agy/MCP-init class) and 900 s after the first byte, with overrides `SPAWN_WORKER_STALL_SECS`, `SPAWN_WORKER_IDLE_SECS` and the matching `SPAWN_BRAIN_` names. Say if you want 90 s for the idle limit too.
2. **MCP opt-in.** No spec field: no current task names a server. Contract 7 gives every Claude worker and brain no MCP servers. A later task that needs one gets a contract-8 field then.
3. **Not yet proven on this Mac:** (a) whether `--strict-mcp-config` also leaves out the claude.ai connectors; (b) whether a real stream-json log still gives the observed model and usage. H-1 after T-048 is accepted: `bash scripts/probe-seat.sh claude.economy`, then read `mcp_servers` in the init event in `events.jsonl` and the observation. If connectors still load, the next contract adds the env override `ENABLE_CLAUDEAI_MCP_SERVERS=false` through `provider_contract`'s env overrides (Architect review).
4. **Codex MCP.** The two enabled Codex servers (cua_repl, node_repl) are out of scope for this plan. Isolating them is your call (it would be a Codex contract change).
5. **H-2 after T-049:** re-run the real F007 smoke (`fleet-doctor.sh --smoke --f007`) to show the watchdog stops no healthy seat.

Full suite for T-048 (reference tree with T-050, T-049 and T-048 applied): `bash tests/run-tests.sh` exit 0 (118 ok lines, ALL TESTS PASSED), shellcheck exit 0, no `__pycache__`.
