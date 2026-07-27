---
status: draft
owner: {{HUMAN}}
orchestrator: {{opus | sol | fable (manual)}}
created: {{DATE}}
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

## Fleet (worker invocations for THIS mission — dispatch-worker reads this table)

Tier chosen at GATE 0: {{economy | premium | mixed}}
Orchestrator: {{opus (alias, effort high/extra) | gpt-5.6-sol (effort high) | fable (manual override)}} — resolved model logged in PROGRESS.md

Verified local CLIs (mission-init ran `command -v` on this machine):
{{paste: which claude / codex / agent / agy}}

| Worker | Invocation |
|---|---|
| codex | {{`bash scripts/spawn-worker.sh codex docs/missions/<slug>/tasks/T-XXX.md` or Fleet override}} |
| agent | {{`bash scripts/spawn-worker.sh agent ...` — Cursor Agent CLI (`agent`), model composer}} |
| agy | {{`bash scripts/spawn-worker.sh agy ...` — Antigravity}} |
| claude | {{`bash scripts/spawn-worker.sh claude ...` — haiku economy / sonnet premium}} |

Prefer `scripts/spawn-worker.sh` so logs land in `.tasks/logs/` and flags stay pinned.
Per-task `invocation:` frontmatter overrides this table.

## Human gates
- GATE 0: feature list approved before any dispatch
- GATE {{n}}: {{e.g. staging review before merging to main}}

When a human gate is reached: set `status: awaiting-gate`, get the human verdict,
append a **Human — GATE n** entry to PROGRESS.md, then set `status: done` or
`in-progress`. Chat approval alone is not the record.

## Source of truth
The binary checklist lives in `features.json` in this mission folder. This file
is narrative only — if they disagree, features.json wins.

## Status lifecycle
`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` (optional) → `done`
