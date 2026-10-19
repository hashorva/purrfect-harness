---
task_id: T-{{NNN}}
feature: {{F00X}}
worker: {{WORKER}}
invocation: {{INVOCATION}}
max_attempts: 2
size: medium
---

# Task: {{OBJECTIVE}}

## Before you write any code

1. Read `AGENTS.md`, this task, `{{MISSION}}/features.json`, and the newest
   mission `PROGRESS.md` entries. Run `git log --oneline -10`. Do not read `progress-archive/` (large history, not needed).
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

## Files you MUST NOT touch

- `{{DENIED_PATH}}`
- `{{MISSION}}/features.json`
- `{{MISSION}}/fleet.json`
- `{{MISSION}}/PROGRESS.md` (the Front Desk records your run from its receipt)
- existing execution specs, receipts, and VerificationRecords

## Verification commands

- `{{VERIFY_ARGV}}`

## Exit criteria (all must be true)

- [ ] Feature {{F00X}} steps verified with the checks above
- [ ] Every reproduced failure has a negative regression at its real entry point
- [ ] Only allow-listed files changed; final Git tree is clean
- [ ] Your final message reports the result, each check's exit code and any missing evidence (the Front Desk records it)
- [ ] Scoped change committed as `{{COMMIT_MESSAGE}}`
- [ ] No feature acceptance or gate/status change made by this worker

## Iteration policy

Max {{2}} attempts under this task. If exit criteria still fail, stop, state the
exact failure in your final message, and report back for a correction task. Never claim
success when a required check's final result is unavailable.

> Run a long check exactly once, e.g. `bash tests/run-tests.sh > /tmp/rt.log 2>&1; echo exit=$?`,
> then read the log tail. Never start a second copy of a command that is still running.

> Sandbox limits: per-provider write limits live in `harness-registry.json`
> (`sandbox_limits`); `dispatch_policy.py` refuses a task that hits one before
> launch. Login-state limits are routing-only (not decidable from the allow-list).
> (a) Codex workspace-write cannot see Claude or agy login state; login checks are
> verification-only. (b) Since contract 5 (T-013), a Codex task can write under `.agents/` when its allow-list names `.agents/…` paths: the adapter then adds `--add-dir <repo>/.agents`. Broad patterns (`**`, `.agents`) do not enable it.
> Worker checks are focused and sandbox-safe. The full suite and
> real-machine checks are verification commands, which `verify-mission.sh` runs
> outside the sandbox.

The result of a check is its exit code. Run the check and record the exit code.
You do not need to see a summary line (for example a final banner). Do not stop
only because the output is long or cut.
