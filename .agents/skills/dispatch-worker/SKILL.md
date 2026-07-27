---
name: dispatch-worker
description: >
  How the orchestrator dispatches a WORKER_TASK to a local worker CLI
  (codex, agent/Cursor, agy/Antigravity, claude -p) via scripts/spawn-worker.sh
  and processes the result. MUST be used in the DISPATCH and REVIEW steps.
  Cursor: Grok for premium, Composer for economy (Grok falls back to Composer).
  Always prefer spawn-worker + fleet from fleet-inventory over hand-rolled flags.
  Orchestrator-only; workers never dispatch other workers.
---

# Dispatch a worker (orchestrator only)

## Cost pinning is MANDATORY

Every dispatch pins model + tier. Account defaults (flagship, max effort) are a
failed dispatch.

| CLI | Economy | Premium |
|---|---|---|
| `agent` | Composer (`--tier economy`) | **Grok** (`--tier premium`; Composer if Grok unavailable) |
| `codex` | inventory `codex.economy` (Luna-class) | inventory `codex.premium` (Terra-class) |
| `claude` | haiku | sonnet |
| `agy` | flash-class when available | pro-class when available |

```bash
bash scripts/spawn-worker.sh agent "$MISSION/tasks/T-XXX.md" --tier premium
bash scripts/spawn-worker.sh agent "$MISSION/tasks/T-XXX.md" --tier economy
bash scripts/spawn-worker.sh codex "$MISSION/tasks/T-XXX.md" --tier economy
```

**Invocation precedence:** task `invocation:` > GOAL Fleet bind > inventory seat
> MODEL_ROUTING family fallback.

Before spawn: `MISSION=$(bash scripts/active-mission.sh)`; read Fleet; use
`--tier` unless frontmatter overrides. First use of a CLI: `<cli> --help`.

**Escalation:** raise tier only after a CAPABILITY failure, one step at a time,
`escalated: true` in frontmatter + PROGRESS. Never escalate brain to Fable
unless the human names Fable.

Delegate small safe work to Composer (economy) — do not burn Grok on boilerplate.

## Step 0 — Preconditions

- Active mission `in-progress` (or promote `approved` on first spawn).
- Working tree CLEAN.
- Task under `$MISSION/tasks/` names one feature.
- Target CLI on PATH; if not, reassign — do not silently absorb into orchestrator
  chat when the Fleet CLI is healthy.

## Step 1 — Choose worker + tier

1. Needs judgment beyond task/skills? → orchestrator handles or splits.
2. Many files / repo context? → `agent` **premium** (Grok).
3. Small safe / boilerplate? → `agent` **economy** (Composer) or `claude`/`codex` economy.
4. Tight verifiable scope? → `codex` with inventory tier.
5. High-volume low-judgment? → economy seats.

## Step 2 — Spawn (blocking; log never to context)

```bash
MISSION=$(bash scripts/active-mission.sh)
bash scripts/spawn-worker.sh agent "$MISSION/tasks/T-XXX.md" --tier premium
echo "exit=$?"
```

Judge by exit code, `tail -20` of `.tasks/logs/T-XXX.log`, `git status`,
`git diff --stat`. Then code-reviewer subagent against AGENTS.md + deny-list.

## Step 3 — Outcomes

- **PASS** → verify steps, flip `passes: true`, ensure PROGRESS entry.
- **CAPABILITY FAIL** → consumes attempt; rewrite task (max 2) or reassign.
- **INFRASTRUCTURE FAIL** (429 / auth / no edits) → does not consume attempt;
  reassign; if Grok infra-fails on agent premium, retry `--tier economy`
  (Composer) or next CLI.

## Human gates

Set `awaiting-gate` → ask for GATE n verdict → PROGRESS Human entry → `done` or
`in-progress`.

## Parallelism

Never two workers in the same working tree. Pipeline task-writing while one runs.
Cross-repo parallel OK.

## Never

- Never stream full worker transcripts into orchestrator context.
- Never let workers edit features.json descriptions, AGENTS.md, docs/, skills.
- Never skip inventory-approved binds without a task `invocation:` override.
- Never auto-escalate to Fable.
