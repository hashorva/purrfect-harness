---
task_id: T-{{NNN}}
feature: {{F00X from features.json}}
worker: cursor | codex | agy | claude
invocation: {{optional — overrides the GOAL.md Fleet row for this task only; also set on escalation}}
max_attempts: 2
---

# Task: {{one-line objective}}

## Before you write any code
1. Read `AGENTS.md` (root) — hard rules are binding.
2. Read `PROGRESS.md` (last 3 entries) and run `git log --oneline -10`.
3. Read these skills and follow them exactly:
   - `.agents/skills/{{skill-1}}/SKILL.md`
   - `.agents/skills/{{skill-2}}/SKILL.md`
4. Baseline: run `{{TYPECHECK_CMD}}` and start `{{DEV_CMD}}`. If broken, stop and report.

## Objective
{{Precise description. Reference exact files relative to known landmarks. Include
snippets/signatures where ambiguity is possible. Pre-answer every decision branch —
the worker must not need to ask anything.}}

## Files you MAY touch
- {{src/pages/FundDetail.tsx}}
- {{src/components/fund/*}}

## Files you MUST NOT touch
- {{supabase/** (no schema changes in this task)}}
- {{src/contexts/AuthContext.tsx}}
- features.json descriptions/steps (flip `passes` only)

## Exit criteria (all must be true)
- [ ] Feature {{F00X}} steps verified end-to-end
- [ ] `{{TYPECHECK_CMD}}` green
- [ ] `{{TEST_CMD}}` green
- [ ] Commit with message `{{type}}: {{short description}} (T-{{NNN}})`
- [ ] PROGRESS.md entry appended

## Iteration policy
Max {{2}} attempts. If exit criteria still fail, STOP, commit nothing further, write a
PROGRESS.md entry describing the failure, and report back — the orchestrator will
rewrite the task.
