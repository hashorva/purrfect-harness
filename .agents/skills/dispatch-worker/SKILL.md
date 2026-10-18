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
- Run `bash scripts/fleet-doctor.sh` before dispatch; any `ERROR` blocks dispatch.
- For a bug fix, reproduce the bug on the unfixed tree before dispatch, because a task whose oracle never failed on the base proves nothing.
- Name the exact field for every value a task states (for example `receipt.scope.result`, not the result), because a worker that has to guess the field guesses wrong.

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

For Cursor, the provider is `cursor` (binary `cursor-agent`), so
`spawn-worker.sh cursor ...` is the normal form, with the approved `standard` or
`fast` speed. `agent` is a legacy name: frozen v1 fleets and v3 specs record it,
and the launcher converts `cursor` to it. Do not dispatch as bare `agent`, because
Grok Build also installs a bare `agent`. Check the frozen seat before adapting the example.

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

### Brain `review` action (structured verdict)

`spawn-brain.sh … review` judges worker effects by diff and log; when the brain
records a structured review verdict as JSON, that document must validate against
`schemas/review-verdict.schema.json`. Check a saved verdict file:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_verdict.py \
  schemas/review-verdict.schema.json /path/to/verdict.json
```

When the verdict JSON is taken from a provider transcript saved to a file, read
each provider's `structured_output.json_schema_flag` in `harness-registry.json`.
If the flag is set, validate the saved file with the command above. If the
provider has no structured-output flag (for example cursor), use `--after-run`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_verdict.py --after-run \
  <provider> schemas/review-verdict.schema.json /path/to/output.txt
```

On success the script prints `mode=flag` or `mode=after-run`.

Receipt fields include `outcome`, `exit_code`, `git_before`, `git_after`,
`commits`, `changed_paths`, `workspace_changed`, and `scope`. Check that:

- UUID, mission, feature, work unit, attempt, and spec hash identify this dispatch.
- Outcome is `completed`, exit code is zero, workspace changed is true, and
  `scope.result` is `pass`.
- Changed paths and commits demonstrate the requested work within the allow-list.
- The log shows actual work, not a flag explanation, refusal, or unanswered question.
- Required checks have final results, and the receipt's `git_after` is clean (the
  worker committed).

New worker evidence cannot use null workspace-change values or legacy
`worker-*.json` receipts as a warning-only substitute. Exit zero alone is not
proof of implementation.

If the receipt's `git_after` is dirty (the worker did not commit), do not rewrite
the old receipt. Create a bounded qualification
task for the same pending feature, commit its checks and allow-list, and run
it from a clean base. Review and verify that new run; retain the implementation
run as evidence of its own effects.

## 4. Verify, then accept separately

Do this after effect review; later commits do not affect it:

```bash
RUN_ID="<UUID printed by the launcher>"
bash scripts/verify-mission.sh --run-id "$RUN_ID" "$MISSION"
```

This executes the verification argv from the task at the receipt's base commit.
It refuses a dirty receipt `git_after`, runs the checks in a temporary clean
worktree at the receipt's commit, and requires that worktree's snapshot to equal
the receipt's before and after the checks. A check that needs machine-local state
reads it through `$PURRFECT_LIVE_ROOT`. It creates one immutable record at
`$MISSION/verification/$RUN_ID.json`; it does not accept the feature.

Only after a passing result and effect review may the orchestrator compute the
exact record hash and accept:

```bash
VERIFICATION_SHA256=$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' \
  "$MISSION/verification/$RUN_ID.json")
bash scripts/accept-feature.sh --run-id "$RUN_ID" \
  --verification-sha256 "$VERIFICATION_SHA256" --accepted-by "orchestrator identity" "$MISSION"
python3 scripts/ledger.py fold "$MISSION"
bash scripts/verify-mission.sh --require-workers "$MISSION"
```

Acceptance records `accepted_run_id`, `accepted_verification_sha256`,
`accepted_at`, and `accepted_by` in features.json. No separate acceptance
artifact is needed. Each run's row stays gitignored under `.tasks/ledger/`
until fold; commit verification, acceptance, `docs/missions/ledger.jsonl`, and
`$MISSION/drift.jsonl` together with the progress record. A ledger row holds execution summaries only: no transcripts, prompts, secrets, or absolute paths.

## 5. Handle failures and gates

- Implementation/capability failure: follow the task's attempt limit and write a
  bounded correction task before retrying. An approved alternative seat may be
  selected explicitly; do not mutate the frozen fleet.
- Infrastructure failure (auth, quota, launch, transport): record what actually
  happened. It does not justify claiming success or changing an immutable record.
- No-op execution: investigate the task and log; do not treat exit zero as evidence.
- Missing final test output: the exit code is the result. A check without an
  exit code is unproven. An independent check can qualify a candidate, but
  cannot manufacture a passing VerificationRecord for an older snapshot.
- Before advancing a gate/status, run the current mission audit. Record the
  human verdict in PROGRESS.md and update status according to the approved gate.
- A follow-up that would loosen a gate, guard or check goes to the planner as a proposal, never to a worker as a fix, because loosening a gate is a planning decision.

Workers never accept features or change mission gates. Bootstrap exemptions must
be declared at feature authoring; they do not convert worker code into exempt work.

## Sandbox limits

Per-provider write limits live in `harness-registry.json` (`sandbox_limits`);
`dispatch_policy.py` refuses a worker task whose allow-list hits one before launch.
Login-state visibility limits are not decidable from a task file alone; they remain
routing rules in this table.

| Limit | Rule |
| --- | --- |
| Codex workspace-write cannot see Claude or agy login state; login checks are verification-only. | Do not run login checks (for example `scripts/fleet-doctor.sh`) as worker checks; put them in the task's verification commands. |
| Codex workspace-write can write under `.agents/` only when the task's allow-list names `.agents/…` paths: since contract 5 (T-013) the adapter then adds `--add-dir <repo>/.agents`. Broad patterns (`**`, `.agents`) do not enable it, so such a write still fails at run time. | Allow-list each skill edit by its `.agents/…` path (for example `.agents/skills/dispatch-worker/SKILL.md`) when the task goes to Codex. Write limits are data in `harness-registry.json` (`sandbox_limits`), which `dispatch_policy.py` enforces before launch. |

Worker checks are focused and sandbox-safe commands only; the full suite and
real-machine checks go in the task's verification commands. When a new limit is
found, add a row here and in the template note.

## Never

- Never use hand-written provider flags to bypass the shared adapter or frozen fleet.
- Never omit `--feature` or borrow another run's success.
- Never edit a persisted spec, receipt, or VerificationRecord to fit a later outcome.
- Never flip `passes` manually in place of the acceptance entry point.
- Never launch two writers or a verifier alongside a worker in the same workspace.
- Never dispatch an external repository through `--repo`.
- Never let a worker change features.json, fleet approval, or gates.
