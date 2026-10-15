---
title: Orchestration Protocol
version: 3.0.0
---

<!-- markdownlint-disable MD025 -->

# Orchestration Protocol — Orchestrator + Cheap Workers

One orchestrator plans, decomposes, dispatches, and reviews — **Opus by
default** per [`MODEL_ROUTING.md`](MODEL_ROUTING.md). Cursor (often Grok) may
intake a brief plan; Opus weighs it and runs the mission loop. Human may name
Fable or Codex/Sol as chair, or declare “no orchestration.” Cheap workers
(Cursor `cursor-agent`: Grok premium / Composer economy; Codex Terra/Luna-class;
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
4. Never edits approved features.json descriptions/steps; only the orchestrator
   accepts a feature through `accept-feature.sh` after current verification evidence
5. Writes its actions to the shared artifacts (PROGRESS.md, git) — not private memory

Claude Code may use the bundled client permission configuration in
`.claude/settings.json`, plus path rules and the code-reviewer subagent. Those client settings are
not an absolute security boundary or privileged Claude-only enforcement; every
orchestrator remains accountable to the same repository rules and verification.

**Local CLI rule:** when the loop runs on a Mac with studio CLIs installed, the
orchestrator MUST spawn the **brain** via `scripts/spawn-brain.sh` and workers via
`scripts/spawn-worker.sh`. Each spawn writes a UUID-keyed spec, log, and terminal
receipt under `.tasks/`. Only the shared adapter resolves provider arguments.
Before acceptance, run verification for the exact run UUID; before advancing a
gate/status, the current mission audit must exit 0. Doing all features inside one
Cursor chat without spawns is a failed dispatch — PROGRESS prose is not proof.

## Roles & dispatch table

| Agent                                                                                                                                                   | Role                                                                                                                  | Send it                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| **Orchestrator / brain** (Opus default; Fable or Sol only when human names them or when it starts from a chat with Sol or Fable — see MODEL_ROUTING.md) | Weigh intake plan → features.json, WORKER_TASK files, review diffs, arbitrate, update AGENTS.md when decisions change | The GOAL, review requests, "what next"         |
| **Cursor Agent** (`cursor-agent`)                                                                                                                       | Multi-file work: **Grok** = premium, **Composer** = economy (Grok falls back to Composer)                             | WORKER_TASK files; small safe tasks → Composer |
| **Codex** (`codex`)                                                                                                                                     | Inventory seats: Sol = brain when named; Terra ≈ premium; Luna ≈ economy                                              | Tight allow-lists / verifiable tasks           |
| **Antigravity** (`agy`)                                                                                                                                 | **UI lane** (shadcn/Luma/appearance) + opt-in workers; Flash economy / Pro premium                                    | UI WORKER_TASKs; or when human says use agy    |
| **Claude** (`claude -p`)                                                                                                                                | Haiku economy / Sonnet premium workers (not the default chair)                                                        | Tight allow-list tasks                         |

Rule of thumb: **judgment up, volume down.** Anything requiring a decision that isn't
already written in AGENTS.md / a skill / the task file goes UP to the orchestrator, never
improvised by a worker.

## Mission folder & GOAL status

Missions live under `docs/missions/<YYYYMMDD-slug>/`. Root `GOAL.md` /
`features.json` are not valid after harness 2.0.0.

`GOAL.md` frontmatter `status:`:

| Status          | Meaning                                                                           |
| --------------- | --------------------------------------------------------------------------------- |
| `draft`         | Files written; GATE 0 not approved                                                |
| `approved`      | Human approved feature list; no dispatch yet                                      |
| `in-progress`   | Workers may run; active mission                                                   |
| `awaiting-gate` | Implementation ready for a named human GATE; do not merge/deploy until registered |
| `done`          | Mission closed (keep folder; never delete from updater)                           |

Exactly one mission may be `in-progress` or `awaiting-gate` at a time. Discover
with `bash scripts/active-mission.sh`.

## The loop

```text
┌─ 1. INITIALIZER (orchestrator, once per mission)
│    - Create docs/missions/<date>-<slug>/ from templates (mission-init skill)
│    - Verify local CLIs + run scripts/fleet-inventory.sh (ALWAYS show map at GATE 0)
│    - Expand into features.json — every feature: description + verify steps + passes:false
│    - Human approves feature list + seat binds  ← GATE 0
│    - Freeze approved bindings as mission fleet.json; commit approved state
│    - Explicitly transition and commit in-progress before first dispatch
│
├─ 2. DISPATCH (orchestrator, each cycle)
│    - Pick one assigned passes:false feature
│    - Write tasks/T-XXX.md from the template (one feature = one task)
│    - Choose worker; spawn via scripts/spawn-worker.sh (BLOCKING)
│
├─ 3. EXECUTE (worker, one session per task)
│    - Bearings: pwd → mission PROGRESS.md → features.json → git log
│    - Baseline check: the task's project-appropriate checks
│    - Read the skills the task file names
│    - Implement ONLY the task. Test end-to-end; report evidence to the orchestrator.
│    - Commit scoped implementation and PROGRESS.md; leave a clean tree.
│
├─ 4. REVIEW (orchestrator)
│    - Read the diff (git diff or PR), PROGRESS.md entry, and verify claims
│    - Check against AGENTS.md hard rules and the task's deny-list
│    - PASS → verify the exact run, then accept its VerificationRecord hash through
│      accept-feature.sh. FAIL → write a correction task (do NOT let the same
│      worker "keep trying" without a rewritten task — that's how context rots)
│    - Recurring failure class? → add a line to AGENTS.md or a skill  ← the flywheel
│
└─ 5. GATE (human)
     - At milestones marked in GOAL.md: human reviews, merges, decides scope changes.
     - Set status: awaiting-gate while waiting; after human signs off, append a
       Human GATE entry to PROGRESS.md (required — chat alone is not the record).
     - Scope changes go through the orchestrator → features.json append. Never verbal.
```

## Execution truth and acceptance

Worker dispatch requires an `in-progress` mission, one committed task for one
pending feature, a clean tree, approved canonical `fleet.json`, supported
configuration, and an exclusive workspace lock. External `--repo` targets are
disabled in Phase 1. Task `invocation:` is descriptive; model/effort/speed flags
are equality assertions against the frozen seat. Live inventory cannot rebind it.

One UUID links four distinct truths:

| Artifact | Question it answers |
| --- | --- |
| `.tasks/specs/<uuid>.json` | What was authorized before launch? |
| `.tasks/receipts/<uuid>.json` | What actually ran and changed? |
| `<mission>/verification/<uuid>.json` | Did that run pass its committed checks? |
| Feature acceptance fields in `features.json` | Which verified run did the orchestrator accept? |

Current ExecutionSpec v3 binds provider contract 2; v1/v2 evidence retains
historical contract 1 semantics. A receipt records Git-visible before/after
state, commits, changed paths, scope, and terminal outcome. The scope guarantee
is limited to Git-visible changes in the declared workspace; it is not general
filesystem containment. Unknown provider observations remain `unknown`.

After effect review (later commits do not affect it; checks run at the
receipt's commit):

```bash
bash scripts/verify-mission.sh --run-id "$RUN_ID" "$MISSION"
```

The verifier reads JSON argv bullets from the task at the receipt's base commit,
requires a clean receipt `git_after`, then checks out that commit in a temporary
detached worktree and requires its snapshot to match before and after checks. A
check that needs machine-local state (for example `.tasks/`) reads it through
`$PURRFECT_LIVE_ROOT`. The verifier atomically creates an immutable
VerificationRecord in the live mission. It does not change feature acceptance.
Only the orchestrator then runs:

```bash
VERIFICATION_SHA256=$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' \
  "$MISSION/verification/$RUN_ID.json")
bash scripts/accept-feature.sh --run-id "$RUN_ID" \
  --verification-sha256 "$VERIFICATION_SHA256" --accepted-by "orchestrator identity" "$MISSION"
bash scripts/verify-mission.sh --require-workers "$MISSION"
```

Acceptance records `accepted_run_id`, `accepted_verification_sha256`, `accepted_at`,
and `accepted_by`. A failed, no-op, unrelated, legacy, or null-evidence run cannot
stand in for this chain. Retain old artifacts without manufacturing acceptance.
If the receipt's `git_after` is dirty (the worker did not commit), the verifier
refuses it; dispatch a bounded qualification task for the pending feature and
verify its new run; do not rewrite old evidence.

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

<!-- markdownlint-disable MD029 -->

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
(max attempts before escalating back to orchestrator). The allow-list uses
backtick-quoted relative-path bullets. Verification commands use consecutive
Markdown code-span bullets containing non-empty JSON argv arrays; a missing or
malformed section is rejected. Workers never edit features.json or accept work.

## Escalation triggers (worker → orchestrator, immediately)

- A hard rule in AGENTS.md conflicts with the task
- The task requires touching a deny-listed file
- Baseline check fails and the fix isn't obvious in ≤15 min of work
- Two implementation attempts failed exit criteria
- Anything involving prod config, auth, secrets, or destructive DB ops
