---
name: dispatch-worker
description: >
  How the orchestrator dispatches a WORKER_TASK to a local worker CLI
  (codex, agent/Cursor, agy/Antigravity, claude -p) via scripts/spawn-worker.sh
  and processes the result. MUST be used in the DISPATCH and REVIEW steps of the
  orchestration loop, whenever spawning a worker, choosing which worker gets a
  task, or handling a worker failure, quota exhaustion, or stall.
  Orchestrator-only; workers never dispatch other workers.
---

# Dispatch a worker (orchestrator only)

## Worker fleet — cost pinning is MANDATORY

Workers are cheap BY CONSTRUCTION: every dispatch must pin model + effort
explicitly. Dispatching on account defaults (flagship model, high effort) is a
failed dispatch — the harness removes ambiguity from tasks precisely so cheap
tiers succeed.

| CLI | Agent | Economy spawn | Best at |
|---|---|---|---|
| `codex` | Codex | `bash scripts/spawn-worker.sh codex <mission>/tasks/T-XXX.md` | tight, verifiable tasks |
| `agent` | Cursor Agent | `bash scripts/spawn-worker.sh agent <mission>/tasks/T-XXX.md` | multi-file work, repo-wide context |
| `agy` | Antigravity | `bash scripts/spawn-worker.sh agy <mission>/tasks/T-XXX.md` | cheap bulk: boilerplate, translations |
| `claude` | Claude Haiku | `bash scripts/spawn-worker.sh claude <mission>/tasks/T-XXX.md` | small tasks, strong instruction-following |

`scripts/spawn-worker.sh` pins economy defaults (composer / medium effort /
haiku), writes `.tasks/logs/T-XXX.log`, and prints only `exit=` + tail. Prefer
it over hand-rolled CLI lines so Mac Mini PATH + flags stay consistent.

**Invocation precedence (most specific wins):**
1. `invocation:` in the WORKER_TASK frontmatter (per-task override / escalation)
2. the `## Fleet` table in the mission's GOAL.md (chosen at GATE 0)
3. `scripts/spawn-worker.sh` economy defaults

Before every spawn: resolve the active mission (`bash scripts/active-mission.sh`),
read its Fleet table, and use that row unless the task frontmatter overrides.
First use of ANY worker CLI in an environment: run `<cli> --help` and verify
flags still exist — these CLIs change fast. Never assume.

**Escalation rule:** raising model tier or effort is allowed ONLY as part of a
task rewrite after a CAPABILITY failure, one tier at a time, noted in the task
frontmatter (`escalated: true`) and in PROGRESS.md. Frequent escalation =
under-specified task files (flywheel signal), not a fleet problem. The
orchestrator itself is the only always-premium brain in the loop (Opus or Sol
per docs/missions/MODEL_ROUTING.md; Fable only via its escalation triggers there).

## Step 0 — Preconditions

- Active mission: `MISSION=$(bash scripts/active-mission.sh)` with
  `status: in-progress` (or set `approved` → `in-progress` on first dispatch).
- Working tree CLEAN (`git status`). Dirty → commit or stash first; never
  dispatch on top of uncommitted changes (diffs must be attributable).
- WORKER_TASK file exists under `$MISSION/tasks/` and names exactly one feature.
- Target CLI is on PATH (`command -v`); if not, reassign or stop — do not
  silently implement the task inside the orchestrator session as a substitute
  unless the human explicitly waives fleet dispatch for that task.

## Step 1 — Choose the worker (three-question routing)

1. Needs judgment beyond what's written in task/skills? → don't dispatch; the
   orchestrator handles it or splits further.
2. Many files / repo-wide context? → `agent` (Cursor Agent CLI).
3. Tight scope, mechanically verifiable? → `codex`.
4. High-volume, low-judgment? → `agy` or `claude` (haiku).

## Step 2 — Spawn (blocking call, output to log — never to context)

```bash
MISSION=$(bash scripts/active-mission.sh)
# ensure status is in-progress before first spawn
bash scripts/spawn-worker.sh codex "$MISSION/tasks/T-XXX.md"
echo "exit=$?"
```

Variants: replace `codex` with `agent` | `agy` | `claude`. If the task
frontmatter has `invocation:`, run that exact command instead (still redirect
to `.tasks/logs/` yourself if it bypasses spawn-worker.sh).

The Bash call BLOCKS until the worker process exits — completion detection is
the exit itself; no polling. Sandbox notes: codex uses `workspace-write` via
spawn-worker; NEVER `danger-full-access` outside a container. NEVER pass secrets
in prompts (prompts end up in transcripts).

## Step 3 — Judge by effects, not transcript

Read ONLY: exit code, `tail -20` of `.tasks/logs/T-XXX.log`, `git status`,
`git diff --stat`. Never load the full worker transcript into orchestrator
context. Then run REVIEW: delegate `git diff` to the code-reviewer subagent
(.claude/agents/code-reviewer.md) against AGENTS.md hard rules + task deny-list.

## Step 4 — Outcome (two failure classes — treat them differently)

- **PASS** → verify the feature's steps, flip `passes: true`, ensure PROGRESS.md
  entry exists (write it if the worker skipped it), next cycle.
- **CAPABILITY FAIL** (worker produced wrong/incomplete work) → consumes an
  attempt. Rewrite the task with the findings baked in (max 2 attempts total),
  or reassign, or escalate to human. Recurring failure class → one line into
  AGENTS.md or a skill (flywheel).
- **INFRASTRUCTURE FAIL** (log tail shows 429 / rate limit / quota / usage
  limit / auth error, or non-zero exit with no edits, or stall past timeout) →
  does NOT consume an attempt. Recover: `git checkout .` if the tree is dirty,
  log the event in PROGRESS.md, reassign the SAME task file to the next worker
  in routing order. If all workers are exhausted → stop and report to human.

## Human gates mid-mission

When GOAL.md says the next milestone is a human gate (or all features pass and
a merge/deploy gate remains):

1. Set GOAL `status: awaiting-gate`.
2. **Ask the human** for an explicit GATE n verdict before ending the session.
3. Append `## {{DATE}} — Human — GATE n` to PROGRESS.md.
4. Set `status: done` or resume `in-progress`.

## Parallelism rules

- **Never two workers in the same working tree simultaneously** — they corrupt
  each other's files and git index, and diffs become unattributable.
- **Pipelining is encouraged**: while a worker runs, the orchestrator writes the
  next task file and reviews the previous diff.
- **Cross-repo parallel is allowed** (different working trees).
- Same-repo true parallelism requires git worktrees (one branch + checkout per
  worker) — adopt only after the serial loop is proven; then revisit
  `.worktreeinclude`.

## Never

- Never stream a worker's stdout into the orchestrator context.
- Never let a worker edit features.json descriptions, AGENTS.md, docs/, or
  .agents/skills/ — orchestrator/human territory.
- Never re-run an identical failed command hoping for a different result.
- Never "dispatch" by doing the worker's job inside the orchestrator chat when
  the Fleet CLI for that task is installed and healthy — that breaks the cost
  model and the audit trail (`.tasks/logs/`).
