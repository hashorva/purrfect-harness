---
name: dispatch-worker
description: >
  How the orchestrator (Claude Code) dispatches a WORKER_TASK to a worker CLI
  (codex, agent/Cursor, agy/Antigravity, claude -p) and processes the result.
  MUST be used in the DISPATCH and REVIEW steps of the orchestration loop,
  whenever spawning a worker, choosing which worker gets a task, or handling a
  worker failure, quota exhaustion, or stall. Orchestrator-only; workers never
  dispatch other workers.
---

# Dispatch a worker (orchestrator only)

## Worker fleet — cost pinning is MANDATORY

Workers are cheap BY CONSTRUCTION: every dispatch must pin model + effort
explicitly. Dispatching on account defaults (flagship model, high effort) is a
failed dispatch — the harness removes ambiguity from tasks precisely so cheap
tiers succeed.

| CLI | Agent | Pinned invocation | Best at |
|---|---|---|---|
| `codex exec --profile worker` | Codex | profile pins cheap model + `model_reasoning_effort="medium"` (see setup below); inline alternative: `codex exec -m <mini-model> -c model_reasoning_effort="medium"` | tight, verifiable tasks |
| `agent -p ... --model composer` | Cursor Composer | Composer IS the fast/cheap model — pin it explicitly | multi-file work, repo-wide context |
| `agy -p ... -m <flash-tier>` | Antigravity | pin the Flash-class model; verify flag via `agy --help` (CLI is new) | cheap bulk: boilerplate, translations |
| `claude -p ... --model claude-haiku-4-5` | Claude Haiku | already pinned | small tasks, strong instruction-following |

**Invocation precedence (most specific wins):**
1. `invocation:` in the WORKER_TASK frontmatter (per-task override / escalation)
2. the `## Fleet` table in GOAL.md (mission tier, chosen by the human at GATE 0)
3. machine economy defaults (`~/.codex/worker.config.toml` profile, composer, flash, haiku)

Before every spawn: read the Fleet table in GOAL.md and use its row for the
chosen worker unless the task frontmatter overrides it. The table above shows
the ECONOMY defaults. One-time machine setup: create `~/.codex/worker.config.toml`
with the cheap model + `model_reasoning_effort = "medium"` + `sandbox_mode =
"workspace-write"` so `--profile worker` carries everything.

First use of ANY worker CLI in an environment: run `<cli> --help` and verify
flags still exist — these CLIs change fast. Never assume.

**Escalation rule:** raising model tier or effort is allowed ONLY as part of a
task rewrite after a CAPABILITY failure, one tier at a time, noted in the task
frontmatter (`escalated: true`) and in PROGRESS.md. Frequent escalation =
under-specified task files (flywheel signal), not a fleet problem. The
orchestrator itself is the only always-premium brain in the loop (Opus or Sol
per docs/MODEL_ROUTING.md; Fable only via its escalation triggers there).

## Step 0 — Preconditions

- Mission active (GOAL.md + features.json at repo root).
- Working tree CLEAN (`git status`). Dirty → commit or stash first; never
  dispatch on top of uncommitted changes (diffs must be attributable).
- WORKER_TASK file exists and names exactly one feature.

## Step 1 — Choose the worker (three-question routing)

1. Needs judgment beyond what's written in task/skills? → don't dispatch; the
   orchestrator handles it or splits further.
2. Many files / repo-wide context? → `agent` (Cursor).
3. Tight scope, mechanically verifiable? → `codex`.
4. High-volume, low-judgment? → `agy` or `claude -p` (haiku).

## Step 2 — Spawn (blocking call, output to log — never to context)

```bash
mkdir -p .tasks/logs
codex exec --profile worker "Read docs/tasks/T-XXX.md and complete it exactly. Follow AGENTS.md \
and the skills the task names. Do not touch files outside the allow-list." \
  > .tasks/logs/T-XXX.log 2>&1
echo "exit=$?"
```

Variants: `agent -p "<same prompt>"` (+ documented write-enable flag) ·
`agy -p "<same prompt>"` (+ its auto-approve flag) ·
`claude -p "<same prompt>" --model claude-haiku-4-5 --allowedTools "Read,Write,Edit,Bash(npm*)"`.
The Bash call BLOCKS until the worker process exits — completion detection is
the exit itself; no polling. Sandbox notes: codex defaults read-only, escalate
to workspace-write deliberately, NEVER danger-full-access outside a container.
NEVER pass secrets in prompts (prompts end up in transcripts).

## Step 3 — Judge by effects, not transcript

Read ONLY: exit code, `tail -20` of the log, `git status`, `git diff --stat`.
Never load the full worker transcript into orchestrator context.
Then run REVIEW: delegate `git diff` to the code-reviewer subagent
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
