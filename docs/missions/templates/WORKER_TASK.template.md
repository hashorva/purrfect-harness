---
task_id: T-{{NNN}}
feature: {{F00X}}
worker: {{WORKER}}
invocation: {{INVOCATION}}
max_attempts: 2
---

# Task: {{OBJECTIVE}}

## Before you write any code

1. Read `AGENTS.md`, this task, `{{MISSION}}/features.json`, and the newest
   mission `PROGRESS.md` entries. Run `git log --oneline -10`.
2. Read `{{SKILL_PATH}}` and the other skills required by the task.
3. Baseline: run `{{BASELINE_CMD}}`. If broken, stop and report.
4. You are the dispatched worker. Do not launch another worker or brain.

## Objective

{{OBJECTIVE}}

The invocation above records the approved provider, tier, model, effort, and
speed from this mission's frozen `fleet.json`; it cannot override that file.
Complete only this feature and stay within the allow-list below.

## Files you MAY touch

- `{{ALLOWED_PATH}}`
- `{{MISSION}}/PROGRESS.md` (prepend one entry only)

## Files you MUST NOT touch

- `{{DENIED_PATH}}`
- `{{MISSION}}/features.json`
- `{{MISSION}}/fleet.json`
- existing execution specs, receipts, and VerificationRecords

## Verification commands

- `{{VERIFY_ARGV}}`

## Exit criteria (all must be true)

- [ ] Feature {{F00X}} steps verified with the checks above
- [ ] Every reproduced failure has a negative regression at its real entry point
- [ ] Only allow-listed files changed; final Git tree is clean
- [ ] Mission PROGRESS.md records the result and any missing evidence
- [ ] Scoped change and progress entry committed as `{{COMMIT_MESSAGE}}`
- [ ] No feature acceptance or gate/status change made by this worker

## Iteration policy

Max {{2}} attempts under this task. If exit criteria still fail, stop, record the
exact failure in PROGRESS.md, and report back for a correction task. Never claim
success when a required check's final result is unavailable.

> Run a long check exactly once, e.g. `bash tests/run-tests.sh > /tmp/rt.log 2>&1; echo exit=$?`,
> then read the log tail. Never start a second copy of a command that is still running.

> Sandbox limits: per-provider write limits live in `harness-registry.json`
> (`sandbox_limits`); `dispatch_policy.py` refuses a task that hits one before
> launch. Login-state limits are routing-only (not decidable from the allow-list).
> (a) Codex workspace-write cannot see Claude or agy login state; login checks are
> verification-only. (b) Codex workspace-write cannot write under `.agents/`
> (PermissionError); route skill edits to a seat that can, until the adapter is
> fixed. Worker checks are focused and sandbox-safe. The full suite and
> real-machine checks are verification commands, which `verify-mission.sh` runs
> outside the sandbox.

The result of a check is its exit code. Run the check and record the exit code.
You do not need to see a summary line (for example a final banner). Do not stop
only because the output is long or cut.
