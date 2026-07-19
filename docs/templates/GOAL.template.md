---
status: draft | approved | in-progress | done
owner: {{HUMAN}}
orchestrator: Claude Fable
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

| Worker | Invocation |
|---|---|
| codex | {{`codex exec --profile worker` (economy) or `codex exec -m <flagship> -c model_reasoning_effort="high"` (premium)}} |
| cursor | {{`agent -p ... --model composer` or premium model flag}} |
| agy | {{`agy -p ... -m <flash-tier>` or premium tier}} |
| claude | {{`claude -p ... --model haiku` (economy) or `--model sonnet` (premium) — aliases track latest; resolved model logged at GATE 0}} |

## Human gates
- GATE 0: feature list approved before any dispatch
- GATE {{n}}: {{e.g. staging review before merging to main}}

## Source of truth
The binary checklist lives in `features.json`. This file is narrative only —
if they disagree, features.json wins.
