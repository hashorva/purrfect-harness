---
status: done
owner: Zamir
orchestrator: opus
created: 2026-10-14
intake: docs/proposals/20261014-phase-2.md (sections 13 and 14)
---

# Goal

## Mission (2–4 sentences, outcome not tasks)

Mission 2A "Foundation" builds the data layer for Phase 2 ("yield per token").
It moves provider, door and pool facts into one registry, records the observed model and usage in every receipt, adds fleet v2
(policy seats and visible drift), adds the ledger and structured verdicts, and
proves it with a real smoke run through three doors (claude, codex, cursor) on the owner's Mac. (Amended 2026-10-16 by the owner: agy is dropped from this mission; its hang evidence is in progress-archive/.)

## Why now / forcing function

Phase 1 (v3.0.0) made every run provable. Mission 2B (loop, board, benchmark)
needs this data layer first. Harness version stays 3.0.0 until a release task.

## In scope

- Features F001, F003–F007 as listed in `features.json`.
- **F002 is removed** (owner Gate 0 verdict, 2026-10-14): Grok Build is not a provider
  in 2A. Grok runs through `cursor-agent`. Ids are not renumbered.
- Proposal sections 4–8 and 13 are the design input.

## Explicitly OUT of scope (workers: do not touch)

- Everything in mission 2B: Front Desk and Architect skills, `mission-run.sh`,
  repair rounds, anti-gaming checks, worktree lanes, board, benchmark, lessons,
  STE rewrite (X-003).
- Fast modes, usage credits and API billing (never in 2A).
- A `grok` provider (removed F002). Deferred experiment X-GROK: Grok via `grok` against
  Grok via `cursor-agent`, measured in the ledger on spare quota.
- Git tags, remotes and releases.

## Constraints

- Hard rules: see AGENTS.md — all apply.
- Provider naming: the provider name is `cursor` (binary `cursor-agent`). `agent`
  stays only as a legacy name for v3 evidence. Never call a bare `agent` binary.
- Every observed number carries a source flag: `observed`, `estimated` or `unknown`.
- Features F004 (fleet v2) depends on Gate 0 decision 2 below.

## Architect instructions (read before you change features.json)

- Keep ids F001, F003–F007 (F002 is removed; do not renumber). You may tighten steps and cut work for economy workers.
  Do not drop the fleet-doctor requirement in F001 or the naming rule.
- F001 is the largest feature. Plan it as several small tasks, each with its own
  allow-list and verification commands. T-001 is a first slice, not the whole feature.
- Why the steps are binary: the verifier reads exit codes only. A step a script
  cannot decide is a defect, so rewrite it until a command can decide it.
- Every feature stays `passes: false` and `bootstrap: false`.

## Fleet (proposal and narrative copy of this mission's frozen fleet.json)

Proposal only. Gate 0 decides. Source: `bash scripts/fleet-inventory.sh` at
2026-10-14T15:00:44Z.

Tier chosen at GATE 0: mixed (economy first)
Orchestrator (brain): Opus 5.5, effort high. Owner chose it via Antigravity (`agy`,
`claude-opus-5-5-high`) to keep the Claude Pro pool for the Front Desk, with fallback
`claude` / `opus` if the first agy run fails to launch. **Frozen interim: `claude` / `opus`, effort high** (chair intent and switch rule in PROGRESS.md).

Verified local CLIs: claude, codex, cursor-agent, agy, grok. `which -a` shows
duplicate PATH entries only; all hits resolve to one binary per CLI (owner
accepted). `grok` is installed but is not a 2A provider; Grok runs through `cursor-agent`.

### Proposed seat binds (from inventory — edit only with human GATE 0 approval)

| Seat           | CLI          | Model                 | Family   | Health  | Source                                                                   |
| -------------- | ------------ | --------------------- | -------- | ------- | ------------------------------------------------------------------------ |
| brain          | claude       | opus                  | opus     | healthy | alias (owner wants agy/claude-opus-5-5-high; no such inventory seat yet) |
| brain_codex    | codex        | gpt-6.1-sol           | sol      | healthy | observed                                                                 |
| brain_fable    | claude       | fable                 | fable    | healthy | alias (named only)                                                       |
| cursor.premium | cursor-agent | grok-4.7-xhigh        | grok     | healthy | observed                                                                 |
| cursor.economy | cursor-agent | composer-2.5          | composer | healthy | observed                                                                 |
| codex.premium  | codex        | gpt-5.6-terra         | terra    | healthy | observed                                                                 |
| codex.economy  | codex        | gpt-6-luna            | luna     | healthy | observed                                                                 |
| agy.premium    | agy          | unavailable           | pro      | unknown | unavailable                                                              |
| agy.economy    | agy          | gemini-3.8-flash-high | flash    | healthy | observed                                                                 |
| claude.premium | claude       | sonnet                | sonnet   | healthy | alias                                                                    |
| claude.economy | claude       | haiku                 | haiku    | healthy | alias                                                                    |

Degraded or unavailable: `agy.premium` is unavailable (no Pro model on this plan).
The three `claude` seats and `brain_fable` are alias-sourced: the Claude probe
listed 0 models, so the exact model is not observed until a receipt records it.

Ledger rule (owner answer): each run writes `.tasks/ledger/<run_id>.json`
(gitignored). The orchestrator folds rows into `docs/missions/ledger.jsonl` in each
acceptance commit and at gates.

Spawn helpers (prefer these so logs land in `.tasks/logs/`):

| Worker                      | Economy                                                                                                           | Premium                          |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| cursor (`agent` legacy key) | `bash scripts/spawn-worker.sh agent <task> --tier economy --feature F00X --effort <approved> --speed <approved>`  | same flags with `--tier premium` |
| codex                       | `bash scripts/spawn-worker.sh codex <task> --tier economy --feature F00X --effort <approved> --speed <approved>`  | same flags with `--tier premium` |
| agy                         | `bash scripts/spawn-worker.sh agy <task> --tier economy --feature F00X --effort <approved> --speed <approved>`    | unavailable                      |
| claude                      | `bash scripts/spawn-worker.sh claude <task> --tier economy --feature F00X --effort <approved> --speed <approved>` | same flags with `--tier premium` |

In v3.0.0 the spawn scripts still use the key `agent`. F001 renames it to `cursor`
and keeps `agent` as a legacy name.

Freeze the human-approved bindings with `scripts/fleet_state.py freeze` as
described in the mission-init skill. Dispatch reads only `fleet.json`.
Worker dispatch requires `status: in-progress` and a committed task; transition
and commit before the first launch. Cross-repository execution is disabled.

## Human gates

- GATE 0: feature list + **fleet inventory map** + **brain receipt** approved
  before any dispatch. Four owner decisions (proposal section 14):
  1. chair for 2A: Opus 5.5, effort high, via `agy` (fallback `claude` / `opus`) — approved;
  2. amend the Phase 1 rule "a live probe cannot change an active mission" to
     "it can change it, but never silently" — approved;
  3. lift the Phase 1 non-goals for Phase 2: worktrees, parallel scheduling,
     adaptive routing, analytics, dashboard — approved, and 2A uses none of them;
  4. budgets (approved): per spawn 40 min; per night max 12 worker + 4 Architect runs;
     per pool stop at an estimated 80% of a 5-hour window or 70% of the weekly cap;
     never credits, never fast modes.
- GATE 1: after F001–F006, deterministic suite green.
- GATE 2: after F007, real smoke on the Mac.

When a human gate is reached: run `bash scripts/verify-mission.sh` (must exit 0),
set `status: awaiting-gate`, get the human verdict, append a **Human — GATE n**
entry to PROGRESS.md, then set `status: done` or `in-progress`. Chat approval
alone is not the record — receipts are.

## Source of truth

The binary checklist lives in `features.json` in this mission folder. This file
is narrative only — if they disagree, features.json wins.

## Status lifecycle

`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` (optional) → `done`
