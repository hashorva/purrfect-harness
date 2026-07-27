---
name: mission-init
description: >
  Bootstrap an orchestrated mission: create a dated folder under docs/missions/
  with GOAL.md, features.json, PROGRESS.md, and the first WORKER_TASK from the
  repo's templates. MUST be used whenever the user says "start a mission",
  "new goal", "bootstrap the loop", "let's run the orchestration on X", or asks
  to begin orchestrated work of any kind. Also use to re-scope an existing
  mission. Produces files mechanically from docs/missions/templates/ — never
  freestyle the formats. Verifies local CLI agents (claude, codex, agent, agy)
  so dispatch can truly spawn workers on this machine.
---

# Mission init (orchestrator only)

## Step 0 — Preconditions

- No active mission: run `bash scripts/active-mission.sh`. If it prints a path,
  STOP and ask the human whether to finish (`status: done`), keep waiting on a
  gate, or re-scope. Never start a second `in-progress` / `awaiting-gate` mission.
- Also refuse leftover root `GOAL.md` / `features.json` (pre-2.0 layout) — move
  or delete them first.
- Read AGENTS.md (hard rules constrain every feature) and skim docs/ filenames
  so features reference real docs.
- Load `docs/missions/MODEL_ROUTING.md` once for this GATE 0 decision (not as
  ambient session context).

## Step 0b — Local CLI inventory (mandatory on this machine)

```bash
command -v claude; command -v codex; command -v agent; command -v agy
claude --version; codex --version; agent -v; agy --version
```

Record which CLIs are present in GOAL.md Fleet ("Verified local CLIs"). Missing
a CLI is fine — strike that row — but do not invent invocations for tools that
are not installed. First use of a present CLI: `<cli> --help` and confirm flags
still match `scripts/spawn-worker.sh` / dispatch-worker.

## Step 1 — Extract the mission (interview only if needed)

From the user's paragraph, determine: outcome (what will be TRUE at the end),
forcing function, explicit out-of-scope, human gates, ORCHESTRATOR BRAND
(opus | sol — apply MODEL_ROUTING.md criteria; fable only by manual override or
declared task-class trigger), and FLEET TIER — economy (default), premium
(hard/risky missions), or mixed (per-worker). Slug: `YYYYMMDD-short-kebab-name`
using today's date. If the user didn't state a tier, propose one with a reason;
never silently assume premium. Missing pieces → ask AT MOST 3 questions in one
message. Do not start writing files until the outcome is unambiguous.

## Step 2 — Write the mission folder FROM TEMPLATES (never from memory)

```bash
SLUG="{{YYYYMMDD-short-name}}"
MISSION="docs/missions/$SLUG"
mkdir -p "$MISSION/tasks"
cp docs/missions/templates/GOAL.template.md "$MISSION/GOAL.md"
cp docs/missions/templates/features.template.json "$MISSION/features.json"
cp docs/missions/templates/PROGRESS.template.md "$MISSION/PROGRESS.md"
cp docs/missions/templates/WORKER_TASK.template.md "$MISSION/tasks/T-001.md"
```

1. Fill every `{{placeholder}}` in GOAL.md. Keep mission text to 2–4 sentences of
   OUTCOME, not tasks. Set `status: draft`. Fill Fleet with verified CLI paths /
   `scripts/spawn-worker.sh` invocations.
2. Replace example features in features.json. Rules for each feature:
   - description = user-observable behavior ("page renders X from Y"), never
     implementation ("add a useEffect")
   - steps = executable checks a worker can literally perform (navigate, run,
     grep, curl) — no vibes ("works correctly" is forbidden)
   - priority encodes the dependency DAG: structure before styling, schema
     before UI, low number = first
   - 3–10 features; bigger missions get split into two missions
   - every feature starts "passes": false
   - validate: `python3 -c "import json; json.load(open('$MISSION/features.json'))"`
3. Fill `tasks/T-001.md` for the priority-1 feature ONLY. Allow/deny lists from
   real repo paths (verify they exist), name the skills the task needs,
   `max_attempts: 2`.

## Step 3 — GATE 0 (mandatory stop)

Present to the human: the feature list (id + description + priority only),
the Fleet table (tier + exact spawn commands), which CLIs were found on PATH,
the resolved orchestrator model+version (alias resolution logged to PROGRESS.md),
which worker T-001 is routed to and why (per dispatch-worker skill), and any
assumption made. DO NOT dispatch anything until the human approves.

On approval:
1. Append a Human — GATE 0 PROGRESS entry (verdict approved).
2. Set GOAL `status: approved` (then `in-progress` when the first spawn starts).
3. Follow `.agents/skills/dispatch-worker/SKILL.md` — spawn via
   `scripts/spawn-worker.sh`, never by re-doing the work solely inside the
   orchestrator chat when a worker CLI is available for that task class.

## Never

- Never invent file formats — templates are the only source of structure.
- Never write features the repo's AGENTS.md forbids.
- Never create more than the first WORKER_TASK at init (later tasks are written
  after earlier reviews, with real findings baked in).
- Never put mission files at repo root (harness 2.0.0+).
