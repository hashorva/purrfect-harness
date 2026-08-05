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
| `agy` | Gemini Flash-class (`agy.economy`) | Gemini Pro-class (`agy.premium`) — **prefer for UI / shadcn / Luma** |
| `claude` | haiku | sonnet |

```bash
bash scripts/spawn-worker.sh agent "$MISSION/tasks/T-XXX.md" --tier premium --feature F00X
bash scripts/spawn-worker.sh agent "$MISSION/tasks/T-XXX.md" --tier economy --feature F00X
bash scripts/spawn-worker.sh codex "$MISSION/tasks/T-XXX.md" --tier economy --feature F00X
# Worker repo lives elsewhere (e.g. purrfect-worker): workspace only; logs/receipts stay here
bash scripts/spawn-worker.sh agent "$MISSION/tasks/T-XXX.md" --tier premium --feature F00X \
  --repo ~/Projects/purrfect-worker
```

**Never dispatch a worker to edit `scripts/spawn-worker.sh` through `spawn-worker.sh`.**
The wrapper re-execs from a snapshot (2.2.2+) so self-edits are safe, but prefer
orchestrator-owned harness changes when possible.

Each spawn writes `.tasks/logs/…` **and** `.tasks/receipts/worker-*.json`.
Before flipping `passes: true` or asking for a human GATE:

```bash
bash scripts/verify-mission.sh "$MISSION"
```

No receipt → not greenlit. PROGRESS claims without receipts are a protocol failure.

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
2. **UI / shadcn / Luma / appearance / chatbuilding** and agy healthy? → `agy`
   (premium for multi-file layout; economy for polish) — spend Antigravity credits
   on purpose unless the human pinned Cursor/Codex for that feature.
3. Many files / repo context (non-UI)? → `agent` **premium** (Grok).
4. Small safe / boilerplate (non-UI)? → `agent` **economy** (Composer) or economy seats.
5. Tight verifiable scope? → `codex` with inventory tier.
6. Human said “use agy” / GATE 0 UI lane → `agy` even for non-UI if they want.
7. High-volume low-judgment? → economy seats (`agy` flash, Composer, Luna, Haiku).

Home-fleet reminder: Cursor intake → default Grok/Composer; Codex chair → default
Terra/Luna; neither excludes agy when UI (or explicit) says so.

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

### False-green checklist — `exit=0` is not proof of work

Two silent false-greens have already reached this point undetected: agy's
Go-style flag parser once swallowed the prompt into `-p`'s value and exited 0
having only answered a question about the flag (`catalog-truth` F004); a
mocked test suite reported green twice without touching the target file
(`catalog-truth` F009).

`scripts/spawn-worker.sh` now captures git state around every CLI invocation
and `scripts/write-receipt.sh` records it on the receipt as `commits_made` /
`dirty_after` / `workspace_changed`. `scripts/verify-mission.sh` hard-fails any
`passes: true` feature whose matched receipt has `exit=0` but
`workspace_changed: false` — that mechanical check is not optional and you
cannot bypass it by re-running `verify-mission.sh`. Receipts written before
this existed have `workspace_changed: null` and only WARN; treat a WARN as "go
verify the diff by hand," not as a pass.

Before trusting ANY receipt as a PASS, in addition to `verify-mission.sh` green:

- [ ] `git diff --stat` (worker's workspace) shows changes in the task's
      allow-listed files, not just wherever `workspace_changed` says nonzero
- [ ] `tail -40` of `.tasks/logs/…` shows the CLI actually reading the task and
      producing tool calls/edits — not prose *about* a flag, a refusal, or a
      question back to the user
- [ ] The receipt's `feature` field matches the feature being flipped (see
      "Never" below — a missing tag is not silently acceptable)
- [ ] If `workspace_changed` is `false` and the task expected code changes,
      that is an INFRASTRUCTURE or CAPABILITY fail per Step 3 above — rewrite
      or reassign, never re-flip `passes: true` on the same receipt

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
- Never flip `passes: true` without `verify-mission.sh` green and a worker receipt
  tagged `--feature F00X` for that feature (orchestrator-only features need
  `"bootstrap": true` in features.json — never inferred from description text).
- Never implement the worker allow-list inside the orchestrator chat when the
  Fleet CLI is installed — that produces no receipt and fails verify.
