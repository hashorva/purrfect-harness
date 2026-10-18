# Changelog — agent-harness kit

## 3.1.0 (2026-10-17)

Minor release (Phase 2A Foundation). New capabilities, schemas, and scripts
propagate cleanly through `scripts/update-harness.sh`; read the consumer
migration notes below before updating a repository.

### Migration: read this before you update a consumer

This is a minor release: `bash scripts/update-harness.sh /path/to/consumer`
propagates the new scripts, schemas, registry, and skills on a branch without
committing. Review these operational changes when adopting `v3.1.0`:

1. **Fleet v2 policy seats and doors:** new missions use `fleet.json` v2 policy
   seats bound to doors in `harness-registry.json`, with per-spawn model
   resolution recorded in the ExecutionSpec and model or door changes appended
   to `drift.jsonl`. Existing `fleet.json` v1 files still validate; Door IDs in
   `harness-registry.json` are permanent and retire only via `"deprecated": true`.
2. **Tool PATH and Gate 0 doctor (`scripts/harness-path.sh`, `scripts/fleet-doctor.sh`):**
   wrappers source `scripts/harness-path.sh` to prepend `/opt/homebrew/bin` and
   `/usr/local/bin` once without duplicates. `fleet-doctor.sh` checks `git`,
   `python3`, `tmux`, `jq`, and `shellcheck` plus provider binary identity and
   login at Gate 0.
3. **Seat admission probes and capability baselines (`scripts/probe-seat.sh`):**
   before dispatching a newly frozen or changed seat, run
   `bash scripts/probe-seat.sh <seat>` to verify a one-turn probe in a fresh Git
   folder with stdin closed, record MCP server names only, and diff `<cli> --help`
   flags against `docs/missions/capabilities/<cli>.txt`.
4. **Provider contracts 7–9:** Claude runs under `--strict-mcp-config` (unless
   the spec explicitly names an MCP server) and `--permission-mode bypassPermissions`
   with `--add-dir <repo>`, the `CLAUDE_DISALLOWED_TOOLS` deny-list, and the
   post-run protected-path receipt guard. Codex keeps `-s workspace-write` with
   `sandbox_workspace_write.network_access=true`, `web_search="live"`, and
   per-run `cua_repl`/`node_repl` disabled. Every adapter runs under the 90s
   stall watchdog and fails any run that completes with 0 turns.
5. **Ledger v2 privacy and `self_reported_model`:** `.tasks/ledger/<run_id>.json`
   stays gitignored until folded into `docs/missions/ledger.jsonl` at feature
   acceptance. Ledger rows carry `self_reported_model` alongside `observed_model`
   and enforce the `[A-Za-z0-9 ._:/-]{0,200}` allow rule on harness-generated
   text fields.
6. **Native-only doors:** freeze-v2 refuses, and resolve_v2 skips, a door that is not native to the seat family; re-freeze any v2 fleet that binds a foreign model on agy before dispatch.

### What changes

- **Fleet v2 (`scripts/fleet_state.py`, `harness-registry.json`):** policy seats
  resolve through ranked doors (`included` before `credits`/`api` unless
  opted in, never `-fast` unless enabled), encode Cursor effort in the model id
  and Antigravity effort in the model name (`agy.economy` = `gemini-3.8-flash`,
  `agy.premium` = `gemini-4-argon` on its weekly-only pool, native doors only), and require a writable drift log whenever resolution changes.
- **Provider contracts 7–9 (`scripts/execute_provider.py`, `scripts/execution_runner.py`, `scripts/execution_receipt.py`):**
  contract 7 adds the 90s stall watchdog, zero-turn failure guard, and Claude
  `--strict-mcp-config`; contract 8 restores the `agy` `stream-json` lane with
  stdin closed; contract 9 unlocks native toolsets across providers — Claude
  `bypassPermissions` with the 73-pattern `CLAUDE_DISALLOWED_TOOLS` deny-list
  and in-memory pre/post protected-path, symlink, `.gitignore`, and stdlib-shadowing
  guards, and Codex `workspace-write` with live network/web search and
  `cua_repl`/`node_repl` disabled per run.
- **Ledger and verdicts (`scripts/ledger.py`, `scripts/validate_verdict.py`, `schemas/`):**
  ledger schema v2 records `self_reported_model`, enforces the character-set
  allow rule and near-miss refusal on harness-generated text, and verifies door
  permanence across `docs/missions/ledger.jsonl`; JSON schemas validate task
  plans, review verdicts, and worker outputs.
- **Seat probes and capability inventory (`scripts/probe-seat.sh`, `scripts/probe_seat.py`):**
  runs the seat's exact harness command in a scratch Git repo with stdin closed
  and a 2-minute cap, classifies `ok`, `no-turn`, `mcp-init-wait`,
  `permission-wait`, `input-wait`, `auth`, `limit`, or `unknown`, records MCP
  server names only, and diffs `<cli> --help` flags against committed baselines.
- **Model identity (`scripts/observe_output.py`):** observed model identity is
  taken strictly from authoritative CLI session metadata (for Codex, only the
  top-level session `model` field, never nested or guessed values) and `no_turn`
  requires positive zero-turn evidence.
- **Autopilot driver (`scripts/drive-cli.sh`, `scripts/drive_cli_rules.py`, `scripts/drive-cli.rules.json`):**
  isolated `tmux` driver with deterministic regex rules that answers at most one
  exact folder-trust prompt and stops with exit code 3 on any later or
  numbered/menu unknown prompt without sending input. Boxed menus and
  alternate-screen redraws are accepted residuals that end as an exit-4 stall.
- **Shared tool PATH (`scripts/harness-path.sh`):** idempotent PATH helper
  sourced by wrappers, `fleet-doctor.sh`, and tests; safe under `set -u`.
- **Seeded-defect reviewer calibration:** `routing-data.jsonl` records 3/3
  planted-bug catches (cases A, B, C) for `grok-4.7-high` and
  `gemini-4-argon-high (agy)` to qualify guard-review lanes from evidence.

### Phase 2A features F010 to F013

- F010 capability unlock: every adapter runs its full native toolset under provider contract 9; Claude keeps the deny-list and --strict-mcp-config, Codex keeps workspace-write with network and live web search and cua_repl/node_repl off per run, and probe-seat.sh diffs each CLI --help flag list.
- F011 drive-cli hardening: after one answered trust prompt, any later prompt-like pane and every numbered or menu approval prompt stops with exit 3, and no input is sent.
- F012 release 3.1.0 candidate: harness-manifest.json, README frontmatter and this CHANGELOG say 3.1.0 / v3.1.0 together, and the docs/RELEASING.md checks pass.
- F013 native-only fleet: launcher prompts give goal, resources, budget and acceptance checks; Claude Code runs delegate wide reading to the Haiku explorer subagent; receipts record subagent calls and their tokens; the load-sensitive tests pass 5/5 under load; compiled-module and stdlib shadowing are scope violations.
- Native-only rule: a door never serves a model from another vendor, so the agy Opus, Sonnet and GPT-OSS bindings are gone, and a move to another vendor is an explicit choice of another approved native seat.
- Effort by role: brain seats (brain, brain_codex, brain_argon) run at high effort; review and worker seats run at medium effort.

### Known limits

- **Claude `bypassPermissions` + `Bash` is a net, not a wall:** headless Claude
  Code has no OS-level workspace-write sandbox, and `acceptEdits`/`dontAsk` do
  not confine shell commands when `Bash` is enabled. Contract 9 pairs the
  `--disallowedTools` deny-list with post-run protected-path and Git-state
  receipt checks, which catch accidental destructive commands and protected-path
  edits rather than arbitrary shell evasion (see
  `docs/missions/20261014-2a-foundation/evidence/claude-unlock-residual-risk.md`).
- Scope checks and protected-path snapshots cover Git-visible workspace changes
  and the explicitly snapshotted protected paths only.
- One worker at a time per repository workspace lock.
- Residual risks (docs/missions/20261014-2a-foundation/evidence/claude-unlock-residual-risk.md): a command that evades --disallowedTools can still read, exfiltrate or change paths outside the workspace, and the post-run snapshot detects changes only to the listed protected paths and Git workspace and index state.
- drive-cli residuals: boxed menus and alternate-screen redraws are not classified as prompts; the driver sends no input and the run ends as an exit-4 stall.

## 3.0.0 (2026-10-14)

First release since `v2.3.0`. It publishes Phase 1 (Execution Truth) and the
2.3.2 fixes. The untagged development baselines `2.3.1` and `2.3.2` below were
never published; their entries stay as history.

Every run is now provable: one UUID links the authorization, what actually ran,
the verification, and the orchestrator's acceptance. A fresh process can rebuild
that chain from the repository alone (see the F007 evidence archive).

### Migration: read this before you update a consumer

This is a major release. The updater alone is not enough.

1. Update from the clean `v3.0.0` tag: `bash scripts/update-harness.sh /path/to/consumer`.
   It works on a branch and never commits.
2. Review the consumer's own `AGENTS.md` against `docs/templates/AGENTS.md.template`
   by hand. Port the new mission rules; keep the project's own rules.
3. Resolve `.claude/settings.json.new`. The new baseline allows the harness's
   launch, verify and test commands.
4. Old mission evidence stays, but it can fail the new strict audit. Do not invent
   UUIDs or acceptance fields for old runs. Start new missions from the current
   templates.
5. New missions freeze their fleet at Gate 0 (`scripts/fleet_state.py freeze`).
   Workers dispatch only from that `fleet.json`.
6. Cross-repository dispatch (`--repo` to another repository) is disabled.
7. Cursor workers now run as `cursor-agent`. Run `cursor-agent login` with the
   account your Cursor app uses. Grok Build also installs a bare `agent`.
8. Qualify one small real mission in the consumer before you rely on it.

### What changes

- **Authorization:** each brain or worker run writes an immutable, UUID-keyed
  ExecutionSpec before the provider starts. One shared adapter builds the exact
  command for Codex, Cursor, Antigravity and Claude.
- **Frozen fleet:** Gate 0 freezes the approved models in the mission's
  `fleet.json`. A later probe cannot change an active mission. Model, effort and
  speed flags must match the frozen seat; they never override it.
- **Dispatch gate:** a worker starts only for an in-progress mission, a committed
  task for one pending feature, a clean tree, and an exclusive workspace lock.
- **Terminal receipts:** every run ends with a receipt: outcome, exit code, Git
  state before and after, commits, changed paths and a scope check. Timeouts and
  interrupts stop the whole provider process tree.
- **Verification and acceptance are separate:** `verify-mission.sh --run-id`
  runs the task's checks on the exact snapshot and writes a VerificationRecord.
  Only the orchestrator accepts a feature, with `accept-feature.sh`.
- **Distribution:** `harness-manifest.json` owns what install, update and sync
  copy. A normal install or update needs a clean, annotated release tag.
- **CI on Linux and macOS**, with ShellCheck pinned to 0.11.0.
- **Truthful inventory:** it reads the real Cursor, Antigravity and Grok model
  lists, ranks by version (then date, then effort), never picks a `-fast` model
  automatically, and marks a missing family as unavailable instead of guessing.

### Known limits

- Scope checks cover Git-visible changes in the declared workspace only.
- Cursor effort and speed are still passed as `model[effort=…,fast=…]`. A real
  Cursor run through the harness has not proved this format yet.
- One worker at a time per repository. Parallel lanes, a loop driver, Grok Build
  as its own provider and usage records are Phase 2 work.

## 2.3.2 (2026-10-14)

- **Development baseline; not yet released:** `2.3.2` is an untagged development
  baseline. It adds fixes to the untagged 2.3.1 Phase 1 baseline. Tagging and
  publication remain separate human decisions (see docs/RELEASING.md).

- **CI is green again, on Linux and macOS.** CI pins ShellCheck 0.11.0, so CI and
  local runs report the same codes. The trap cleanup functions disable both
  SC2317 (old ShellCheck) and SC2329 (new ShellCheck). CI runs on `ubuntu-latest`
  and `macos-latest` and validates every tracked JSON file.

- **Tests run the same on every shell.** One check used `$(< file)` inside
  `sh -c`; on Linux `sh` is dash, which reads it as empty. It now uses `bash -c`.
  `run-tests.sh` sets `PYTHONDONTWRITEBYTECODE=1`, and `.gitignore` ignores
  `__pycache__/` and `*.pyc`: bytecode left in the tree made the next dispatch
  fail with "workspace must be clean". The release fixture tag now comes from
  `harness-manifest.json`.

- **The Cursor lane calls `cursor-agent`.** Grok Build also installs a bare
  `agent`. On a machine with both, `agent` can start Grok Build. Provider
  contract 3 calls Cursor's CLI by its unambiguous name, and the inventory
  probes `cursor-agent models`. New ExecutionSpec v3 files carry contract 3.
  Contract 1 and 2 evidence keeps its historical argv, so old receipts still
  verify. The provider name in fleets stays `agent`.

- **The inventory reads real model lists.** The parser read nothing from
  Antigravity output (`id   Display Name`) or Grok output (`* id (default)`).
  That is why Phase 1 marked those seats degraded and guessed ids. It now reads
  the Cursor, Antigravity and Grok formats.

- **"Newest model" means newest.** The chooser summed digits, so `grok-4.5`
  ranked above `grok-5`, and a dated old Claude id ranked above a new one. It
  now ranks stable before preview, then version, then release date, then effort.
  A `-fast` model is never chosen automatically: fast modes cost more and are
  opt-in only. A successful list without a family member gives an honest
  `unavailable` seat. Before, it produced a guessed seat that made the whole
  inventory command fail.

- **Client permissions and worker guidance.** `.claude/settings.json` allows the
  harness's own launch, verify and test commands, and `cursor-agent -p` instead
  of `agent -p`. Feature acceptance still asks the human. The worker template
  states that a check's result is its exit code; a missing summary line is not a
  reason to stop.

## 2.3.1 (2026-08-13)

- **Development baseline; not yet released:** `2.3.1` remains an untagged development
  baseline after published annotated `v2.3.0`. Phase 1 is complete, including Human
  Gates 1/2 and the real consumer smoke. Final release numbering requires downstream
  migration review; this development identifier does not decide it.

- **Execution authorization:** every brain/worker run atomically persists a UUID-keyed
  immutable ExecutionSpec before provider launch. One shared adapter constructs exact
  argv for Codex, Cursor agent, agy, and Claude. Current spec v3 binds provider
  contract 2; legacy v1/v2 specs retain contract 1, so adapter evolution does not
  reinterpret historical receipts. Codex contract 2 retains workspace-write and
  explicitly mounts the same repository's Git metadata.

- **Fleet and dispatch truth:** Human Gate 0 freezes canonical approved mission
  `fleet.json`. Model/effort/speed flags are equality assertions, never overrides.
  Failed probes preserve per-provider last-good state as degraded, and fallback
  guesses cannot appear observed. Workers require an in-progress mission, pending
  feature, matching task identity, clean workspace, and an exclusive workspace lock.
  Cross-repository execution is disabled in Phase 1.

- **Execution evidence:** the shared runner writes one terminal ExecutionReceipt with
  spec hash, requested/resolved/unknown-observed configuration, exact Git-visible
  before/after state, commits, changed paths, scope result, and process outcome.
  UUIDs prevent timestamp collisions; no-op and null evidence cannot qualify worker
  implementation. Timeout/interruption cleans up and reaps the provider process tree.
  Scope is explicitly limited to Git-visible changes in the declared workspace.

- **Verification and acceptance:** `verify-mission.sh --run-id` uses checks authorized
  by the task at the receipt's base commit, requires the same Git snapshot before and
  after checks, and publishes an immutable VerificationRecord. The orchestrator then
  uses `accept-feature.sh` to record the exact run/hash/time/identity in feature state.
  Verification does not imply acceptance. Mission audit rejects unrelated receipts,
  legacy/null substitutes, malformed metadata, and rehashed identity rebinding.

- **Distribution truth:** `harness-manifest.json` owns distributable skills, payloads,
  update paths, discovery targets, and the consumer AGENTS skeleton. Its validator
  is mounted by release CI, install, update, and sync. Normal propagation requires
  the exact clean annotated manifest tag; `--dev` is only for explicit local smoke.
  Unsafe ownership and installed versions fail closed; project-owned instructions,
  mission instances, and foreign discovery skills are preserved.

- **Real end-to-end evidence:** an authenticated Codex/Luna consumer run changed and
  committed one nonce file, passed its run-specific checks, and was separately
  accepted. The archived fleet/spec/receipt/verification/acceptance/Git bundle and
  sanitized log reconstruct all four truths in a fresh process. Raw hash tampering
  and rehashed acceptance rebinding have mounted negative regressions.

- **Release-readiness instructions:** canonical skills, protocol, and templates now
  use frozen fleet authority, UUID artifacts, JSON argv checks, and separate feature
  acceptance. The shipped worker template has a real-wrapper regression plus a
  missing-verification-section negative. Guard verification requires red results at
  the intended assertion. Release docs preserve published tags and follow automatic
  tag-triggered packaging; consumer migration review remains explicit.

## 2.3.0 (2026-08-12)

- **New skill: `guard-verification`.** Graduated from three shipped instances of the same failure —
  a correct guard with a green test suite that never runs where it matters, or that nothing can
  violate. FinDuck's `20260810-glossary-content-model` produced two: a publication flag wired into
  four places but never into the corpus validator (the only caller passing it was a unit test, and
  flipping the flag published documents the guard existed to block), and a `<main>` extraction
  falling back to `''` so the link gate passed having examined nothing. Mission 1A produced the
  third — a correct language switcher the public navbar never rendered. The skill is the procedure:
  find the non-test callers, name the entry point, **break the guard and watch the real path fail**,
  interrogate every fallback, construct the weakest satisfying value, and assert against the mount
  point rather than the validator.
- **`dispatch-worker`: the codex sandbox limits are now one table, checked before routing.** Three
  limits, each learned by a failed dispatch: cannot bind a TCP port, cannot read the macOS keychain
  (so `supabase db push` fails while `migration list` succeeds), and — new from F017 — **cannot
  reach the npm registry**, so any task that adds a dependency must go to `agent`. All three are
  reachable from the orchestrator's own shell, so testing them locally proves nothing about the
  worker.
- **`shadcn-luma`: current preset code, the missing `--pointer` flag, and the CSS-import trap.** The
  preset had sat unverified at `b2D0wqNxT` for months despite the skill's own instruction to check
  it every run; it is now `b83suB2Xac` with a dated status table and the create URL. `--pointer` is
  a real flag (`enable pointer cursor for buttons`) and pointer-on-buttons is studio convention —
  omitting it silently yields the default cursor, which reads as "not quite our UI" without ever
  looking broken. Also documents that `--preset` affects `init`/`apply` only (`add` reads
  `components.json`), so a rotated code cannot explain drift in installed components; and that
  `@import 'shadcn/tailwind.css'` in global CSS makes `shadcn` a **runtime** dependency — in FinDuck
  that shipped `express`, `msw` and the MCP SDK into production and hoisted a CommonJS `cookie@0.7.2`
  that broke Astro prerendering outright. **Grep CSS as well as JS before calling a package
  CLI-only.**
- Documentation formatting and structure pass across the kit.

## 2.2.9 (2026-08-05)

- **Mechanized false-green detection for `dispatch-worker`.** `exit=0` from
  `spawn-worker.sh` has already produced two silent no-op "successes" in a
  consuming repo (agy's Go-style flag parser swallowing the prompt into `-p`'s
  value; a mocked test suite reporting green twice with no edits — both
  `catalog-truth` F004/F009). `verify-mission.sh` only checked receipt
  `exit==0` + feature-tag match, never whether anything actually changed.
  - `spawn-worker.sh` now captures the workspace's git `HEAD` before/after
    every CLI invocation, computes commits made + dirty files, and logs an
    inline `WARNING` on `exit=0`-but-unchanged.
  - `write-receipt.sh` accepts `--commits-made`/`--dirty-after` and derives
    `workspace_changed` (`true`/`false`/`null`) onto worker receipts.
  - `verify-mission.sh` hard-fails any `passes: true` feature whose matched
    worker receipt has `workspace_changed: false`. Receipts predating this
    field (`null`) WARN instead of failing — no retroactive breakage for
    existing `.tasks/receipts/`.
  - `dispatch-worker/SKILL.md`'s false-green checklist now documents this as
    an enforced gate, not a manual reminder.
  - Brain receipts are untouched — `mission-init`/`gate0`/`review` don't all
    produce a diff (`review` must not), so the check is worker-only.

## 2.2.8 (2026-08-05)

- **README/CHANGELOG version match enforced in `tests/run-tests.sh`.** Same extraction
  as `.github/workflows/ci.yml` (`version:` vs top `##` heading), plus a non-vacuous
  mismatch fixture so the check cannot pass vacuously. CI stays as the backstop —
  this fails seconds before a push instead of minutes after one. Forgotten at v2.2.4
  and v2.2.5; that is enough.
- `docs/RELEASING.md` names the README bump and the local test as required release
  steps, not optional memory.

## 2.2.7 (2026-08-05)

- **Fix: the v2.2.6 codex stdin redirect was never applied.** The changelog and the
  stdin regression test both assumed `codex exec … < /dev/null`, but
  `scripts/spawn-worker.sh`'s codex arm still inherited stdin. CI failed on
  `codex stdin is closed so EOF-reading stub returns` (~1s bounded kill) while a
  simplified local run often passed because the test process's stdin was already
  closed. The redirect is now on the real invocation. Do **not** "fix" this by
  only widening the test wait window — that masks a missing redirect.

## 2.2.6 (2026-08-05)

- **Fix: the `codex` lane hung forever.** `codex exec` blocks reading stdin unless stdin is
  closed; `spawn-worker.sh` never closed it, so every codex dispatch stalled on
  "Reading additional input from stdin...". Now redirects `< /dev/null`.
  **Third of four lanes found broken** — and a different failure mode from `agy` (2.2.3)
  and `claude` (2.2.5), which were flags eating the positional prompt. An argument-shape
  stub would not have caught this one.
- **`--effort <value>`** passthrough for codex (`-c model_reasoning_effort="<value>"`);
  omitting it keeps the previous `medium` default. Ignored for other lanes.
- **codex and agent lanes now stub-tested**, comparing the full argv against an expected
  file (`cmp`), so flag/value boundaries and final prompt position are asserted exactly —
  not a simplified invocation.
- **stdin regression test** holds the wrapper's stdin open via a FIFO and asserts the stub
  reaches EOF, with a bounded failure path so a regression fails in seconds instead of
  hanging.
- Releaser note: bump `README.md`'s `version:` line with the CHANGELOG — CI compares them.

## 2.2.5 (2026-08-05)

- **Fix: the `claude` worker lane never worked either.** `--allowedTools` is **variadic** —
  it keeps consuming following arguments as tool names — so `spawn-worker.sh`'s
  `claude -p --model M --allowedTools "Read,Write,Edit,Bash" "$PROMPT"` fed the prompt to
  `--allowedTools` and claude exited with _"Input must be provided either through stdin or
  as a prompt argument when using --print"_. The prompt now comes **before** the flags.
- **Same failure family as the `agy` fix in 2.2.3** — a flag eating the positional prompt.
  Two of the four worker lanes shipped broken this way. A CLI smoke test that omits the
  real flags will not catch it: `claude -p --model sonnet "..."` succeeds, and only fails
  once `--allowedTools` is in the line. **Smoke-test the exact invocation the harness uses,
  not a simplified one.**
- Regression tests: a stub `claude` on `PATH` asserts the prompt follows `-p` directly and
  is never positioned after `--allowedTools`.
- `codex` and `agent` lanes unchanged. `codex`'s `-c` takes exactly one value and `agent`'s
  `-p` is a boolean, so neither shows this shape — but neither is covered by a stub test
  yet, and that gap is worth closing next.

## 2.2.4 (2026-08-04)

- **`"bootstrap"` authoring guidance.** 2.2.2 made `verify-mission.sh` require an explicit
  `"bootstrap": true` for brain-only features, but nothing told the orchestrator _when_ to
  set it — so a real mission authored an orchestrator-only feature (an `AGENTS.md` edit)
  without the field, and it went green on `verify-mission`'s any-worker fallback with only
  a WARN. `mission-init/SKILL.md` now states the rule, why the failure is quiet rather than
  loud, and that the decision belongs at authoring time: adding the flag after GATE 0 is an
  edit to an approved feature, which `features.json`'s own rules forbid.
- The template's `rules` string now carries the same instruction, so it is visible inside
  every mission's `features.json` rather than only in the skill.
- Tests: every template feature must ship the `bootstrap` field, the template `rules` must
  explain it, and the `mission-init` skill must document it.
- No behaviour change to `verify-mission.sh` — the gate was already correct; only the
  guidance around it was missing.

## 2.2.3 (2026-08-03)

- **Fix: the `agy` lane never worked.** Antigravity's CLI uses a Go flag parser in
  which `-p` / `--print` / `--prompt` **takes the prompt as its value**.
  `spawn-worker.sh` called
  `agy -p --dangerously-skip-permissions --model M "$PROMPT"`, so
  `print="--dangerously-skip-permissions"` and the real prompt was discarded — agy
  replied with prose about the flag, exited 0, and the wrapper reported success
  having done no work. `-p` now comes last, with the prompt as its value.
  **Any project on 2.1.1–2.2.2 that dispatched to `agy` got a silent no-op.**
- `--print-timeout` now set to `30m` (Antigravity defaults to 5m, which truncates
  multi-file UI tasks).
- Regression test: a stub `agy` on `PATH` asserts the real prompt is the value of
  `-p`, that `-p` is never fed the permissions flag, and that a print-timeout is passed.
- Reminder this surfaced: `exit=0` from `spawn-worker.sh` means _the CLI exited 0_,
  not _the work happened_. Review the diff, never the exit code alone.

## 2.2.2 (2026-07-28)

- **Cross-repo dispatch:** `spawn-worker.sh` gains `--repo <path>` — worker CLI
  workspace can be another repo (e.g. `~/Projects/purrfect-worker`) while logs,
  receipts, and mission files stay in the consuming repo. `write-receipt.sh`
  records `repo` on each receipt.
- **Self-edit safety:** `spawn-worker.sh` re-execs from a temp snapshot on entry so
  a worker editing the script cannot kill the running wrapper (bash re-reads the
  live file by byte offset after the CLI returns).
- **Log isolation:** dispatch logs are timestamped (`T-001-20260728T….log`) so stub
  re-runs of the same task basename cannot clobber the real transcript.
- **verify-mission bootstrap gate:** brain-only features must opt in with
  `"bootstrap": true` in `features.json`. Removed substring heuristic over
  descriptions (`"mission files"` falsely excused harness features from needing
  worker receipts).

## 2.2.1 (2026-07-27)

- README hero mermaid: invisible `Rewrite ~~~ Flip` layout link so pass/fail
  arrows from Opus review do not cross.

## 2.2.0 (2026-07-27)

- **Dispatch proof:** `scripts/spawn-brain.sh` (Claude Opus brain), `write-receipt.sh`,
  and `verify-mission.sh`. Workers/brain writes `.tasks/receipts/*.json`; GATE /
  `passes:true` / `status: done` require `verify-mission.sh` exit 0. PROGRESS prose
  is not evidence. Waiver path for “already on Opus in this chat” is explicit and
  labeled. spawn-worker gains `--feature` for per-feature receipts.
- mission-init / dispatch-worker / ORCHESTRATION / AGENTS updated for the receipt rule.

## 2.1.2 (2026-07-27)

- README first screen for newbies: shields.io badges under H1, orchestration
  mermaid (Opus → GATE 0 → Grok/Composer → review), intro aligned to 2.1.x routing.

## 2.1.1 (2026-07-27)

- Antigravity (`agy`) is first-class: inventory binds `agy.premium` (Gemini Pro-class)
  and `agy.economy` (Flash-class); dispatch prefers agy for UI/shadcn/Luma tasks;
  home-fleet note — Cursor→Grok/Composer, Codex→Terra/Luna, agy opt-in or UI lane.
- spawn-worker resolves agy `--tier`; GOAL template lists agy seats.

## 2.1.0 (2026-07-27)

- MODEL_ROUTING rewrite: **Opus default brain**; Cursor intake → Opus weighs & orchestrates;
  Fable / Sol only when human names them (no Fable auto-escalate); “no orchestration” escape.
- Cursor workers: **Grok = premium**, **Composer = economy** (Grok → Composer if unavailable).
- Codex seats inventory-classified (Sol brain / Terra premium / Luna economy — names may change).
- NEW `scripts/fleet-inventory.sh` — probe CLIs, bind seats, always show map at GATE 0 for
  confirm/swap; writes `.tasks/fleet-inventory.json` (gitignored).
- `spawn-worker.sh` gains `--tier economy|premium` and `--model`; resolves via inventory.
- mission-init / dispatch-worker / GOAL template / ORCHESTRATION updated for the policy.

## 2.0.2 (2026-07-27)

- FIX `scripts/sync-skills.sh`: per-skill discovery links use relative paths
  (`../../.agents/skills/<name>`), not absolute machine paths.

## 2.0.1 (2026-07-27)

- FIX `scripts/sync-skills.sh`: if `.claude/skills` (etc.) is a legacy parent symlink to
  `.agents/skills`, replace it with a real directory before writing per-skill links.
  Previously sync corrupted canonical skills into self-symlink loops. install-harness
  no longer creates the parent symlink — it runs sync-skills instead.

## 2.0.0 (2026-07-27)

- **BREAKING — mission layout:** orchestration lives under `docs/missions/`. Protocol +
  `MODEL_ROUTING.md` + templates move there; instance missions are
  `docs/missions/<YYYYMMDD-slug>/{GOAL,features,PROGRESS,tasks/}`. Root `GOAL.md` /
  `features.json` are obsolete. Stubs remain at `docs/ORCHESTRATION.md`,
  `docs/MODEL_ROUTING.md`, `docs/templates/README.md` for old links.
- **Active mission** = exactly one folder with GOAL `status: in-progress|awaiting-gate`
  (`scripts/active-mission.sh`). Status lifecycle: `draft` → `approved` →
  `in-progress` → `awaiting-gate` → `done`.
- **Human GATE registration** required in PROGRESS.md; session-end rule: agents must
  ask before ending when a gate is pending. Chat approval alone is not the record.
- **Local CLI spawn:** `scripts/spawn-worker.sh` runs `codex` / `agent` / `agy` /
  `claude` on the machine PATH with economy pins and `.tasks/logs/`. dispatch-worker +
  mission-init require real CLI inventory (`command -v`) — orchestrators must not
  silently absorb fleet work into one chat when CLIs are available.
- `update-harness.sh` / install copy kit-owned mission _protocol_ paths only — never
  wipe project mission folders. AGENTS.md skeleton ports the new layout (manual merge
  in consuming repos).
- MAJOR: consuming repos need AGENTS.md section port + move any root mission into
  `docs/missions/<slug>/` before relying on the loop.

## 1.11.0 (2026-07-19)

- NEW `docs/MODEL_ROUTING.md` — four routing criteria (horizon, silent-error cost, verifiability, volume); orchestrator policy: Opus (alias `--model opus`, effort high/extra) OR GPT-5.6 Sol (effort high) chosen per mission at GATE 0; Fable 5 demoted to evidence-gated escalation (2x review failure, mission stall, features churn, declared task class, or manual override) — self-reported confidence explicitly rejected as a trigger
- Alias doctrine: invocations use CLI aliases so new flagships (Opus 5, ...) are adopted automatically at the NEXT GATE 0, never mid-mission; resolved model+version logged in PROGRESS.md; deliberate pin bumps = PATCH
- ORCHESTRATION.md + dispatch-worker: "Fable/Opus always-premium" wording replaced with MODEL_ROUTING reference (post 2026-07-20 Fable paywall, the old line silently spent API credits)
- GOAL.template.md: Fleet gains an Orchestrator line; stale `claude-sonnet-4-6` pin replaced by `haiku`/`sonnet` aliases
- mission-init: orchestrator brand is a GATE 0 decision; GATE 0 presents the resolved model
- Price snapshot quarantined in a dated appendix (decays fast, never load-bearing)
- update-harness.sh: docs/MODEL_ROUTING.md added to KIT_PATHS (propagates on update)
- NEW LICENSE (CC BY-NC-SA 4.0): attribution required, non-commercial, share-alike
- NEW .github/workflows/ci.yml — shellcheck, JSON template validation, version-consistency (README vs CHANGELOG), end-to-end install/update test in a throwaway repo
- NEW .github/workflows/release.yml — on tag v\*: tag==CHANGELOG guard, GitHub Release with kit zip + notes extracted from CHANGELOG
- NEW tests/run-tests.sh — install collision rules (absent/identical/different), symlinks, .harness-version, update path
- NEW docs/PUBLISHING.md — first-publish and every-release runbooks (gh CLI)

## 1.10.0 (2026-07-09)

- NEW `scripts/install-harness.sh` — first-time install with conservative collision rule (absent→copy, identical→skip, different→.harness-new; AGENTS.md never proposed against, arrives as .template; refuses repos already under management)
- README: install section rebuilt as "Purrfect Install" — separate new-repo vs existing-repo flows, each with a Mermaid diagram, script snippets, manual TODOs, and the pre-merge ritual

## 1.9.1 (2026-07-09)

- README: detailed install procedure (6 steps, verify checklist) + two Mermaid diagrams (anatomy: who-reads-what; mission lifecycle: trigger chain)
- NEW docs/RELEASING.md — SemVer interpretation for a harness, annotated-tag release procedure, propagation rules
- Docs-only: no behavioral change (hence PATCH)

## 1.9.0 (2026-07-09)

- NEW `scripts/update-harness.sh` — safe propagation to consuming repos: clean-tree check, update branch, overwrites kit-owned manifest paths only, settings.json via .new file, records .harness-version, never auto-commits
- README: ownership model (kit-owned / project-owned / merged) + the two laws (never edit kit files in repos; improvements flow upstream, never sideways)

## 1.8.0 (2026-07-09)

- NEW `.agents/skills/skillify/SKILL.md` — evidence-based skill graduation (≥2 occurrences, deterministic, verifiable, human-gated; patch-over-create)
- `docs/ORCHESTRATION.md`: added "Orchestrator contract" (5 requirements; role is protocol-agnostic; Claude Code = only enforced implementation; enforcement ports deferred to a forcing event)
- Deliberately NOT shipped after break-even analysis: multi-orchestrator enforcement configs, auto-parallel dispatch

## 1.7.0 (2026-07-09)

- Dynamic per-mission fleet: `## Fleet` table added to GOAL.template.md (tier chosen at GATE 0)
- WORKER_TASK.template.md: optional `invocation:` frontmatter (per-task override; doubles as escalation mechanism)
- dispatch-worker: invocation precedence chain — task frontmatter > GOAL.md Fleet > machine economy defaults
- mission-init: fleet tier (economy/premium/mixed) is an explicit GATE 0 decision; never silently premium

## 1.6.0 (2026-07-09)

- dispatch-worker: mandatory cost pinning — fleet table with pinned invocations (`codex exec --profile worker`, `agent --model composer`, agy flash-tier, `claude -p --model claude-haiku-4-5`)
- Escalation rule: tier-up only inside a task rewrite after CAPABILITY failure, one tier at a time, logged
- One-time machine setup documented: `~/.codex/worker.config.toml` (cheap model, medium effort, workspace-write)

## 1.5.0 (2026-07-09)

- dispatch-worker rewritten: real fleet CLIs (codex / agent / agy / claude -p); two failure classes — CAPABILITY (burns attempt) vs INFRASTRUCTURE (quota/429/stall: reset tree, reassign, no attempt burned); completion = blocking process exit; parallelism rules (never two workers same tree; pipelining encouraged; cross-repo OK; worktrees deferred)
- NEW `.agents/skills/mission-init/SKILL.md` — deterministic mission bootstrap from templates (GOAL.md + features.json + T-001 only), GATE 0 mandatory stop
- settings.json allow-list updated to real CLI names

## 1.4.0 (2026-07-09)

- NEW `.agents/skills/dispatch-worker/SKILL.md` — spawn via Bash with log redirect, three-question routing, judge-by-effects, two-attempt policy
- settings.json: worker CLIs pre-allowed

## 1.3.0 (2026-07-09)

- NEW Claude Code enforcement layer: `.claude/settings.json` (deny rm -rf / db reset / force-push / credential reads; allow routine verification), `.claude/rules/database.md` + `ui.md` (path-gated pointers), `.claude/agents/code-reviewer.md` (read-only review subagent, PASS/FAIL + flywheel note)
- README: enforcement-vs-guidance section; documented deliberate omissions (commands/, output-styles/, workflows/, .mcp.json, local/memory files)

## 1.2.0 (2026-07-09)

- Skills promoted to v2 universal: shadcn-luma (Luma preset b2D0wqNxT mechanics, apply vs --only theme, --base radix studio convention); supabase-migration (apply Path A `db push` vs Path B GitHub integration, read from project AGENTS.md)
- Templates: MD025 fix (removed `title:` frontmatter)
- README: four-layer model (AGENTS.md=rules, docs/=knowledge, skills=procedures, templates=dormant loop)

## 1.1.0 (2026-07-09)

- AGENTS.md template restructured to the FinDuck skeleton (Product → Stack → ... → Orchestrated missions → Repo structure)
- Install switched to whole-directory symlinks (3 one-liners); sync-skills.sh demoted to optional

## 1.0.0 (2026-07-09)

- Initial kit: AGENTS.md template, thin CLAUDE.md/GEMINI.md wrappers, docs/ORCHESTRATION.md, 4 templates (GOAL, features.json, PROGRESS, WORKER_TASK), 5 skills (supabase-migration, shadcn-luma, react-conventions, mcp-hygiene, cloudflare-deploy), sync-skills.sh
