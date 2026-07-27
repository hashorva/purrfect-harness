---
status: done
owner: Zamir
orchestrator: opus
created: 2026-07-27
intake: Cursor Grok plan — README badges + orchestration mermaid for newbies
---

# Goal

## Mission (2–4 sentences, outcome not tasks)

Make the purrfect-harness README first screen newbie-transparent: shields.io badges
directly under `# Agent Harness Kit`, a clear orchestration mermaid flowchart after
the intro, and an intro paragraph that matches current 2.1.x routing (Opus brain,
Grok/Composer workers). Do not remove existing mid-README diagrams.

## Why now / forcing function

Harness routing and mission layout shipped; the README opening still describes the
old Fable/Composer-only story. New adopters need a scannable “what is this?” above the fold.

## In scope

- Badges under H1 (version, license, loop, skills, CI)
- Newbie orchestration mermaid before “The four layers”
- Refresh stale intro one-liner
- Docs PATCH release `2.1.2` after human skim

## Explicitly OUT of scope (workers: do not touch)

- Deleting or rewriting install/update/anatomy/lifecycle mermaid blocks
- Changing LICENSE text (badge only)
- Editing skills, scripts, or product repos

## Constraints

- Hard rules: see AGENTS.md — all apply.
- Allow-list for workers: `README.md` only (+ mission `passes` / PROGRESS).
- Version badge must match README frontmatter / CHANGELOG.

## Fleet (worker invocations for THIS mission — dispatch-worker reads this table)

Tier chosen at GATE 0: mixed (Cursor only)
Orchestrator (brain): opus

Verified local CLIs: claude, codex, agent, agy on PATH

### Approved seat binds

| Seat | CLI | Model | Family |
|---|---|---|---|
| brain | claude | opus | opus |
| cursor.premium | agent | cursor-grok-4.5-high | grok |
| cursor.economy | agent | composer-2.5 | composer |

| Worker | Economy | Premium |
|---|---|---|
| agent | `bash scripts/spawn-worker.sh agent <task> --tier economy` | `... --tier premium` |

## Human gates

- GATE 0: feature list + fleet approved (plan implement = approve)
- GATE 1: human skim of badges + mermaid before/with 2.1.2 release

## Source of truth

`features.json` in this folder wins over this narrative.

## Status lifecycle

`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` → `done`
