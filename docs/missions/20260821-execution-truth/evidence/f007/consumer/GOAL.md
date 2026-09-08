---
status: in-progress
owner: Zamir
orchestrator: current-chat (GPT-5.6 Sol/high named by parent mission)
created: 2026-09-07
intake: Parent mission 20260821-execution-truth F007 and Human Gate 1 approval
---

# Goal

## Mission (2–4 sentences, outcome not tasks)
Prove the installed Purrfect Harness control path in a disposable consumer repository.
One real authenticated Codex/Luna worker must create and commit exactly one authorized
nonce file; verification and orchestrator acceptance must bind to that same run.

## Why now / forcing function
The parent Phase 1 mission cannot close on deterministic stubs alone.

## In scope
- Fresh local fleet inventory and immutable approved fleet snapshot
- One real economy-provider worker invocation through the installed wrapper
- One Git-visible nonce file, one commit, strict receipt, VerificationRecord, and acceptance

## Explicitly OUT of scope (workers: do not touch)
- Harness implementation changes, dependencies, network services, tags, and remotes
- Cross-repository execution, provider waivers, analytics, or Phase 2+ concepts

## Constraints
- Hard rules: see AGENTS.md PROJECT block — all apply.
- Exact nonce: `5818a92a-4798-4c29-832f-81e71012bece`
- Worker write scope is exactly `smoke/nonce.txt`; mission progress is orchestrator-owned

## Fleet (worker invocations for THIS mission — dispatch-worker reads this table)

Filled at GATE 0 from `bash scripts/fleet-inventory.sh` (human confirms or remaps).

Tier chosen at GATE 0: economy
Orchestrator (brain): current-chat GPT-5.6 Sol/high — concrete bind logged in PROGRESS.md

Verified local CLIs:
- claude: `/opt/homebrew/bin/claude`
- codex: `/opt/homebrew/bin/codex`
- agent: `/Users/zamirhashorva/.local/bin/agent`
- agy: `/Users/zamirhashorva/.local/bin/agy`

### Approved seat binds (from inventory — edit only with human GATE 0 approval)

| Seat | CLI | Model | Family |
|---|---|---|---|
| brain | codex | gpt-5.6-sol | sol |
| cursor.premium | agent | cursor-grok-4.6-xhigh | grok |
| cursor.economy | agent | composer-2.5 | composer |
| codex.premium | codex | gpt-5.6-terra | terra |
| codex.economy | codex | gpt-5.6-luna | luna |
| agy.premium | agy | gemini-3.1-pro-high | gemini-pro (degraded fallback; not approved for dispatch) |
| agy.economy | agy | gemini-3.6-flash-high | gemini-flash (degraded fallback; not approved for dispatch) |
| claude.premium | claude | sonnet | sonnet |
| claude.economy | claude | haiku | haiku |

Spawn helpers (prefer these so logs land in `.tasks/logs/`):

| Worker | Economy | Premium |
|---|---|---|
| agent | `bash scripts/spawn-worker.sh agent <task> --tier economy` | `... --tier premium` (Grok; Composer fallback) |
| codex | `bash scripts/spawn-worker.sh codex <task> --tier economy` | `... --tier premium` |
| agy | `bash scripts/spawn-worker.sh agy <task> --tier economy` (Flash) | `... --tier premium` (Pro) — prefer for UI |
| claude | `bash scripts/spawn-worker.sh claude <task> --tier economy` | `... --tier premium` |

Per-task `invocation:` / `--model` overrides this table for one spawn.

## Human gates
- GATE 0: feature list + **fleet inventory map** + **brain receipt** (`verify-mission.sh`) approved before any dispatch
- GATE 1: parent mission reconstructs and approves the archived smoke chain

When a human gate is reached: run `bash scripts/verify-mission.sh` (must exit 0),
set `status: awaiting-gate`, get the human verdict, append a **Human — GATE n**
entry to PROGRESS.md, then set `status: done` or `in-progress`. Chat approval
alone is not the record — receipts are.

## Source of truth
The binary checklist lives in `features.json` in this mission folder. This file
is narrative only — if they disagree, features.json wins.

## Status lifecycle
`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` (optional) → `done`
