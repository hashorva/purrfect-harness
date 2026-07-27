---
title: Orchestration Protocol
version: 2.2.0
---

# Orchestration Protocol — Orchestrator + Cheap Workers

One orchestrator plans, decomposes, dispatches, and reviews — **Opus by
default** per [`MODEL_ROUTING.md`](MODEL_ROUTING.md). Cursor (often Grok) may
intake a brief plan; Opus weighs it and runs the mission loop. Human may name
Fable or Codex/Sol as chair, or declare “no orchestration.” Cheap workers
(Cursor `agent`: Grok premium / Composer economy; Codex Terra/Luna-class;
`agy`; Claude Haiku/Sonnet) implement on **local machine CLIs**.

The loop runs on three files **inside the mission folder**: `features.json`
(what's true), `PROGRESS.md` (what happened), `GOAL.md` (narrative + fleet +
gates). Protocol index: [`README.md`](README.md).

## Orchestrator contract (the role is protocol-agnostic)

The orchestrator is a ROLE, not a specific product. Any agent CLI may take the
chair if it meets all five requirements:

1. Reads and follows `.agents/skills/` (mission-init, dispatch-worker, skillify)
2. Can run shell commands and BLOCK on child processes (worker spawns)
3. Respects GATE 0 — never dispatches before human approval of features.json
4. Never edits features.json descriptions/steps (flip `passes` only, on evidence)
5. Writes its actions to the shared artifacts (PROGRESS.md, git) — not private memory

The blessed implementation is Claude Code (it additionally carries the enforced
layer: .claude/settings.json permissions, path rules, the code-reviewer
subagent). Other CLIs meet the contract in guidance-only mode; port enforcement
configs per-tool only when there is a forcing event (quota lockout, model
superiority) — not speculatively.

**Local CLI rule:** when the loop runs on a Mac with studio CLIs installed, the
orchestrator MUST spawn the **brain** via `scripts/spawn-brain.sh` and workers via
`scripts/spawn-worker.sh` (or exact Fleet invocations). Each spawn writes a receipt
under `.tasks/receipts/`. Before flipping `passes` or registering a human GATE as
done, `bash scripts/verify-mission.sh` must exit 0. Doing all features inside one
Cursor chat without spawns is a failed dispatch — PROGRESS prose is not proof.

## Roles & dispatch table

| Agent | Role | Send it |
|---|---|---|
| **Orchestrator / brain** (Opus default; Fable or Sol only when human names them — see MODEL_ROUTING.md) | Weigh intake plan → features.json, WORKER_TASK files, review diffs, arbitrate, update AGENTS.md when decisions change | The GOAL, review requests, "what next" |
| **Cursor Agent** (`agent`) | Multi-file work: **Grok** = premium, **Composer** = economy (Grok falls back to Composer) | WORKER_TASK files; small safe tasks → Composer |
| **Codex** (`codex`) | Inventory seats: Sol = brain when named; Terra ≈ premium; Luna ≈ economy | Tight allow-lists / verifiable tasks |
| **Antigravity** (`agy`) | **UI lane** (shadcn/Luma/appearance) + opt-in workers; Flash economy / Pro premium | UI WORKER_TASKs; or when human says use agy |
| **Claude** (`claude -p`) | Haiku economy / Sonnet premium workers (not the default chair) | Tight allow-list tasks |

Rule of thumb: **judgment up, volume down.** Anything requiring a decision that isn't
already written in AGENTS.md / a skill / the task file goes UP to the orchestrator, never
improvised by a worker.

## Mission folder & GOAL status

Missions live under `docs/missions/<YYYYMMDD-slug>/`. Root `GOAL.md` /
`features.json` are not valid after harness 2.0.0.

`GOAL.md` frontmatter `status:`:

| Status | Meaning |
|---|---|
| `draft` | Files written; GATE 0 not approved |
| `approved` | Human approved feature list; no dispatch yet |
| `in-progress` | Workers may run; active mission |
| `awaiting-gate` | Implementation ready for a named human GATE; do not merge/deploy until registered |
| `done` | Mission closed (keep folder; never delete from updater) |

Exactly one mission may be `in-progress` or `awaiting-gate` at a time. Discover
with `bash scripts/active-mission.sh`.

## The loop

```
┌─ 1. INITIALIZER (orchestrator, once per mission)
│    - Create docs/missions/<date>-<slug>/ from templates (mission-init skill)
│    - Verify local CLIs + run scripts/fleet-inventory.sh (ALWAYS show map at GATE 0)
│    - Expand into features.json — every feature: description + verify steps + passes:false
│    - Human approves feature list + seat binds  ← GATE 0
│    - On approval: status → approved, then in-progress on first dispatch
│
├─ 2. DISPATCH (orchestrator, each cycle)
│    - Pick next passes:false feature(s)
│    - Write tasks/T-XXX.md from the template (one feature = one task)
│    - Choose worker; spawn via scripts/spawn-worker.sh (BLOCKING)
│
├─ 3. EXECUTE (worker, one session per task)
│    - Bearings: pwd → mission PROGRESS.md → features.json → git log
│    - Baseline check: typecheck + dev server + smoke test
│    - Read the skills the task file names
│    - Implement ONLY the task. Test end-to-end. Flip passes:true.
│    - Commit. Append PROGRESS.md entry.
│
├─ 4. REVIEW (orchestrator)
│    - Read the diff (git diff or PR), PROGRESS.md entry, and verify claims
│    - Check against AGENTS.md hard rules and the task's deny-list
│    - PASS → next dispatch. FAIL → write a correction task (do NOT let the same
│      worker "keep trying" without a rewritten task — that's how context rots)
│    - Recurring failure class? → add a line to AGENTS.md or a skill  ← the flywheel
│
└─ 5. GATE (human)
     - At milestones marked in GOAL.md: human reviews, merges, decides scope changes.
     - Set status: awaiting-gate while waiting; after human signs off, append a
       Human GATE entry to PROGRESS.md (required — chat alone is not the record).
     - Scope changes go through the orchestrator → features.json append. Never verbal.
```

## Human GATE registration (binding)

Before presenting a gate for approval (and before `status: done`):

```bash
bash scripts/verify-mission.sh   # must exit 0 — receipts required
```


When the human approves or rejects a gate (staging sign-off, merge permission,
deploy), the orchestrator MUST:

1. Ask the human (if they have not already typed it) to confirm the gate id and
   verdict before ending the session.
2. Append a PROGRESS.md entry of the form:

```markdown
## {{DATE}} — Human — GATE {{n}}
- **Verdict:** approved | rejected
- **Notes:** {{what they said / checked}}
- **Next:** {{status: done | in-progress | blocked}}
```

3. Update `GOAL.md` `status:` accordingly (`done` when the mission's last gate
   passes; otherwise back to `in-progress`).

Ending a session that reached a human gate without registering it in PROGRESS.md
is a protocol failure — future humans/agents cannot see the decision.

## Context-rot rules (binding for all agents)

1. **Fresh session per task.** Workers never carry a finished task's context into the
   next one. The handoff is the task file + PROGRESS.md + git — nothing else.
2. **Files are memory; context is scratch.** Anything worth remembering goes in
   PROGRESS.md, a commit message, or a doc. If it only exists in a chat window, it
   doesn't exist.
3. **MCP hygiene.** Query → persist result to a file → work from the file → don't
   keep the server chatty in context. Full procedure: `.agents/skills/mcp-hygiene/`.
4. **Compaction is a smell.** If a worker session needs compaction, the task was too
   big — split the feature, don't summarize and push on.
5. **Orchestrator context is precious too.** Workers report back in ≤10 lines
   (what changed, what passed, what's blocked). Never paste full diffs into the
   orchestrator chat — point to commits.

## WORKER_TASK format

Use `docs/missions/templates/WORKER_TASK.template.md`. Non-negotiable fields: objective (one
feature), context pointers (files to read, skills to follow), file allow-list, file
deny-list, exit criteria as binary checklist, test commands, iteration policy
(max attempts before escalating back to orchestrator).

## Escalation triggers (worker → orchestrator, immediately)

- A hard rule in AGENTS.md conflicts with the task
- The task requires touching a deny-listed file
- Baseline check fails and the fix isn't obvious in ≤15 min of work
- Two implementation attempts failed exit criteria
- Anything involving prod config, auth, secrets, or destructive DB ops
