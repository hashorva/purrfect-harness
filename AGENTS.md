---
spec: AGENTS.md v1.1 (aligned to FinDuck skeleton, Jul 2026)
tools: {{Claude Code (backend/execution), Antigravity (frontend), Codex (execution), Cursor (parallel implementation)}}
---

# {{PROJECT_NAME}} — Agent Instructions

## Product

{{2–4 lines: what this is, who it's for, what the AI component is called if any.
Part of purrfect.build studio (4 products sharing infrastructure). Live at: {{domain}}}}

## Stack

- Frontend: {{e.g. Vite + React + TypeScript + Tailwind CSS v4 + shadcn/ui (Luma theme)}}
- Backend: {{e.g. Cloudflare Worker (`purrfect-worker`) — route prefix `/{{product}}/`}}
- Database: {{e.g. Supabase PostgreSQL (region) — schema baseline + migrations}}
- Auth: {{mechanism; where tokens live; what never touches localStorage}}
- Deploy: {{e.g. Cloudflare Pages, auto-deploy from GitHub `main`}}
- Local toolchain: {{e.g. Node.js + npm only (lockfile: package-lock.json)}}

## Deployment discipline

- {{e.g. `main` auto-deploys to production. Treat every merge to `main` as a production change.}}
- {{e.g. Risky DB/auth/refactor work goes through a branch + staging, never direct to `main`.}}

## Package manager — {{npm only}}

| Task | Command |
| --- | --- |
| Install | {{npm install}} |
| Dev server | {{npm run dev}} |
| Production build | {{npm run build}} |
| TypeScript check | {{npm run typecheck}} |
| Tests | {{npm test}} |
| Lint | {{npm run lint}} |

## Security invariants — never violate

- {{e.g. Never expose the service-role key to the frontend or commit it to git}}
- {{e.g. Never accept user_id from the request body — derive from the verified JWT}}
- {{e.g. Backend-only tables/schemas and their access model}}
- {{e.g. Soft delete rules for reference data}}
- Never commit secrets. `.env*` stays untracked.

## Database rules

- Schema changes follow `.agents/skills/supabase-migration/SKILL.md` — CLI creates the
  file (`supabase migration new`), then dry-run → push → verify → commit. MCP is
  read-only verification, never a write path.
- {{project-specific query/client rules, e.g. the getDB()/getUserDB() split}}
- Before touching RLS, auth, or migrations → consult `docs/DATABASE.md` {{if it exists}}

## Frontend rules

- {{canonical types location; forbidden imports; data-access boundary}}
- For UI work → consult `docs/DESIGN.md` {{if it exists}} and
  `.agents/skills/shadcn-luma/SKILL.md` before changing components or adding styles

## Repo boundary

- {{list the repos this project touches and the rule: do not edit across repos in a
  single task unless explicitly instructed; propose a two-step plan instead}}

## Skills (procedures — read before improvising)

Reusable procedures live in `.agents/skills/` (Agent Skills open standard; canonical
source of truth). Tool discovery paths (`.claude/skills`, `.cursor/skills`,
`.gemini/skills`) are whole-directory symlinks to it — edit skills ONLY in
`.agents/skills/`. If a task matches a skill (migrations, shadcn/Luma UI, MCP usage,
deploys, components), read that SKILL.md and follow it. Re-deriving a procedure a
skill already covers is a failed task.

## Workflow

- Inspect existing file structure before editing — audit before assuming
- Prefer small, reviewable diffs — one concern per commit
- Do not introduce new production dependencies without explaining the reason
- Do not edit `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or any file under `docs/` unless
  the task is explicitly about project instructions or agent rules
- Run `{{npm run typecheck}}` after any TypeScript change; `{{npm run build}}` if build
  config is affected
- When stuck or if planning exceeds 3 iterations without a clear path → STOP, output
  your current hypothesis, and request human intervention. Never guess on schema,
  security, or architecture.

## Orchestrated missions (GOAL/features loop — active only when a mission is)

Some work runs as an orchestrator/worker loop. Full protocol:
`docs/missions/ORCHESTRATION.md`. A mission is **active** when exactly one folder
under `docs/missions/<slug>/` has `GOAL.md` status `in-progress` or
`awaiting-gate` (`bash scripts/active-mission.sh`). Model routing lives only at
`docs/missions/MODEL_ROUTING.md` — load at GATE 0 / mission advance, not casually.
When active, these rules apply on top of everything above:

- **Session start (bearings):** resolve the active mission dir; read its
  `PROGRESS.md` (last 3 entries), `features.json`, and `git log --oneline -10`
  before editing anything. Verify baseline (typecheck) before implementing; if
  the repo is broken, fix/report that first.
- **One feature per session.** Pick the assigned (or highest-priority)
  `passes: false` feature. Never start a second one in the same session.
- **`features.json` is append-only truth.** Agents may only flip
  `"passes": false → true` after verifying every step end-to-end. Editing or
  removing descriptions/steps is a failed task. `GOAL.md` is narrative; if they
  disagree, `features.json` wins.
- **Session end (clean state):** typecheck green, tests green, committed with a
  descriptive message, one entry appended to the mission `PROGRESS.md`. If a
  human gate is pending, **ask** to register the Human GATE verdict in
  PROGRESS.md and update GOAL `status` before ending — chat alone is not the record.
- **WORKER_TASK files are binding.** If you received one, it is your entire scope;
  its file allow/deny lists override any broader interpretation of the goal.
  Respect its iteration policy, then STOP and report — never keep grinding.
- **Local CLI workers.** Orchestrators spawn work via
  `scripts/spawn-worker.sh --tier economy|premium` using CLIs on this machine
  (`claude`, `codex`, `agent`, `agy`). Cursor: Grok = premium, Composer = economy.
  Run `scripts/fleet-inventory.sh` at GATE 0 and show the map for human confirm/swap.
  Default brain is Opus unless the human names Fable/Sol/current-chat or skips
  orchestration. Do not silently absorb fleet work into one chat when CLIs exist.

## Repo structure (key paths)

- {{src/pages/... — main routes}}
- {{src/types/... — canonical types}}
- `.agents/skills/` — canonical agent skills (symlinked into per-tool paths)
- `docs/missions/` — orchestration protocol, MODEL_ROUTING, templates, mission folders
- `scripts/active-mission.sh` / `scripts/spawn-worker.sh` / `scripts/fleet-inventory.sh`