# Changelog — agent-harness kit

## 2.0.0 (2026-07-27)
- **BREAKING — mission layout:** orchestration lives under `docs/missions/`. Protocol +
  `MODEL_ROUTING.md` + templates move there; instance missions are
  `docs/missions/<YYYYMMDD-slug>/{GOAL,features,PROGRESS,tasks/}`. Root `GOAL.md` /
  `features.json` are obsolete. Stubs remain at `docs/ORCHESTRATION.md`,
  `docs/MODEL_ROUTING.md`, `docs/templates/README.md` for old links.
- **Active mission** = exactly one folder with GOAL `status: in-progress|awaiting-gate`
  (`scripts/active-mission.sh`). Status lifecycle: `draft` → `approved` →
  `in-progress` → `awaiting-gate` → `done`.
- **Human GATE registration** required in PROGRESS.md; session-end rule: agents must
  ask before ending when a gate is pending. Chat approval alone is not the record.
- **Local CLI spawn:** `scripts/spawn-worker.sh` runs `codex` / `agent` / `agy` /
  `claude` on the machine PATH with economy pins and `.tasks/logs/`. dispatch-worker +
  mission-init require real CLI inventory (`command -v`) — orchestrators must not
  silently absorb fleet work into one chat when CLIs are available.
- `update-harness.sh` / install copy kit-owned mission *protocol* paths only — never
  wipe project mission folders. AGENTS.md skeleton ports the new layout (manual merge
  in consuming repos).
- MAJOR: consuming repos need AGENTS.md section port + move any root mission into
  `docs/missions/<slug>/` before relying on the loop.

## 1.11.0 (2026-07-19)
- NEW `docs/MODEL_ROUTING.md` — four routing criteria (horizon, silent-error cost, verifiability, volume); orchestrator policy: Opus (alias `--model opus`, effort high/extra) OR GPT-5.6 Sol (effort high) chosen per mission at GATE 0; Fable 5 demoted to evidence-gated escalation (2x review failure, mission stall, features churn, declared task class, or manual override) — self-reported confidence explicitly rejected as a trigger
- Alias doctrine: invocations use CLI aliases so new flagships (Opus 5, ...) are adopted automatically at the NEXT GATE 0, never mid-mission; resolved model+version logged in PROGRESS.md; deliberate pin bumps = PATCH
- ORCHESTRATION.md + dispatch-worker: "Fable/Opus always-premium" wording replaced with MODEL_ROUTING reference (post 2026-07-20 Fable paywall, the old line silently spent API credits)
- GOAL.template.md: Fleet gains an Orchestrator line; stale `claude-sonnet-4-6` pin replaced by `haiku`/`sonnet` aliases
- mission-init: orchestrator brand is a GATE 0 decision; GATE 0 presents the resolved model
- Price snapshot quarantined in a dated appendix (decays fast, never load-bearing)
- update-harness.sh: docs/MODEL_ROUTING.md added to KIT_PATHS (propagates on update)
- NEW LICENSE (CC BY-NC-SA 4.0): attribution required, non-commercial, share-alike
- NEW .github/workflows/ci.yml — shellcheck, JSON template validation, version-consistency (README vs CHANGELOG), end-to-end install/update test in a throwaway repo
- NEW .github/workflows/release.yml — on tag v*: tag==CHANGELOG guard, GitHub Release with kit zip + notes extracted from CHANGELOG
- NEW tests/run-tests.sh — install collision rules (absent/identical/different), symlinks, .harness-version, update path
- NEW docs/PUBLISHING.md — first-publish and every-release runbooks (gh CLI)

## 1.10.0 (2026-07-09)
- NEW `scripts/install-harness.sh` — first-time install with conservative collision rule (absent→copy, identical→skip, different→.harness-new; AGENTS.md never proposed against, arrives as .template; refuses repos already under management)
- README: install section rebuilt as "Purrfect Install" — separate new-repo vs existing-repo flows, each with a Mermaid diagram, script snippets, manual TODOs, and the pre-merge ritual

## 1.9.1 (2026-07-09)
- README: detailed install procedure (6 steps, verify checklist) + two Mermaid diagrams (anatomy: who-reads-what; mission lifecycle: trigger chain)
- NEW docs/RELEASING.md — SemVer interpretation for a harness, annotated-tag release procedure, propagation rules
- Docs-only: no behavioral change (hence PATCH)

## 1.9.0 (2026-07-09)
- NEW `scripts/update-harness.sh` — safe propagation to consuming repos: clean-tree check, update branch, overwrites kit-owned manifest paths only, settings.json via .new file, records .harness-version, never auto-commits
- README: ownership model (kit-owned / project-owned / merged) + the two laws (never edit kit files in repos; improvements flow upstream, never sideways)

## 1.8.0 (2026-07-09)
- NEW `.agents/skills/skillify/SKILL.md` — evidence-based skill graduation (≥2 occurrences, deterministic, verifiable, human-gated; patch-over-create)
- `docs/ORCHESTRATION.md`: added "Orchestrator contract" (5 requirements; role is protocol-agnostic; Claude Code = only enforced implementation; enforcement ports deferred to a forcing event)
- Deliberately NOT shipped after break-even analysis: multi-orchestrator enforcement configs, auto-parallel dispatch

## 1.7.0 (2026-07-09)
- Dynamic per-mission fleet: `## Fleet` table added to GOAL.template.md (tier chosen at GATE 0)
- WORKER_TASK.template.md: optional `invocation:` frontmatter (per-task override; doubles as escalation mechanism)
- dispatch-worker: invocation precedence chain — task frontmatter > GOAL.md Fleet > machine economy defaults
- mission-init: fleet tier (economy/premium/mixed) is an explicit GATE 0 decision; never silently premium

## 1.6.0 (2026-07-09)
- dispatch-worker: mandatory cost pinning — fleet table with pinned invocations (`codex exec --profile worker`, `agent --model composer`, agy flash-tier, `claude -p --model claude-haiku-4-5`)
- Escalation rule: tier-up only inside a task rewrite after CAPABILITY failure, one tier at a time, logged
- One-time machine setup documented: `~/.codex/worker.config.toml` (cheap model, medium effort, workspace-write)

## 1.5.0 (2026-07-09)
- dispatch-worker rewritten: real fleet CLIs (codex / agent / agy / claude -p); two failure classes — CAPABILITY (burns attempt) vs INFRASTRUCTURE (quota/429/stall: reset tree, reassign, no attempt burned); completion = blocking process exit; parallelism rules (never two workers same tree; pipelining encouraged; cross-repo OK; worktrees deferred)
- NEW `.agents/skills/mission-init/SKILL.md` — deterministic mission bootstrap from templates (GOAL.md + features.json + T-001 only), GATE 0 mandatory stop
- settings.json allow-list updated to real CLI names

## 1.4.0 (2026-07-09)
- NEW `.agents/skills/dispatch-worker/SKILL.md` — spawn via Bash with log redirect, three-question routing, judge-by-effects, two-attempt policy
- settings.json: worker CLIs pre-allowed

## 1.3.0 (2026-07-09)
- NEW Claude Code enforcement layer: `.claude/settings.json` (deny rm -rf / db reset / force-push / credential reads; allow routine verification), `.claude/rules/database.md` + `ui.md` (path-gated pointers), `.claude/agents/code-reviewer.md` (read-only review subagent, PASS/FAIL + flywheel note)
- README: enforcement-vs-guidance section; documented deliberate omissions (commands/, output-styles/, workflows/, .mcp.json, local/memory files)

## 1.2.0 (2026-07-09)
- Skills promoted to v2 universal: shadcn-luma (Luma preset b2D0wqNxT mechanics, apply vs --only theme, --base radix studio convention); supabase-migration (apply Path A `db push` vs Path B GitHub integration, read from project AGENTS.md)
- Templates: MD025 fix (removed `title:` frontmatter)
- README: four-layer model (AGENTS.md=rules, docs/=knowledge, skills=procedures, templates=dormant loop)

## 1.1.0 (2026-07-09)
- AGENTS.md template restructured to the FinDuck skeleton (Product → Stack → ... → Orchestrated missions → Repo structure)
- Install switched to whole-directory symlinks (3 one-liners); sync-skills.sh demoted to optional

## 1.0.0 (2026-07-09)
- Initial kit: AGENTS.md template, thin CLAUDE.md/GEMINI.md wrappers, docs/ORCHESTRATION.md, 4 templates (GOAL, features.json, PROGRESS, WORKER_TASK), 5 skills (supabase-migration, shadcn-luma, react-conventions, mcp-hygiene, cloudflare-deploy), sync-skills.sh
