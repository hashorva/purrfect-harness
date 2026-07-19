---
paths:
  - "supabase/**"
---

# Database work — load-bearing pointers

You are touching schema/migration files. Before any edit:

1. Read `.agents/skills/supabase-migration/SKILL.md` and follow it exactly
   (CLI-named files only; check the project's apply path in AGENTS.md Step 5).
2. Read `docs/DATABASE.md` if it exists.
3. Never hand-create or rename migration files. Never `db reset`.
