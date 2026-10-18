---
status: draft
owner: Zamir
orchestrator: opus
created: 2026-10-18
intake: docs/proposals/20261014-phase-2.md (section 13), docs/proposals/20261016-structured-progress.md, docs/proposals/20261015-parallel-dispatch.md (section 5), owner list of 2026-10-18
---

# Goal

## Mission (2–4 sentences, outcome not tasks)

Mission 2B "Autonomy" makes Phase 2 yield per token: a quota meter, then a scripted loop the Front Desk starts, watches and reports. The meter reads percent left and reset time per pool, spends the quota that expires soonest, and keeps every reading as the training set. Later gates add structured progress, the worker's own check-and-repair loop, a task-size signal, a two-lane merge, a phone-readable board, a held-out benchmark, Front Desk skills, and a prediction model that does not override the meter.

## Why now / forcing function

2A made runs provable. There is still no quota meter: day-5 pause notes are error text and are not trusted. PROGRESS.md is still written by hand. This folder stays `draft` while 2A is the active mission (`docs/missions/20261014-2a-foundation`, status `in-progress`). A second `in-progress` GOAL would make `scripts/active-mission.sh` fail.

## In scope

- Features F001–F010 in `features.json`, in that order.
- Owner order, which replaces the proposal's 2B numbering: quota meter, loop driver, structured progress, worker inner loop, task-size signal, parallel lanes (minimum slice), static board, held-out benchmark, Front Desk skills, prediction model.
- The structured-progress proposal is Gate 2, not the first feature. The parallel-dispatch minimum slice is Gate 3, not the start of the mission.

## Explicitly OUT of scope (workers: do not touch)

- The 2A mission directory, and accepting 2A features.
- Proposal items not in the owner list: anti-gaming checks, lessons intake, the STE rewrite (X-003), and an overnight smoke mission.
- Fast modes, usage credits, API billing, and X-FAST.
- A `grok` provider. Grok stays on `cursor-agent`, inside the cursor ladder.
- More than two parallel lanes, the same provider twice, a Codex lane, parallel Architect runs, parallel acceptance, and automatic merge resolution.
- Live `claude`, `codex`, `cursor-agent`, `agy`, or `drive-cli.sh` inside tests.
- Letting the prediction model override the 98% rule.

## Constraints

- Hard rules: see AGENTS.md — all apply.
- Every number carries a source flag: `observed`, `estimated`, or `unknown`. Unparsable text stays `unknown`. Never guess.
- The 98% rule replaces the 2A pool stop (80% of a 5-hour window, 70% of the weekly cap). Dispatch only if percent left minus the forecast is greater than 2, on the 5-hour window and on the weekly window, with the same comparison. Gate 0 confirms this replacement.
- Choosing a pool may prefer the soonest reset across vendors. After a task starts, repair and escalation stay inside that vendor: claude haiku → sonnet → opus; codex luna → terra → sol; cursor composer → grok; agy flash → argon → opus-on-agy. An agy pause does not select a claude seat.
- Pauses end at the reset time on the vendor usage screen. Re-read after that time. Never trust a reset time parsed from error text. If the new read is unknown or still over the rule, probe again after 30 minutes.
- Runtime Python stays the standard library. Draft dev tools, confirmed at Gate 0: `ruff` and `ty`, installed only with `uv tool install`.
- Draft prediction threshold, confirmed at Gate 0: 300 kept readings.
- Verification bullets are one Markdown code span whose text is a non-empty JSON argv of non-empty strings, with no backtick inside the span.
- A test command names the file and `Class.method`. The full file and `bash tests/run-tests.sh` are their own bullets.
- Verification commands are frozen at the task commit. The verifier reads that commit. A bad oracle is a new task with a real change, not an edit of the frozen commands.
- The verifier checks a run against that run's own commit. A later commit does not make the old run pass.
- A planner run writes at most 3 task files. This run writes T-001 only.
- Workers never edit `features.json`, `fleet.json`, or `PROGRESS.md`.
- `scripts/progress.py` is the only PROGRESS writer, and only after F003. Until then the loop writes `loop-state.json`, not PROGRESS.md.

## Architect instructions (read before you change features.json)

- Keep ids F001–F010. Do not renumber. You may tighten steps. Do not drop the 98% rule, the unknown-not-guessed rule, or the vendor ladder.
- T-001 is the parser slice of F001 (steps 1 and 2). It does not implement snapshots, the ledger column, dispatch, pauses, or drive-cli capture.
- Every feature stays `passes: false` and `bootstrap: false`.
- A step a script cannot decide is a defect. Rewrite it until a command can decide it.
- At most 3 tasks per planner run.

## Fleet (proposal and narrative copy of this mission's frozen fleet.json)

Proposal only. Not a new probe. Copied from the 2A frozen fleet recorded in that mission's PROGRESS.md on 2026-10-18. Gate 0 runs `bash scripts/fleet-doctor.sh` and `bash scripts/fleet-inventory.sh` and replaces this table. Error-text pause notes from 2A are not meter readings.

Tier chosen at GATE 0: mixed (economy first), proposed.
Orchestrator (brain): Opus, effort high, proposed. The door is not frozen. 2A's chair is `agy` / `claude-opus-5-5-high`.

Verified local CLIs: not re-checked in this draft. 2A recorded claude, codex, cursor-agent, agy, and grok, with `grok` not a provider.

### Proposed seat binds (from the 2A fleet — edit only with human GATE 0 approval)

| Seat | CLI | Model | Family | Health | Source |
| --- | --- | --- | --- | --- | --- |
| brain | agy | claude-opus-5-5-high | opus | copied, not re-probed | 2A fleet 2026-10-18 |
| cursor.premium | cursor-agent | grok-4.7-high | grok | copied, not re-probed | 2A fleet 2026-10-18 |
| cursor.economy | cursor-agent | composer-2.5 | composer | copied, not re-probed | 2A fleet 2026-10-18 |
| codex.premium | codex | gpt-5.6-terra | terra | copied, not re-probed | 2A fleet 2026-10-18 |
| codex.economy | codex | gpt-6-luna | luna | copied, not re-probed | 2A fleet 2026-10-18 |
| agy.premium | agy | gemini-4-argon-high | argon | copied, not re-probed | 2A fleet 2026-10-18 |
| agy.economy | agy | gemini-3.8-flash-medium | flash | copied, not re-probed | 2A fleet 2026-10-18 |
| claude.premium | claude | sonnet | sonnet | copied, not re-probed | 2A fleet 2026-10-18 |
| claude.economy | claude | haiku | haiku | copied, not re-probed | 2A fleet 2026-10-18 |

Spawn helpers (prefer these so logs land in `.tasks/logs/`):

| Worker | Economy | Premium |
| --- | --- | --- |
| cursor (`agent` legacy key) | `bash scripts/spawn-worker.sh agent <task> --tier economy --feature F00X --effort <approved> --speed <approved>` | same flags with `--tier premium` |
| codex | `bash scripts/spawn-worker.sh codex <task> --tier economy --feature F00X --effort <approved> --speed <approved>` | same flags with `--tier premium` |
| agy | `bash scripts/spawn-worker.sh agy <task> --tier economy --feature F00X --effort <approved> --speed <approved>` | same flags with `--tier premium` |
| claude | `bash scripts/spawn-worker.sh claude <task> --tier economy --feature F00X --effort <approved> --speed <approved>` | same flags with `--tier premium` |

Freeze the human-approved bindings with `scripts/fleet_state.py freeze` as described in the mission-init skill. Dispatch reads only `fleet.json`. Per-task `invocation:` documents the approved bind; `--model`, `--effort`, and `--speed` are equality assertions and cannot override the frozen seat. Worker dispatch requires `status: in-progress` and a committed task. Cross-repository execution is disabled.

Proposed budgets, confirmed at Gate 0: per spawn 40 min; per night max 12 worker + 4 Architect runs; pool stop is the 98% rule; never credits; never fast modes.

## Human gates

- GATE 0: owner approval of this feature list, the fleet inventory map from a fresh probe, the brain receipt (`verify-mission.sh`), and the four draft choices above (98% rule, `ty`, threshold 300, deferred proposal items). No dispatch before that.
- GATE 1: after F001 and F002 (quota meter and loop driver).
- GATE 2: after F003, F004, and F005 (structured progress, worker inner loop, task-size signal).
- GATE 3: after F006 (parallel lanes, minimum slice).
- GATE 4: after F007, F008, F009, and F010 (board, benchmark, Front Desk skills, prediction).

When a human gate is reached: run `bash scripts/verify-mission.sh` (must exit 0), set `status: awaiting-gate`, get the human verdict, append a **Human — GATE n** entry to PROGRESS.md, then set `status: done` or `in-progress`. Chat approval alone is not the record — receipts are.

## Source of truth

The binary checklist lives in `features.json` in this mission folder. This file is narrative only — if they disagree, features.json wins.

## Status lifecycle

`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` (optional) → `done`
