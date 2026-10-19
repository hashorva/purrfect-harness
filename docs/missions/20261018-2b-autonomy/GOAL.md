---
status: in-progress
owner: Zamir
orchestrator: opus
created: 2026-10-18
intake: owner spec 2026-10-18 (dark factory, items a-h), owner changes 2026-10-18 (F000 safety net first, run order with F004 before F003, measurable F001, status generated from progress.jsonl), docs/proposals/20261014-phase-2.md (sections 6-10, 13), docs/proposals/20261016-structured-progress.md, docs/proposals/20261015-parallel-dispatch.md (section 5), 2A DAY 6 REPORT
---

# Goal

## Mission (2–4 sentences, outcome not tasks)

Mission 2B "The Dark Factory": a prompt goes in. The planner splits it into tasks small enough for economy seats, and workers build with their full abilities. Deterministic checks judge every piece. Failures are re-prompted automatically and broken tools are repaired first. The factory stops only at the goal or at a real blocker, with no human in the loop between gates.

## Why now / forcing function

2A (v3.1.0) made every run provable and the fleet native-only, but a human still drives each step. There is no quota meter: the 2A pause notes are error text, and they are not trusted. The median planning run costs 1.23M tokens (1.82M on Claude Opus). PROGRESS.md is still written by hand. CI does not re-check the 2A evidence or the old provider argv: in T-115, T-071 had changed the codex argv for contracts 2–9 and 76 historic receipts stopped validating, and nothing caught it in time. 2A is done, so this folder can go `approved` → `in-progress` after Gate 0 without a second active mission.

## In scope

Features in `features.json`, in the owner's run order (`run_order`; each `priority` is its position in that list):

0. F000 Safety net (owner change 2026-10-18), first. It adds:
   - golden argv tests for every existing provider contract;
   - the 2A evidence audit in CI;
   - CI on Python 3.12 and 3.14, on Linux and macOS;
   - test discovery by file pattern;
   - one shared run-id validator;
   - the promoted lessons, applied;
   - the 2A PROGRESS.md, refreshed and frozen.
1. a → F001 Delegation and full ability, measured. The explorer subagent shows in receipts, the prompts carry a per-run token budget, and batches of 10 clean runs before and after the change are compared. The target is a planning-run median under 1M tokens, with no drop in review verdict quality.
2. b → F002 Quota meter: real usage screens, the 2% floor, expiring quota first, native-only, pauses that end at the vendor-shown reset, and a training set.
3. d → F004 Structured progress: progress.jsonl, progress.py and a generated PROGRESS.md. It comes before F003 so the loop writes progress events from its first run.
4. c → F003 Loop driver: dispatch → checks → review → fix → re-review. A broken seat or tool is repaired first.
5. e → F005 Worker inner loop: ruff, a type checker and shellcheck. Lint and type errors get a resumed repair; logic errors get a fresh run.
6. f → F006 Task-size signal: more than 2 review rounds sends the task back to the planner to split.
7. g → F007 Parallel lanes, minimum slice: two disjoint tasks, two providers, one serial merge.
8. h → five features:
   - F008 static board;
   - F009 held-out benchmark;
   - F010 Front Desk skills for every CLI;
   - F011 prediction model;
   - F012 OS-level Bash sandbox for Claude bypassPermissions workers.

Item h is five features, so each one is accepted on its own evidence (Gate 0 decision 1). The ids F001–F012 keep their meaning; only the run order changed.

## Explicitly OUT of scope (workers: do not touch)

- The 2A mission directory. It is read-only input (`routing-data.jsonl` is the token baseline), with one exception: F000 step 8, the orchestrator's final refresh of the 2A PROGRESS.md and its `PROGRESS.md.sha256` freeze record. The committed 2A receipt fixture lives under `tests/fixtures/mission-2a/`, not in the 2A directory.
- Proposal items not in the owner list: anti-gaming checks, lessons intake, the STE rewrite (X-003), and the overnight non-Claude-chair smoke.
- Fast modes, usage credits, API billing and X-FAST.
- A `grok` provider. Grok stays on `cursor-agent`.
- Cross-vendor seats: no vendor's door resolves another vendor's family (2A T-100). There is no agy seat for Opus, Sonnet or GPT-OSS.
- In lanes: more than two lanes, the same provider twice, or a Codex lane. Also out: parallel planner runs, parallel acceptance and automatic merge resolution.
- Live `claude`, `codex`, `cursor-agent`, `agy`, or `drive-cli.sh` against a real CLI, inside `tests/run-tests.sh` or in CI. Live checks are local-only task verification commands.
- Letting the prediction model dispatch or override the 2% floor.

## Constraints

- Hard rules: see AGENTS.md — all apply.
- Run order: features run in the `features.json` `run_order`. The next feature starts when the previous one is accepted, with one exception for F001 step 6. That step needs 10 clean planning runs made after the F001 prompt change, and these accumulate during F002, F004 and F003 work. F001 steps 1–5 finish before F002 starts. Step 6 is decided as soon as the after batch exists.
- Native-only: every model runs only on its own vendor's quota.
  - claude: Opus, Sonnet, Haiku.
  - codex: Sol, Terra, Luna.
  - agy: Argon, Flash.
  - cursor: Composer, Grok.
- Repair and escalation stay inside the vendor: haiku → sonnet → opus; luna → terra → sol; composer → grok; flash → argon.
- Effort by role:
  - brain (planner): high;
  - reviewers: medium;
  - economy workers: medium;
  - premium workers: medium, and only on escalation or for a guard task the planner justifies.
- Token budget by role, stated in each brain prompt (F001 step 5): planning 1,000,000, review 400,000, as total tokens per run. The prompt tells the model to stay within the budget by delegating reading and searching to the explorer subagent.
- Review rule: the reviewer is a different vendor than the worker (fleet-proposal.md). Claude Opus reviews guard and safety code, so guard tasks never go to a Claude worker. Most F000 tasks are guard code.
- Quota rule (replaces the 2A 80%/70% pool stop; Gate 0 decision 2): dispatch only if percent left minus the batch forecast is greater than 2 on every window the vendor shows for that pool. An unknown reading is refused. Among allowed pools, the soonest reset wins.
- Pauses end at the reset time on the vendor usage screen. Never trust a reset time parsed from error text. An unparsable screen is `unknown`, and the meter probes again after 30 minutes.
- Every number carries a source flag: `observed`, `estimated`, or `unknown`. Never guess.
- Runtime Python is the standard library. Dev tools (`ruff`, the type checker) are installed only with `uv tool install`.
- New scripts and schemas are registered in `harness-manifest.json` in the same task (distribution ownership stays in the manifest).
- Real CLI behaviour first: before a task relies on a CLI feature (a flag, a usage screen, a stream event), a recorded real `--help` output or a real stream or screen capture is committed under `evidence/`, and the task cites it.
- Provider contract: any adapter argv change ships as a new provider contract number in the same task, with new golden entries (F000 step 1). Existing golden entries and old receipts never change. Background: in 2A T-115, T-071 had changed the codex argv for contracts 2–9 and 76 historic receipts stopped validating.
- Run ids are checked only by `scripts/run_id.py` once F000 is accepted. No script parses run ids itself.
- Verification bullet format:
  - Each bullet is one Markdown code span whose text is a JSON argv of non-empty strings, with no backtick inside the span.
  - Tests are named by file and `Class.method`, as `["env","PYTHONDONTWRITEBYTECODE=1","python3","tests/<file>.py","<Class>.<method>"]`, never `python -m unittest <path>`.
  - The full test file, `shellcheck scripts/*.sh tests/*.sh`, `bash tests/run-tests.sh`, the clean-tree check and the no-`__pycache__` check are each their own bullet.
  - Allow-list bullets are backtick-quoted paths only.
- Workers run only their oracle and named tests. The full suite runs at verification and in CI, never inside a worker attempt.
- Frozen oracle: verification commands are frozen at the task commit and cannot change for that run. A bad oracle needs a new task or a retry with a real change, never an edit of the frozen commands. The verifier checks a run against that run's own commit.
- Rule 6: before a task is committed, the planner or the Front Desk runs its oracle in a scratch clone. The oracle must fail on the base and pass after the reference patch (kept outside the repo tree).
- Planner runs write as many task files as the request needs; each task stays at most 150 changed lines and must not collide with another task in the same batch (no shared allow-list files). Planner output is plain task files in four-backtick fenced blocks or `=== FILE: <path> ===` blocks.
- Flaky is failing. A test that passes only on rerun is a failure: never skip it, wrap it in a retry or loosen it; make it deterministic. Tests synchronise on files, events or fake clocks, never on sleeps.
- CI runs ubuntu-latest and macos-latest, with Python 3.12 and 3.14 on each from F000 on, and installs tmux, jq and jsonschema. It must be green on every gate commit. From Gate 1 on, a green run also includes the golden-argv check and the 2A evidence audit.
- Progress and status:
  - Workers never edit `features.json`, `fleet.json` or `PROGRESS.md`.
  - Until F004 is accepted, the orchestrator writes the 2B PROGRESS.md by hand.
  - From F004 acceptance on, 2B status is generated from `progress.jsonl` by `scripts/progress.py` and is never hand-written. `render --check` also checks the GOAL.md front-matter status.
  - The F003 loop writes progress events from its first run.

## Architect instructions (read before you change features.json)

- Keep the ids F000–F012. Do not renumber. You may tighten steps. Do not drop:
  - the 2% floor;
  - the unknown-not-guessed rule;
  - native-only;
  - the in-vendor ladder;
  - the new-contract-for-new-argv rule.
- `run_order` is the order. Each feature's `priority` equals its index in `run_order`.
- The first planner run after Gate 0 writes F000 tasks. F000 tasks take the next free ids from T-003 on. T-001 and T-002 keep their F001 meaning and are dispatched after F000 is accepted:
  - T-001 is the first slice of F001: the stdlib measurement tool and its fixture tests, new files only. F000 step 5 runs its test by discovery.
  - T-002 adds the ledger planning rows and the receipt and ledger subagent fields (F001 step 2).
- Every feature stays `passes: false` and `bootstrap: false`.
- A step a script cannot decide is a defect. Rewrite it until a command can decide it.

## Fleet

See `fleet-proposal.md` (bindings JSON, policy JSON, review pairing). Gate 0 runs `bash scripts/fleet-doctor.sh` and `bash scripts/fleet-inventory.sh` first, then `freeze-v2` with the approved bindings. Dispatch reads only `fleet.json`.

Tier chosen at GATE 0: mixed (economy first), proposed.
Orchestrator (brain): claude / Opus, effort high. Fallbacks are `brain_argon` (agy / Argon high) and `brain_codex` (codex / Sol high), each on its own vendor's quota. Proposed.

## Budgets (confirmed at Gate 0)

- Per spawn: 40 min wall time.
- Per 24 h: at most 24 worker runs, 24 review runs and 8 planner runs. The loop stops at the cap, not at a guess.
- Per pool: the 2% floor (above). Never credits, never fast modes.
- Per run, stated in the prompt: planning 1,000,000 total tokens, review 400,000.
- Planning tokens:
  - Target: median under 1,000,000 total (input + output + cache read) per planning run, measured by `scripts/planning_stats.py`.
  - F001 compares a before batch and an after batch of 10 clean runs each, on tokens per run (the parent total, and the parent plus subagent total) and on done rate.
  - A single planning run over 3,000,000 is listed in the next gate report.
- Per task: at most 2 worker attempts per rung, and at most 2 review rounds before the F006 split signal.
- Mission estimate: about 60 tasks, 92 worker runs, 78 review runs and 43 planner or gate runs (estimates.md).

## Risks

1. Usage screens may change format or be boxed TUI panels. drive-cli stalls (exit 4) on boxed menus and alt-screen clears (a 2A residual). Mitigation: F002 starts with real captures. An unparsable screen is `unknown`, and the factory waits safely rather than guessing.
2. Claude Pro is shared by the planner, the Opus reviewer, the Front Desk and claude.ai chat, and F000's guard reviews lean on Opus. Mitigation: the meter sees the shared use. The planner fallbacks run on Argon or Sol quota, never through another vendor's door.
3. Claude workers run unattended with `bypassPermissions` before F012. Bash is a net, not a wall (evidence/claude-unlock-residual-risk.md), and the owner order puts F012 last. Mitigation: no Claude worker is dispatched while F012 is open. F003 step 5 makes the loop enforce this, and the Front Desk follows the same rule by hand until then.
4. Plan defects dominate failures (2A: 5 of the first 6 failures were plan text). Mitigation: rule 6 for every task, the size cap and the F006 split signal.
5. The loop could run away or spend silently. Mitigation: per-24h caps, a forecast before every batch, a stop when the ladder is exhausted, and gate-wait as a terminal state.
6. Hot files (`tests/run-tests.sh`, `harness-manifest.json`, `.github/workflows/ci.yml`) block lane pairs, and F000 rewrites the runner. Mitigation: F000 runs serially before any lane. F007 admission refuses overlap, and the lane demo tasks are chosen for disjoint files.
7. The F001 1M target may not be met, or the after batch may not be complete by Gate 2. Mitigation:
   - Gate 2 then reports F001 step 6 as pending, with the measured partial median.
   - F001 is accepted by Gate 3 at the latest, or it stays `passes: false` with the measured median in the gate report.
   - Later features still proceed, because they do not depend on the target.
8. F011 needs 300 kept forecasts, which may not be reachable within this mission. Gate 6 then records an owner amendment, not a relaxed step.
9. A 2A receipt may fail the ledger privacy check as it is. Any scrub changes the sha256 recorded in its VerificationRecord. Mitigation: F000 step 3 stays false and the Gate 1 report names the failing receipts. The owner decides on a new task (for example, a redaction-aware record); the audit is never loosened.
10. Python 3.14 may break tests that pass on 3.12 (deprecations, changed defaults). Mitigation: fix the code. Never drop or pin away 3.14.

## Human gates

Owner approval is required at every gate. The loop stops in `gate-wait` and dispatches nothing until the verdict is recorded.

- **GATE 0 — Package.** The owner approves this package (GOAL, features.json, fleet-proposal.md, estimates.md, T-001). Gate 0 also needs a fresh fleet inventory and `freeze-v2`, and the brain receipt (`verify-mission.sh`). Decisions:
  1. Item h becomes F008–F012.
  2. The 2% floor replaces the 2A 80%/70% pool stop.
  3. Type checker: `ty` via `uv tool install ty` (fallback `mypy`), confirmed by a real `--help` capture.
  4. Prediction threshold: 300 kept batch forecasts with before and after readings.
  5. Order: the owner's `run_order`. F000 comes first, F004 runs before F003, and F012 sits in the F008–F012 group. While F012 is open, no Claude worker seat is dispatched (F003 step 5).
  6. The budgets above, including the per-run token budgets of 1,000,000 for planning and 400,000 for review.
  7. The mid seats `claude.mid` (Sonnet) and `codex.mid` (Terra) are frozen now and become dispatchable after F005.
  8. T-001 creates new files only and waits for F000. Once F000 step 5 lands, its test runs by discovery, so T-002 needs no wiring.
  9. The PROMOTE list for F000 step 7: the PROMOTE items of the 2A lesson proposal (2A PROGRESS.md, "Lesson proposal for you"), plus two owner rules. A changed adapter argv ships as a new provider contract number, and tests synchronise on events, never on sleeps.
  10. F001 measurement: before and after batches of 10 clean claude.brain-planning runs. The after done rate must not fall below the before done rate. Explorer tokens count in the parent-plus-subagent total, so delegation cannot hide cost.
- **GATE 1 — Safety net.** Held after F000. CI is green on all four jobs (two operating systems × Python 3.12 and 3.14), with the golden-argv check and the 2A evidence audit. The 2A PROGRESS.md is frozen.
- **GATE 2 — Cost visible.** Held after F001 and F002. The factory measures its own tokens and quota. F001 step 6 may still be pending (risk 7).
- **GATE 3 — Recorded loop.** Held after F004 and F003. The factory runs its loop and records every stage as progress events. This is the first gate recorded as a `gate` event.
- **GATE 4 — Self-repair.** Held after F005 and F006. The factory repairs its own work and re-splits it.
- **GATE 5 — Two lanes.** Held after F007. Two lanes run in parallel and merge serially.
- **GATE 6 — Full factory.** Held after F008–F012.

When a human gate is reached:

1. Run `bash scripts/verify-mission.sh` (it must exit 0).
2. Confirm that CI is green on the gate commit.
3. Set `status: awaiting-gate`.
4. Get the human verdict and record it:
   - Gates 0–2: a **Human — GATE n** entry in the hand-written 2B PROGRESS.md.
   - From Gate 3 on: a `gate` event with `by: human` in `progress.jsonl`, written with `progress.py add`.
5. Set `status: done` or `in-progress`.

Chat approval alone is not the record — receipts are.

## Source of truth

The binary checklist and the run order live in `features.json` in this mission folder. This file is narrative only — if they disagree, features.json wins.

## Status lifecycle

`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` (optional) → `done`
