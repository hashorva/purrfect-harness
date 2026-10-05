---
name: dispatch-worker
description: >
  Dispatch and review a WORKER_TASK through scripts/spawn-worker.sh using the
  mission's approved frozen fleet. MUST be used in the DISPATCH and REVIEW steps.
  Bind execution, receipt, verification, and orchestrator acceptance to one UUID
  run. Orchestrator-only; workers never dispatch other workers.
---

# Dispatch a worker (orchestrator only)

## Authority and scope

Run from the consuming repository root. Read AGENTS.md and
docs/missions/ORCHESTRATION.md for project rules and human gates.

Choose provider and tier from the mission's approved `fleet.json`. Live
inventory and the GOAL Fleet table explain the proposal; only the frozen file
authorizes worker dispatch. `invocation:` in a task is descriptive.
`--model`, `--effort`, and `--speed` assert equality with the frozen seat;
they cannot override it. Pass the approved effort and speed explicitly.

Routing preferences apply when selecting approved seats: Cursor premium Grok
or economy Composer, Codex inventory premium/economy, agy for an approved UI
lane, and Claude Sonnet/Haiku. An unavailable lane requires an explicit
orchestrator routing decision. Never silently fall back or rebind mid-mission.

Phase 1 runs in one repository. External `--repo` targets are rejected before
provider launch. There is no cross-repository dispatch or parallel scheduling.

## 1. Establish preconditions

- Read the task, mission PROGRESS.md, features.json, and `git log --oneline -10`.
- Mission status must already be `in-progress`; the wrapper does not promote
  `approved` automatically.
- The task is a direct Markdown file under the mission's `tasks/` directory.
  Its filename stem equals `task_id`, and its feature equals `--feature`.
- The feature is `passes: false`. The approved frozen fleet exists.
- The task's `Files you MAY touch` section contains only backtick-quoted
  repository-relative path/glob bullets, including PROGRESS.md if it will change.
- The task is committed before dispatch. Its `Verification commands` section
  contains consecutive Markdown code-span bullets, each a non-empty JSON argv.
- The tree is clean, the task baseline passes, the target CLI is available, and
  no worker or verifier is concurrently changing this workspace.

The wrapper validates authorization before persisting a spec or launching the
provider. Its exclusive workspace lock lasts through terminal receipt creation.

## 2. Dispatch the approved seat

Example for a mission whose frozen Codex economy seat has medium effort and
unknown speed:

```bash
MISSION=$(bash scripts/active-mission.sh)
bash scripts/spawn-worker.sh codex "$MISSION/tasks/T-XXX.md" \
  --tier economy --feature F00X --attempt 1 --effort medium --speed unknown
```

For Cursor, use the approved `agent` tier and its explicit `standard` or `fast`
speed. Check the frozen seat before adapting the example.

The launcher prints `run_id` and the log path. Keep that UUID; never select a
receipt by timestamp, task name, or “latest success.” One run writes:

- `.tasks/specs/<run-id>.json`: immutable authorization before launch
- `.tasks/logs/<run-id>.log`: provider transcript
- `.tasks/receipts/<run-id>.json`: terminal execution evidence

The shared runner manages timeout/interruption and provider process-tree cleanup.
The wrappers default to 2400 seconds via `SPAWN_WORKER_TIMEOUT_SECS` or
`SPAWN_BRAIN_TIMEOUT_SECS`; zero disables the timeout.

The worker wrapper snapshots itself before running. A scoped self-edit requires
an explicit task and review of the wrapper's restoration/lifecycle invariants;
the snapshot does not make arbitrary execution-policy edits safe.

## 3. Review observed effects

Use the exact receipt, scoped Git diff/commits, PROGRESS entry, and a short log
tail. Do not stream full transcripts into review context. Apply the project's
code-reviewer procedure and guard-verification for guards or safety tests.

Receipt fields include `outcome`, `exit_code`, `git_before`, `git_after`,
`commits`, `changed_paths`, `workspace_changed`, and `scope`. Check that:

- UUID, mission, feature, work unit, attempt, and spec hash identify this dispatch.
- Outcome is `completed`, exit code is zero, workspace changed is true, and
  `scope.result` is `pass`.
- Changed paths and commits demonstrate the requested work within the allow-list.
- The log shows actual work, not a flag explanation, refusal, or unanswered question.
- Required checks have final results, and the current Git snapshot still equals
  the receipt's after snapshot.

New worker evidence cannot use null workspace-change values or legacy
`worker-*.json` receipts as a warning-only substitute. Exit zero alone is not
proof of implementation.

If later review/progress commits changed the snapshot before run-specific
verification, do not rewrite the old receipt. Create a bounded qualification
task for the same pending feature, commit its checks and allow-list, and run
it from a clean base. Review and verify that new run; retain the implementation
run as evidence of its own effects.

## 4. Verify, then accept separately

Do this before making any further Git-visible change after the reviewed run:

```bash
RUN_ID="<UUID printed by the launcher>"
bash scripts/verify-mission.sh --run-id "$RUN_ID" "$MISSION"
```

This executes the verification argv from the task at the receipt's base commit.
It requires the current Git snapshot to equal the receipt's after snapshot before
and after the checks. It creates one immutable record at
`$MISSION/verification/$RUN_ID.json`; it does not accept the feature.

Only after a passing result and effect review may the orchestrator compute the
exact record hash and accept:

```bash
VERIFICATION_SHA256=$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' \
  "$MISSION/verification/$RUN_ID.json")
bash scripts/accept-feature.sh --run-id "$RUN_ID" \
  --verification-sha256 "$VERIFICATION_SHA256" --accepted-by "orchestrator identity" "$MISSION"
bash scripts/verify-mission.sh --require-workers "$MISSION"
```

Acceptance records `accepted_run_id`, `accepted_verification_sha256`,
`accepted_at`, and `accepted_by` in features.json. No separate acceptance
artifact is needed. Commit verification and acceptance with the progress record.

## 5. Handle failures and gates

- Implementation/capability failure: follow the task's attempt limit and write a
  bounded correction task before retrying. An approved alternative seat may be
  selected explicitly; do not mutate the frozen fleet.
- Infrastructure failure (auth, quota, launch, transport): record what actually
  happened. It does not justify claiming success or changing an immutable record.
- No-op execution: investigate the task and log; do not treat exit zero as evidence.
- Missing final test output: report the check as unproven. An independent check
  can qualify a candidate, but cannot manufacture a passing VerificationRecord
  for an older snapshot.
- Before advancing a gate/status, run the current mission audit. Record the
  human verdict in PROGRESS.md and update status according to the approved gate.

Workers never accept features or change mission gates. Bootstrap exemptions must
be declared at feature authoring; they do not convert worker code into exempt work.

## Never

- Never use hand-written provider flags to bypass the shared adapter or frozen fleet.
- Never omit `--feature` or borrow another run's success.
- Never edit a persisted spec, receipt, or VerificationRecord to fit a later outcome.
- Never flip `passes` manually in place of the acceptance entry point.
- Never launch two writers or a verifier alongside a worker in the same workspace.
- Never dispatch an external repository through `--repo`.
- Never let a worker change features.json, fleet approval, or gates.
