---
title: Purrfect Harness — Audit after Phase 1 (Execution Truth)
date: 2026-10-06
audited_commit: 840a777 (origin/main)
scope: repository, per-flow implementation, CLI + latest-model integration
status: proposal — nothing here is approved scope until a Gate 0 says so
---

# Purrfect Harness — Audit after Phase 1

This audit covers `main` at `840a777` ("docs: refresh README workflows and
diagrams for Phase 1"). That is the 80-commit Phase 1 push on top of `v2.3.0`.

**Your answers before the audit:**

| Question | Your answer | How the audit uses it |
|---|---|---|
| Installed CLIs | All of them (`claude`, `codex`, `agent`, `agy`, and others) | Section 3 designs one adapter per CLI and a registry so more can be added as data |
| Latest-model policy | **Fully automatic, even mid-mission** | Section 3.2 changes the frozen-fleet rule so models re-resolve per spawn, but never silently |
| Direction | Hybrid. The point is to spend *your subscriptions* across vendors while *any* chair (Sonnet, Terra, Cursor…) keeps progress and follows up until the mission is done | The two biggest missing pieces (§1.3): a chair that works with any vendor, and a loop driver that follows up |

**How the evidence was gathered.** Some claims were tested in this audit. Others
come from reading code. Claims about the other vendors' CLIs that I couldn't run
here are marked **[verify on Mac]**: the cloud container has only `claude`, and
the vendor doc sites are blocked by its network policy.

---

## 0. TL;DR — the ten things that matter, in order

| # | Scale | Finding / action | Severity | Effort |
|---|---|---|---|---|
| 1 | Repo | **CI is red on `main`** (run 22). ShellCheck version skew fails the job before tests run. Once that's fixed, two Linux-only test failures and one hygiene gap are waiting behind it (§1.1). | 🔴 blocker | S |
| 2 | Repo | **`__pycache__/` is not gitignored.** Running the tests leaves untracked files, and the next dispatch is refused with `workspace must be clean`. | 🔴 operational trap | XS |
| 3 | Integration | **Receipts never record which model actually ran.** `observed_configuration` is hardcoded to `unknown`. `claude -p --output-format json` reports the exact resolved model, cost, and permission denials, and the harness discards it. | 🟠 truth gap | S |
| 4 | Integration | **The latest-model picker is wrong.** `fleet_state.choose()` sums digits, so `cursor-grok-4.5-high` beats `cursor-grok-5-high`, and a date-stamped *old* Claude ID beats a new one (reproduced, §3.3). | 🟠 wrong model chosen | S |
| 5 | Integration | **Hardcoded fallback IDs.** `FALLBACKS` pins `gpt-5.6-*`, `cursor-grok-4.5-high`, `composer-2.5`, `gemini-3.x-*`. In Phase 1, **4 of 9 seats were bound to these guesses** because the `agent`/`agy` probes came back empty. This is exactly the "stuck on manual models" problem. | 🟠 | M |
| 6 | Integration | **The agy probe likely can't parse `agy models`.** It lists display strings like `Gemini 3.1 Pro (High)`, but the parser only accepts slug-like tokens. The agy `--model` value format is also unverified **[verify on Mac]**. The agy lane has never run a real dispatch. | 🟠 unproven lane | S |
| 7 | Repo | **No loop driver.** The "orchestrator follows up until done" step only happens while a human keeps a chat open. Phase 1 needed 24 tasks for 7 features, each one a manual hop. | 🟠 vs. your goal | L |
| 8 | Repo | **The chair is still Opus-centric in policy.** The inventory has `brain`=Claude Opus, `brain_fable`, and `brain_codex`=Sol, with no Sonnet, Cursor, or agy chair. The brain prompt is free text with no structured verdict, so a non-Claude chair can't be driven mechanically. | 🟠 vs. your goal | M |
| 9 | Flow | **Serial only.** One workspace lock plus a clean-tree rule means only one provider works at a time. Parallel work in git worktrees is the biggest throughput lever for spreading load across subscriptions. Phase 1 deliberately excluded it. | 🟡 throughput | L |
| 10 | Flow | **Avoidable worker STOPs.** 5 Phase 1 STOPs were "aggregate/final banner unavailable", i.e. a worker couldn't *see* the end of test output. Verification is already mechanical (exit code via `verify-mission.sh`), so the banner requirement only adds friction. | 🟡 cost | XS |

Items 1, 2, 3, 4 and 10 are small and safe: Phase 1 hygiene, not new scope.
Items 5–9 are **Phase 2** and need a mission with Gate 0. §4 has a draft feature list.

---

## 1. Scale one — the whole repository

### 1.1 Verified health (what I ran)

| Check | Result | Evidence |
|---|---|---|
| GitHub CI on `840a777` | **failure** | [Actions run 22](https://github.com/hashorva/purrfect-harness/actions/runs/37526279386): `shellcheck scripts/*.sh tests/*.sh` exits 1 |
| Local ShellCheck 0.11.0 | pass | `shellcheck` rc=0 |
| `bash tests/run-tests.sh` (Linux, clean worktree, `PYTHONDONTWRITEBYTECODE=1`) | **1 FAIL** | `dirty tagged update source is rejected by real updater` |
| `bash tests/run-tests.sh` (Linux, default env) | **2 FAIL** | adds `ExecutionSpec focused test leaves no scripts bytecode` |

**Root causes:**

1. **ShellCheck version skew.** CI installs ShellCheck from Ubuntu's apt, which is
   older than the 0.11 you have locally. The old version reports functions that
   only run from a `trap` (`cleanup()` in `spawn-worker.sh`/`spawn-brain.sh`) as
   **SC2317**. The scripts only suppress **SC2329**, the code 0.11 uses for the
   same thing. The CI log also shows an SC2015.
   *Fix:* pin ShellCheck in CI (download the 0.11 release binary) **and**
   suppress both codes: `# shellcheck disable=SC2317,SC2329`.
2. **Bashism inside `sh -c`.** `tests/run-tests.sh:490` runs
   `test "$(< file)" = …` inside `sh -c`. On Linux `/bin/sh` is `dash`, where
   `$(< file)` expands to an empty string, so the check fails although the updater
   correctly refused. I confirmed the updater does refuse, by hand, with
   `ERROR: … tagged harness source must be clean`. It passes on your Mac only
   because macOS `sh` is bash. *Fix:* `bash -c`, or `$(cat file)`.
3. **The bytecode check depends on the environment.** `run-tests.sh:77-80` runs
   the Python tests without `PYTHONDONTWRITEBYTECODE`, then asserts that
   `scripts/__pycache__` is absent. *Fix:* `export PYTHONDONTWRITEBYTECODE=1` at
   the top of `run-tests.sh`, and set it in `ci.yml`.
4. **Hygiene (not a test failure, but it bites in real use):** `.gitignore`
   contains only `.DS_Store` and `.tasks/`. Any Python run that writes bytecode
   leaves `scripts/__pycache__/` and `tests/__pycache__/` untracked. Then
   `dispatch_policy.clean_workspace()` refuses the next dispatch. *Fix:* add
   `__pycache__/` and `*.pyc` to the kit `.gitignore` **and** to the consumer
   payload. Ignored files don't count as dirty for `git status --porcelain`.

> These are one small PR and one patch release, `2.3.2`. They restore the
> "green before Phase 2" baseline that the Phase 1 GOAL itself required. The
> lesson (a local-only toolchain gave a false green) also belongs in
> `guard-verification`.

### 1.2 Architecture — what's genuinely strong

Phase 1 is good engineering. Keep it as the foundation:

- **The four-truths chain** (spec → receipt → verification → acceptance), keyed
  by one UUID with byte-hash links, immutable and atomically written. Few
  harnesses get this right. The F007 reconstruction archive proves it works end
  to end.
- **Fail-closed preflight** before any lock, spec, or process exists.
- **One shared provider adapter** (`execute_provider.py`) plus a runner that
  supervises the whole process tree. Adding a provider is now one function, not
  four shell branches.
- **Manifest-driven distribution** (`harness-manifest.json`), with install/update
  respecting ownership.
- Negative regressions at real entry points (the `guard-verification` discipline).

### 1.3 Architecture — gaps measured against *your* purpose

Your stated purpose is to use your subscriptions by assigning work to other
vendors' models, while a chair of any vendor keeps progress updated and follows
up until the mission is done.

| Your requirement | What exists today | Gap |
|---|---|---|
| Chair can be Sonnet, Terra, Cursor… | `spawn-brain.sh --provider` accepts any of the 4 CLIs. `freeze` can bind the `brain` role to any inventory seat. | Inventory *proposes* a brain only as Opus, Fable or Sol. Docs and skills say "Opus by default" in 6+ places. The brain's output is free text, so nothing downstream can act on a Cursor or Codex chair's verdict without a human reading it. |
| Follow up **until the mission is reached** | Each brain run is one shot (`mission-init`, `gate0`, `review`). The loop lives in a human chat. | **No loop driver**, no "plan next task" brain action, no resumable state machine, no schedule or wake-up. |
| Use subscriptions efficiently | Tiers (premium/economy) and routing criteria, all prose | No usage/cost ledger, no quota awareness, no parallel lanes. Every provider waits for the single lock. |
| Always the latest model | Live probe at Gate 0, then frozen IDs | Wrong ranking, hardcoded fallbacks, no observed model in receipts, frozen for the whole mission (3 weeks in Phase 1) |
| Works with *whatever* CLI you have | 4 hardcoded providers in 5 places (`PROVIDERS`, `CAPABILITIES`, `SEAT_SPECS`, `provider_contract`, `spawn-*.sh` case statements) | Adding Gemini CLI, opencode, Copilot CLI, etc. means code edits in 5 places plus schema changes |

### 1.4 Documentation drift (repo level)

- `MODEL_ROUTING.md`, `ORCHESTRATION.md`, `mission-init` and `dispatch-worker`
  still put vendor *product names of today* (Grok 4.5-era Cursor, Terra/Luna,
  Gemini Pro/Flash, "Opus by default") into **policy**. The README already says
  "the chair is a role". The policy files should say the same, and push names
  into a data file that can be regenerated (§3.4).
- `MODEL_ROUTING.md` → "Who chairs" has no rows for a Sonnet, Cursor or agy chair,
  which is what you actually want.
- `.claude/settings.json` pre-allows `npm`/`supabase` but **not the harness's own
  commands** (`bash scripts/spawn-worker.sh`, `bash scripts/verify-mission.sh`,
  `bash tests/run-tests.sh`, `shellcheck`). A Claude chair gets a permission
  prompt on every dispatch. `Bash(agy*)` is broader than everything else on the
  list. The `rm -rf` deny is right, but it also blocks cleaning `__pycache__`
  (I hit it during this audit). Gitignoring the folder removes the need.
- `fleet_state.py` is written in a compressed one-liner style (semicolon chains,
  single-line `def`s), unlike its sibling modules. It is now the
  most-changed module in Phase 2, so reformat it *first*, in its own
  behavior-neutral commit.

---

## 2. Scale two — each flow, one by one

The format for each flow: **works** / **problem** / **change** (effort).

### 2.1 Install / update / sync
- **Works:** the ownership manifest, `.harness-new` proposals, refusing on a dirty
  tree or untagged source, per-skill discovery symlinks.
- **Problem:** the payload doesn't ship a `.gitignore` fragment, so consumers
  inherit the `__pycache__` trap (§1.1-4). Discovery targets are 4 fixed
  directories. Newer CLIs (e.g. opencode, Copilot) read `.agents/skills`
  directly or use other paths.
- **Change:** add a managed `.gitignore` block, with markers, so the updater can
  refresh it safely (XS). Read `discovery_targets` from the provider registry
  (§3.4) instead of the manifest constant (S).

### 2.2 mission-init → Gate 0 → freeze
- **Works:** templates, honest degraded labelling, an immutable `fleet.json`
  written read-only with no-clobber.
- **Problems:**
  - The human hand-writes `.tasks/gate0-bindings.json`, which is error-prone.
  - Inventory seat names (`cursor.premium`, `brain_codex`…) are fixed in code.
  - The brain's default for `mission-init`/`gate0` is read from
    `inventory.seats.brain`, i.e. always Claude Opus, unless flags are passed.
- **Change:** `fleet_state.py propose --chair claude.premium` generates the
  bindings file from inventory plus a short role map ("chair=sonnet,
  premium=codex, economy=cursor, ui=agy"). Gate 0 shows it, the human edits one
  line, and freeze consumes it (S). With fleet v2 (§3.2), the Gate 0 decision
  becomes **which family per role and the freshness policy**, not which exact ID.

### 2.3 Dispatch (`spawn-worker.sh`)
- **Works:** snapshot self-re-exec, preflight before lock, trapped cleanup,
  timeout watchdog.
- **Problems:**
  - Eight separate `python3 -c` JSON extractions per spawn: slow and noisy.
  - Effort defaults to `medium` regardless of the seat.
  - Provider-specific defaults (`agent` → premium tier, `standard` speed) are
    duplicated in bash.
  - The worker prompt is one generic sentence; it doesn't pass the feature id,
    attempt number, or the "stop and report" contract.
- **Change:** a single `python3 scripts/dispatch.py worker …` entry point that
  outputs one JSON object (S). Effort and speed come from the frozen seat unless
  asserted (XS). Build the prompt from a template file in the manifest, so it can
  be tuned without touching code (XS).

### 2.4 Worker execution (adapter + runner)
- **Works:** process-group cleanup, outcome taxonomy, receipt always written.
- **Problems:**
  - Every provider runs in **text mode**, so nothing about cost, model, denials
    or turns is observed.
  - The Claude worker gets `--allowedTools Read,Write,Edit,Bash` without
    `--permission-mode`. Denied tool calls are silent unless JSON output is read
    (`permission_denials`).
  - agy's `--print-timeout 30m` is shorter than the runner's 40 min default, so
    two clocks disagree.
- **Change:** see §3.5. JSON or stream-JSON per provider, parsed into
  `observed_configuration` and a new `usage` block (M).

### 2.5 Review (brain `review` action)
- **Works:** review runs only while the mission is `in-progress`/`awaiting-gate`,
  with the frozen brain seat.
- **Problems:**
  - The review verdict is prose in `PROGRESS.md`. The *next* action (accept,
    write a correction task, escalate, stop) has to be inferred by a human.
  - The Claude-only `code-reviewer` subagent is not reachable from a Codex or
    Cursor chair.
- **Change:** brain review returns a **structured verdict** validated by a JSON
  schema: `{verdict, findings[], next_action, correction_task?}`. On Claude this
  is enforced with `--json-schema` (verified flag). On others it is enforced by
  the harness validating the last JSON block of output **[verify on Mac whether
  `codex exec` has an output-schema flag]**. This one change makes *any* vendor's
  chair drivable by a loop (M).

### 2.6 Verify / accept
- **Works:** same-snapshot verification, hash-bound acceptance, strict audit.
- **Problem:** a three-command sequence plus a Python one-liner for the hash,
  typed by the chair every time. Any Git-visible change between review and
  verification forces a whole *qualification task* (Phase 1 needed 7 of them:
  T-011…T-016, T-019).
- **Change:** `accept-feature.sh --run-id X` computes the hash itself and refuses
  unless a passing record exists (XS). Run verification *before* the brain
  review, so the snapshot hasn't moved yet, and have the brain write review
  notes to `.tasks/` (untracked), committing them only with acceptance. That
  removes most qualification tasks (S).

### 2.7 Human gates
- **Works:** gates registered in `PROGRESS.md`, and dispatch is blocked while
  `awaiting-gate`.
- **Problem:** gates are discovered by reading prose. Nothing notifies you.
- **Change:** the loop driver (§3.6) stops at a gate and notifies you. Options:
  a macOS notification, a GitHub issue comment, or a Claude Code routine or push
  notification if the chair is Claude. It writes a gate *summary file* you can
  approve with one command: `bash scripts/gate.sh approve G2 --notes "…"` writes
  the `PROGRESS.md` entry and the status flip (S).

### 2.8 Skillify / learning
- **Works:** evidence ≥2 → draft skill → approval.
- **Problem:** Phase 1 produced clear graduation candidates that aren't skills
  yet:
  - "local toolchain differs from CI"
  - "worker can't see the final banner"
  - "codex sandbox has a read-only `.git`" (only fixed in code)
- **Change:** run `skillify` over the Phase 1 `PROGRESS.md` now (XS, docs only).

### 2.9 PROGRESS.md growth
- **Problem:** the Phase 1 `PROGRESS.md` is 684 lines. Bearings say "last 3
  entries", but entries are long and a chair re-reads them on every action.
- **Change:** roll up `PROGRESS.md` per gate into `PROGRESS-archive/G1.md`, and
  cap entries at ~10 lines (pointers to evidence, not narrative) (XS).

### 2.10 Release / CI
- **Problem:** CI doesn't run on macOS, but the harness targets Mac Mini fleets
  first. The SC2317 skew and dash-vs-bash bugs show the matrix matters.
- **Change:** a CI matrix of `ubuntu-latest` and `macos-latest`, with ShellCheck
  pinned on both (S).

---

## 3. Scale three — integrating whatever CLI you have, always on the latest model

### 3.1 What each CLI can tell us

| CLI | Lists models? | Tracks latest by itself? | Reports the model it actually ran? | Structured output | Status |
|---|---|---|---|---|---|
| `claude` | Not needed: aliases `opus`, `sonnet`, `haiku`, `fable` | **Yes.** Tested here: `sonnet`→`claude-sonnet-5-5`, `opus`→`claude-opus-5-5`, `haiku`→`claude-haiku-4-5-20251001` | **Yes.** `--output-format json` → `modelUsage` keys, `total_cost_usd`, `permission_denials`, `num_turns` | `--json-schema`, `--output-format json/stream-json` | ✅ verified here (Claude Code 2.1.292) |
| `codex` | `~/.codex/models_cache.json` (current probe reads it) | No alias; the cache refreshes with the CLI | `exec --json` emits JSONL (`thread.started`, `turn.completed` with usage, `item.*`) | `--json`; output-schema flag **[verify on Mac]** | Partly verified (public docs) |
| `agent` (Cursor) | `agent models` (current code calls `agent --list-models`) | Cursor offers an `auto` model **[verify on Mac]** | `--output-format json` gives a single result object; whether it includes the model id is **[verify on Mac]** | `--output-format json/stream-json` | Partly verified (public docs) |
| `agy` | `agy models` prints **display strings** (`Gemini 3.1 Pro (High)`) | No | Unknown **[verify on Mac]** | Unknown | ⚠ The harness parser and the `--model gemini-3.1-pro-high` slug are probably wrong |
| Others (`gemini`, `opencode`, Copilot…) | — | — | — | — | Add as registry entries (§3.4) |

**Run this once on your Mac** and paste the results into the Phase 2 mission's
`evidence/`. It settles every **[verify]** above:

```bash
agent models; agent models --output-format json 2>&1 | head -c 2000
agy models
codex --version; jq '.models[0:5]' ~/.codex/models_cache.json
codex exec --help | grep -iE 'json|schema|model'
agent --help | grep -iE 'model|output|auto'
agy --help | grep -iE 'model|output|json|effort'
```

### 3.2 Making "fully automatic, even mid-mission" safe

Today's invariant is "Later live probes cannot silently change an active
mission." Your choice changes it to:

> **Live probes may change the model of an active mission, never silently.**

**How it works:**

1. **Freeze a policy, not an ID.** `fleet.json` v2 seat:
   ```json
   "codex.premium": {
     "provider": "codex",
     "family": "terra",
     "track": "latest",          // or "pinned"
     "pin": null,                 // concrete id when track=pinned
     "floor": "gpt-5.6-terra",   // never resolve below this
     "effort": "high", "speed": "unknown"
   }
   ```
2. **Resolve at every spawn.** `fleet_state.py resolve` reads a fresh inventory.
   It is cached with a short TTL (e.g. 6 h) and re-probed if older. It picks the
   newest model in the family that is at or above the floor and writes into the
   immutable ExecutionSpec:
   `resolved_configuration.model`, `resolution.{inventory_sha256, candidates[], rule}`.
   Execution truth is preserved: every run still records exactly what was
   authorized.
3. **Record what actually ran.** The adapter parses provider JSON into
   `observed_configuration.model` (§3.5). If observed ≠ resolved, the receipt is
   flagged `model_mismatch: true`. That's a review finding, not a silent pass.
4. **Drift is an event, not a surprise.** When the resolved model for a seat
   differs from that seat's previous run, the runner appends one line to
   `PROGRESS.md` (`model drift: codex.premium gpt-5.6-terra → gpt-5.7-terra`) and
   the brain sees it at review. Optional seat flag `drift: "pause"` sends the
   mission to `awaiting-gate` instead, for seats where you want a human to see
   the change first.
5. **A model that disappears doesn't kill the mission.** If the provider rejects
   the model at launch, the runner records `launch_failed` and the next attempt
   resolves the next candidate. Claude also gets `--fallback-model <next>`
   (verified flag).
6. **Gate 0 still exists**, but you approve *roles × families × policy* once,
   not a dozen version strings that rot in three weeks.

This amends a Phase 1 rule, so per your own `AGENTS.md` it needs a human gate.
It should be **F001 of Phase 2** (§4).

### 3.3 Fix the "latest" ranking (bug, reproducible today)

```text
$ python3 -c "from fleet_state import choose; ..."
choose(['cursor-grok-4.5-high','cursor-grok-5-high'],'grok')           -> cursor-grok-4.5-high   ✗ (4+5=9 > 5)
choose(['claude-opus-4-1-20250805','claude-opus-5-5'],'opus')          -> claude-opus-4-1-20250805 ✗ (date digits dominate)
choose(['gemini-3.1-pro-high','gemini-3.6-pro-low'],'pro')             -> gemini-3.1-pro-high    ✗ (effort suffix outweighs version)
```

**Replacement rule:** parse the version into a tuple (`5.10` > `5.6`, `5-5` → `(5,5)`),
strip a trailing `-YYYYMMDD` date (it only breaks ties), penalize `preview`,
`exp`, `fast` and `lite`, and use the effort suffix only to break ties between
identical versions. Add a regression test for each case above, so the
`guard-verification` rule holds.

### 3.4 Provider and family registry as data, not code

Replace the 5 hardcoded tables with a manifest-owned `providers.json` that
updates upstream like skills do:

```json
{
  "schema_version": 1,
  "providers": {
    "claude": {
      "probe": {"kind": "aliases", "aliases": ["opus","sonnet","haiku","fable"]},
      "families": {"opus": {"match": "^opus$|claude-opus"}, "sonnet": {}, "haiku": {}, "fable": {}},
      "efforts": ["low","medium","high","xhigh","max"], "speeds": ["unknown"],
      "argv": "claude_v2",
      "observe": "claude_json",
      "discovery_dir": ".claude/skills"
    },
    "agy": {
      "probe": {"kind": "command", "argv": ["agy","models"], "parse": "display_lines"},
      "model_arg": "display",
      "families": {"gemini-pro": {"match": "Gemini .* Pro"}, "gemini-flash": {"match": "Gemini .* Flash"}}
    }
  },
  "roles": {
    "chair":   {"prefer": ["claude:sonnet", "codex:terra", "agent:grok"]},
    "premium": {"prefer": ["codex:terra", "agent:grok", "claude:sonnet"]},
    "economy": {"prefer": ["agent:composer", "codex:luna", "claude:haiku"]},
    "ui":      {"prefer": ["agy:gemini-pro", "agy:gemini-flash"]}
  }
}
```

- `argv` and `observe` name small Python functions in `execute_provider.py`. That
  is the only code a new CLI needs, roughly 20 lines.
- **New models you haven't classified yet** show up at the next resolution as
  `unclassified` with a one-line notice ("agent offers `xyz-2` — map it to a
  family?"). They are never silently bound, and never ignored.
- The **policy docs (`MODEL_ROUTING.md`) shrink to the four routing criteria and
  the roles.** Today's product names live in `providers.json`, which a script
  can refresh.

### 3.5 Observed model, cost and usage per provider (adapter changes)

| Provider | Change in `provider_contract` | Parse into receipt |
|---|---|---|
| claude | add `--output-format json --no-session-persistence` and `--fallback-model` (all verified) | `observed.model` ← the single `modelUsage` key (or the largest if several, since subagents count), `usage.cost_usd` ← `total_cost_usd`, `usage.denials` ← `permission_denials` |
| codex | add `--json` | `usage.tokens` ← `turn.completed`; model from `thread.started` or config event **[verify on Mac]** |
| agent | add `--output-format json` | model and usage if present **[verify on Mac]** |
| agy | — until verified | stays `unknown` (as Phase 1 requires: no inference) |

Write the log as raw JSON(L). Keep a human `tail` by extracting the final
`result` text after the run. The receipt schema gains an optional `usage` object,
so v3 evidence stays valid.

### 3.6 A chair from any vendor, plus a loop driver that follows up until done

Your goal is a chair that keeps progress updated and follows up until the
mission is reached. Today that depends on a human keeping a chat open. Make it a
**deterministic driver that consults the chair only for judgment:**

```text
scripts/mission-run.sh [--until gate|done] [--max-spawns N] [--budget-usd X]

loop:
  state ← derive from files (GOAL status, features.json, fleet.json, receipts, verification/)
  if status == awaiting-gate        → write gate summary, notify human, EXIT 0
  if no pending features            → set awaiting-gate (final), notify, EXIT 0
  if open correction for feature F  → dispatch it
  else                              → spawn-brain plan-task F   (chair writes tasks/T-XXX.md as structured output; driver validates + commits)
  spawn-worker per task’s role seat → receipt
  verify-mission --run-id           → VerificationRecord
  spawn-brain review --run-id       → structured verdict {pass|fail|escalate, correction_task?}
  pass     → accept-feature, commit, continue
  fail     → commit correction task (attempt+1 ≤ limit) and continue
  escalate / attempts exhausted / budget hit → awaiting-gate + notify, EXIT
```

- **Any chair works.** The chair only has to return schema-valid JSON for
  `plan-task` and `review`. Sonnet 5.5, Codex Terra, and Cursor Grok are all
  interchangeable through `fleet.json` role `chair`.
- **Resumable by construction.** State comes only from committed files and
  `.tasks/`, never from memory. Kill it, reboot the Mac, rerun, and it continues.
- **"Follow up" means scheduling the driver:**
  - On the Mac: a `launchd` plist (or cron) runs `mission-run.sh --until gate`
    every N minutes. The workspace lock already prevents overlap.
  - With Claude as chair: a Claude Code `/loop` or a scheduled routine can run
    the same script.
  - Either way, the script is the engine and the scheduler is replaceable.
- **Budgets:** `--max-spawns` and `--budget-usd` (summed from receipt `usage`)
  stop the loop before an overnight run eats a subscription. Claude spawns also
  get `--max-budget-usd` per run (verified flag).

### 3.7 Parallel lanes (where multiple subscriptions pay off)

One lock per **worktree** instead of per repository:

- Each feature gets `git worktree add .tasks/wt/<run_id> <base>`, the worker runs
  there, and the receipt records that worktree's Git delta.
- Acceptance merges the worker's commits into the mission branch (fast-forward
  or merge commit), then re-verifies on the merged head.
- Disjoint `Files you MAY touch` lists between features in flight are checked
  *before* launch. Overlap means serialize.

This lets Codex, Cursor and agy each work on a different feature at the same
time. Claude's `-w/--worktree` exists (verified), but the harness should own the
worktree so every provider behaves the same. Phase 1 deliberately excluded
worktrees. This is Phase 2 F00x, after the loop driver.

### 3.8 Where Opus 5.5 / Sonnet 5.5 fit (only what was verified here)

Verified with the local `claude --help` and live calls:

- **Aliases follow new releases**: `opus` → `claude-opus-5-5`, `sonnet` →
  `claude-sonnet-5-5`. For Claude seats, `track: latest` needs no probe. Just
  record the observed ID.
- **Effort levels** `low|medium|high|xhigh|max`, already in `CAPABILITIES`.
- **`--json-schema`** for the chair's `plan-task`/`review` verdicts.
  **`--fallback-model`** for availability. **`--max-budget-usd`** per spawn.
  **`--agents`** to pass the read-only `code-reviewer` inline, with no
  `.claude/agents` dependency in consumers.
- **Suggested role defaults** (preferences you can override at Gate 0, not
  rules):
  - Opus 5.5 at `high` for the chair's `mission-init`/`gate0` (decomposition is
    where the strongest model pays off).
  - Sonnet 5.5 at `high` for routine `plan-task`/`review` turns (the loop calls
    these most often).
  - Haiku for mechanical tasks such as docs, renames and rollups.
  - Other vendors for implementation, according to your subscriptions.
- **Per-spawn floor cost:** even a one-word reply cost $0.04 (Sonnet) to $0.07
  (Opus) here, because each spawn loads the full context. That argues for fewer,
  better-scoped spawns: one feature per task, and no qualification re-runs
  (§2.6).

---

## 4. Proposed next steps

**Now: patch release `2.3.2`, no new scope, one PR**
1. CI: pin ShellCheck, add the `SC2317,SC2329` disables, `macos-latest` in the matrix.
2. Tests: `bash -c` instead of `sh -c` at `run-tests.sh:490`; export `PYTHONDONTWRITEBYTECODE=1`.
3. `.gitignore`: add `__pycache__/` and `*.pyc` (kit and consumer payload).
4. `fleet_state.choose()`: version-tuple ranking plus regressions (§3.3).
5. `.claude/settings.json`: allow the harness's own scripts.
6. Remove the "final banner" requirement from the worker template, since
   verification is by exit code.

**Next: Phase 2 mission draft (for `mission-init`, requires Gate 0)**

| Id | Feature | Depends on |
|---|---|---|
| F001 | Fleet v2: policy seats (`track`/`floor`/`pin`), per-spawn resolution recorded in the spec, drift events (§3.2) | 2.3.2 |
| F002 | Provider registry `providers.json` replaces the 5 hardcoded tables, with an unclassified-model notice (§3.4) | F001 |
| F003 | Observed model/usage in receipts for claude, codex and agent; agy after verification (§3.5) | — |
| F004 | Structured chair verdicts (`plan-task`, `review`) with schema validation, any provider (§2.5) | F002 |
| F005 | `mission-run.sh` loop driver with budgets, gate notification and resume (§3.6) | F003, F004 |
| F006 | One-command gate approval and `PROGRESS` rollup (§2.7, §2.9) | F005 |
| F007 | Worktree lanes with parallel dispatch across providers (§3.7) | F005 |
| F008 | Real smoke: a chair other than Claude drives a 3-feature mission on 3 vendors, overnight, to a gate | all |

**Decisions only you can make:**
1. Approve amending the Phase 1 rule "live probes cannot change an active
   mission" to "**may change, never silently**" (§3.2).
2. Default `drift` behavior: `log` (fully automatic, as you chose) or `pause`
   for some seats, e.g. the chair.
3. Budget defaults for an unattended `mission-run`, per night and per spawn.
4. Notification channel at gates: macOS notification, GitHub issue, or
   Claude routine/push.

---

## Appendix A — evidence log (commands run in this audit)

- `git fetch origin` → `3d690b3..840a777`. The working branch was rebased onto
  `origin/main` before auditing.
- CI: [run 37526279386](https://github.com/hashorva/purrfect-harness/actions/runs/37526279386).
  Conclusion `failure`, job `lint-and-test`, SC2317 in `spawn-worker.sh` cleanup.
- `shellcheck --version` → 0.11.0, rc=0 on `scripts/*.sh tests/*.sh`.
- `PYTHONDONTWRITEBYTECODE=1 bash tests/run-tests.sh` in a clean worktree
  (Linux) → 1 FAIL (`dirty tagged update source …`).
- Manual repro: on a tagged fixture with a dirty README,
  `harness-manifest.py --require-release validate` → `ERROR: … must be clean`,
  rc=1. The updater is correct and the test is not.
- `ls -l /bin/sh` → `dash`. `sh -c 'echo "[$(< /etc/hostname)]"'` → `[]`.
- `claude -p … --output-format json --model {haiku,sonnet,opus}` →
  `modelUsage` keys `claude-haiku-4-5-20251001`, `claude-sonnet-5-5`,
  `claude-opus-5-5`. `total_cost_usd` 0.013 / 0.038 / 0.071.
- `fleet_state.choose()` repro in §3.3.
- Phase 1 stats from `docs/missions/20260821-execution-truth/`: 7 features, 24
  task files (incl. 5 `-R` corrections and 7 qualification tasks),
  `PROGRESS.md` 684 lines, 4/9 fleet seats bound by `fallback`.

## Appendix B — external sources (for the [verify on Mac] items)

- Codex `exec --json` event types: [codex exec JSONL reference](https://codex.danielvaughan.com/2026/04/08/codex-exec-jsonl-reference/), [Mintlify Codex exec docs](https://www.mintlify.com/openai/codex/cli/exec)
- Cursor CLI `agent models`, `--output-format json|stream-json`: [Cursor CLI cheat sheet](https://www.scriptbyai.com/cursor-cli-cheat-sheet/), [Cursor docs — output format](https://docs.cursor.com/ko/cli/reference/output-format)
- Antigravity `agy models` display strings, `-p` headless: [Antigravity CLI headless docs](https://antigravity.google/docs/cli/headless), [antigravity-cli skill notes](https://tessl.io/registry/skills/github/NousResearch/hermes-agent/antigravity-cli)
