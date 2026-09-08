---
status: done
owner: Zamir
orchestrator: gpt-5.6-sol-high
created: 2026-08-21
intake: Sol architectural response v3, reconciled with the repository audit and approved by the human
---

# Goal

## Mission (2–4 sentences, outcome not tasks)

Harden Purrfect Harness so every execution is attributable through four distinct
truths: immutable authorization, observed execution, deterministic verification,
and orchestrator acceptance. Finish with a real economy-provider smoke mission whose
archived repository evidence can be reconstructed by a fresh process without chat history.

## Why now / forcing function

The audit reproduced false-green dispatch, receipt, inventory, and distribution paths.
Phase 2 mission memory and later evidence work cannot safely build on those paths.

## In scope

- Immutable, atomically persisted ExecutionSpec and UUID run identity
- One shared provider execution path for brain and workers
- Role-aware fail-closed dispatch, frozen Gate 0 fleet, and exclusive workspace lock
- Exact Git delta, write-scope verification, terminal receipts, and run-specific verification
- Orchestrator-only feature acceptance linked to a verified run
- Release/manifest/install/update/sync truth and a real harness-specific AGENTS.md
- One real end-to-end economy-provider smoke mission with durable archived evidence

## Explicitly OUT of scope (workers: do not touch)

- Full AWU, Decision Log, MissionException, or structured failure-taxonomy models
- JSONL analytics, dashboard, cost optimization, adaptive routing, or learning
- LangGraph, ACP, OpenHands, worktrees, remote execution, or parallel scheduling
- Cross-repository execution: Phase 1 must reject it before provider launch
- General filesystem-containment claims beyond Git-visible changes in the declared workspace

## Constraints

- Hard rules: see AGENTS.md — all apply.
- Every reproduced failure gains a negative regression at its real entry point.
- ExecutionSpec bytes are immutable after validated atomic persistence; amendments create a new run.
- Verification and acceptance remain separate truths; no acceptance fields in verification records.
- No new production dependency. Prefer Bash arrays and existing Python 3 tooling; never `eval`.
- Tests are added with each fix, not deferred to a final test-only feature.
- Current baseline is red only because README says 2.3.0 while CHANGELOG says 2.3.1;
  release/distribution truth (F006) runs first to restore a green baseline.

## Fleet (worker invocations for THIS mission — dispatch-worker reads this table)

Filled at GATE 0 from `bash scripts/fleet-inventory.sh` (human confirms or remaps).

Tier chosen at GATE 0: mixed
Orchestrator (brain): GPT-5.6 Sol / high — human-approved bind logged in PROGRESS.md

Verified local CLIs:

- claude: `/opt/homebrew/bin/claude`
- codex: `/opt/homebrew/bin/codex`
- agent: `/Users/zamirhashorva/.local/bin/agent`
- agy: `/Users/zamirhashorva/.local/bin/agy`

### Approved seat binds (frozen at Human GATE 0)

| Seat | CLI | Model | Family | Probe status |
|---|---|---|---|---|
| brain | codex | gpt-5.6-sol | sol | local model cache; reasoning effort high |
| cursor.premium | agent | cursor-grok-4.5-high | grok | degraded: live model list empty; policy fallback |
| cursor.economy | agent | composer-2.5 | composer | degraded: live model list empty; policy fallback |
| codex.premium | codex | gpt-5.6-terra | terra | local model cache |
| codex.economy | codex | gpt-5.6-luna | luna | local model cache |
| agy.premium | agy | gemini-3.1-pro-high | gemini-pro | degraded: live model list empty; policy fallback |
| agy.economy | agy | gemini-3.6-flash-high | gemini-flash | degraded: live model list empty; policy fallback |
| claude.premium | claude | sonnet | sonnet | alias available |
| claude.economy | claude | haiku | haiku | alias available |

Initial worker proposal: T-001 / F006 → Codex premium (`gpt-5.6-terra`), because
the repository test baseline must be restored before execution-core changes begin.

Human-approved F006 recovery sequence after T-001 exhausted its review attempts:

1. T-002 / F006 → Codex premium (`gpt-5.6-terra`): executable manifest, release,
   install, update, sync, and lifecycle-independent negative-test truth.
2. T-003 / F006 → Codex premium (`gpt-5.6-terra`): repository instructions,
   consumer template, and documentation truth. T-003 dispatches only after T-002
   is reviewed and committed; F006 is accepted only after both tasks verify.

F001 has the explicit Human Gate 0 exception to the current dispatch-worker skill's
"never self-edit spawn-worker.sh through spawn-worker.sh" rule. The exception is narrow:
the existing wrapper must re-exec from a validated snapshot, and the F001 review must
prove that behavior before acceptance.

## Human gates

- GATE 0: feature list, degraded fleet facts, initial F006 routing, and F001 self-edit exception
- GATE 1: deterministic suite green after F001–F006; review exact negative-test evidence
- GATE 2: authenticated real-provider smoke evidence reconstructed from a fresh process

When a human gate is reached: run `bash scripts/verify-mission.sh` (must exit 0),
set `status: awaiting-gate`, register the Human GATE verdict in PROGRESS.md, then
set `status: done` or `in-progress`. Chat approval alone is not the record.

## Source of truth

The binary checklist lives in `features.json` in this mission folder. This file
is narrative only — if they disagree, features.json wins.

## Status lifecycle

`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` → `done`
