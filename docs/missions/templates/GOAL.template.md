---
status: draft
owner: {{HUMAN}}
orchestrator: {{opus (default) | current-chat | fable (named) | sol (named)}}
created: {{DATE}}
intake: {{optional — Cursor/Grok brief that Opus weighed}}
---

# Goal

## Mission (2–4 sentences, outcome not tasks)
{{e.g. Ship the Fund Detail page: tabs Overview/Performance/Fees/Rules, data from the
Worker only, Luma-styled, live on staging behind auth.}}

## Why now / forcing function
{{deadline, dependency, campaign date}}

## In scope
- {{...}}

## Explicitly OUT of scope (workers: do not touch)
- {{...}}

## Constraints
- Hard rules: see AGENTS.md PROJECT block — all apply.
- {{mission-specific: e.g. no new dependencies without orchestrator approval}}

## Fleet (proposal and narrative copy of this mission's frozen fleet.json)

Filled at GATE 0 from `bash scripts/fleet-inventory.sh` (human confirms or remaps).

Tier chosen at GATE 0: {{economy | premium | mixed}}
Orchestrator (brain): {{opus default | fable named | sol named | current-chat}} — concrete bind logged in PROGRESS.md

Verified local CLIs:
{{paste: which claude / codex / agent / agy}}

### Approved seat binds (from inventory — edit only with human GATE 0 approval)

| Seat | CLI | Model | Family |
|---|---|---|---|
| brain | {{claude}} | {{opus}} | {{opus}} |
| cursor.premium | agent | {{cursor-grok-…}} | grok |
| cursor.economy | agent | {{composer-…}} | composer |
| codex.premium | codex | {{gpt-…-terra}} | terra |
| codex.economy | codex | {{gpt-…-luna}} | luna |
| agy.premium | agy | {{gemini-…-pro-…}} | gemini-pro (UI lane) |
| agy.economy | agy | {{gemini-…-flash-…}} | gemini-flash (UI polish) |
| claude.premium | claude | sonnet | sonnet |
| claude.economy | claude | haiku | haiku |

Spawn helpers (prefer these so logs land in `.tasks/logs/`):

| Worker | Economy | Premium |
|---|---|---|
| agent | `bash scripts/spawn-worker.sh agent <task> --tier economy --feature F00X --effort <approved> --speed <approved>` | same flags with `--tier premium` (Grok; Composer fallback) |
| codex | `bash scripts/spawn-worker.sh codex <task> --tier economy --feature F00X --effort <approved> --speed <approved>` | same flags with `--tier premium` |
| agy | `bash scripts/spawn-worker.sh agy <task> --tier economy --feature F00X --effort <approved> --speed <approved>` (Flash) | same flags with `--tier premium` (Pro) — prefer for UI |
| claude | `bash scripts/spawn-worker.sh claude <task> --tier economy --feature F00X --effort <approved> --speed <approved>` | same flags with `--tier premium` |

Freeze the human-approved bindings with `scripts/fleet_state.py freeze` as
described in the mission-init skill. Dispatch reads only `fleet.json`.
Per-task `invocation:` documents the approved bind; `--model`, `--effort`, and
`--speed` are equality assertions and cannot override the frozen seat.
Worker dispatch requires `status: in-progress` and a committed task; transition
and commit before the first launch. Cross-repository execution is disabled.

## Human gates
- GATE 0: feature list + **fleet inventory map** + **brain receipt** (`verify-mission.sh`) approved before any dispatch
- GATE {{n}}: {{e.g. staging review before merging to main}}

When a human gate is reached: run `bash scripts/verify-mission.sh` (must exit 0),
set `status: awaiting-gate`, get the human verdict, append a **Human — GATE n**
entry to PROGRESS.md, then set `status: done` or `in-progress`. Chat approval
alone is not the record — receipts are.

## Source of truth
The binary checklist lives in `features.json` in this mission folder. This file
is narrative only — if they disagree, features.json wins.

## Status lifecycle
`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` (optional) → `done`
