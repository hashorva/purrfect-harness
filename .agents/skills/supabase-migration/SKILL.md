---
name: supabase-migration
description: >
  The only allowed workflow for writing AND applying a Supabase migration in any
  studio project. Activates on requests to add tables, alter columns, add indexes,
  add or modify RLS policies, add constraints, RPCs, or any other schema change —
  and on "push the migration", "apply the schema change". Do NOT use for seeding
  data, running read queries, or explaining schema. Applying SQL via MCP, the
  dashboard SQL editor, or a hand-named migration file is a failed task.
---

# Supabase Migration Skill (v2, studio-wide)

## Step 1 — Read before writing

- Read the project's `AGENTS.md` **Database rules** section — it defines this
  project's APPLY PATH (see Step 5) and any schema-specific invariants.
- Read the project's `docs/DATABASE.md` and/or `docs/ARCHITECTURE.md` if present.
- Run `supabase migration list` to confirm local/remote alignment. Diverged → STOP
  and escalate; do not "fix" by pushing.
- Check the 2–3 most recent files in `supabase/migrations/` to match style.

## Step 2 — Create the file (CLI names it — never hand-name)

```bash
supabase migration new <short_snake_case_description>
```

The CLI generates the timestamped filename. Hand-creating or renaming migration
files breaks ordering guarantees and is a failed task. Write the COMPLETE SQL into
the generated file.

## Step 3 — Migration file header

```sql
-- ============================================================
-- MIGRATION: <short description>
-- Date: YYYY-MM-DD
-- What / Why / Affected tables / Rollback:
-- ============================================================
```

## Step 4 — Checklist before applying (universal core)

- [ ] New table's access model is explicit BEFORE writing RLS/grants: user-RLS,
      service-role-only, or schema-level revoked
- [ ] Migration is additive (or has a rollback plan if destructive)
- [ ] Any new table has RLS enabled
- [ ] User-owned tables: policies cover all operations with both USING and WITH CHECK;
      indexes support RLS/user lookups
- [ ] Backend-only/IP tables: RLS enabled, NO browser policies
- [ ] Every new FK, filter, order, or effective-date query path has an index decision
- [ ] Reference data uses soft delete + `ON DELETE RESTRICT` inbound — never cascade
- [ ] PLUS the project-specific checklist items in the project's AGENTS.md /
      DATABASE.md (e.g. FinDuck: `auto_update_updated_at()` trigger, `response_type`
      CHECK on widget changes, no `user_id` in `internal.*`, `effective_to` inclusive)

## Step 5 — Apply (read the project's apply path from AGENTS.md)

**Path A — manual CLI push** (e.g. FinDuck):

```bash
supabase db push --dry-run   # must show exactly and ONLY your migration
supabase db push
# verify with a READ-ONLY query (MCP or psql): tables/columns/RLS/constraints
git add supabase/migrations/ && git commit -m "db: <description>"
```

**Path B — GitHub integration** (e.g. consulenza360):

```bash
git add supabase/migrations/ && git commit -m "db: <description>"
git push   # to the branch that deploys (usually main) per project rules
# the Supabase GitHub integration applies the migration on merge/push
# verify AFTER deployment with a READ-ONLY query
# do NOT run `supabase db push` unless the user explicitly asks for a manual push
```

If the project's AGENTS.md doesn't state the apply path → STOP and ask. Never guess.
In both paths: MCP and the dashboard are read-only verification, never a write path.

## Step 6 — Report before declaring done

- Summarise the diff; list affected tables, constraints, indexes, policies, RPCs
- Paste the Step 4 checklist, each item checked or N/A
- Paste the verification query result as evidence
- Mention any rollback limitation

## Step 7 — Never do these (universal)

- Never hand-name or hand-create migration files
- Never re-run a project's one-shot baseline schema file
- Never `supabase db reset` or destructive DDL without explicit human instruction
  in the current session
- Never modify the remote database from the dashboard except emergency inspection
- Never apply DDL through MCP
