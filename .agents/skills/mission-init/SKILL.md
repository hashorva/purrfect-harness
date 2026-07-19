---
name: mission-init
description: >
  Bootstrap an orchestrated mission: create GOAL.md, features.json, and the
  first WORKER_TASK from the repo's templates. MUST be used whenever the user
  says "start a mission", "new goal", "bootstrap the loop", "let's run the
  orchestration on X", or asks to begin orchestrated work of any kind. Also
  use to re-scope an existing mission. Produces files mechanically from
  docs/templates/ — never freestyle the formats.
---

# Mission init (orchestrator only)

## Step 0 — Preconditions

- No active mission: if GOAL.md or features.json already exist at repo root,
  STOP and ask the human whether to finish, archive (move to
  docs/missions/<date>-<name>/), or re-scope the current one.
- Read AGENTS.md (hard rules constrain every feature) and skim docs/ filenames
  so features reference real docs.

## Step 1 — Extract the mission (interview only if needed)

From the user's paragraph, determine: outcome (what will be TRUE at the end),
forcing function, explicit out-of-scope, human gates, ORCHESTRATOR BRAND
(opus | sol — apply docs/MODEL_ROUTING.md criteria; fable only by manual
override or declared task-class trigger), and FLEET TIER — economy
(default), premium (hard/risky missions: best model per CLI, high effort), or
mixed (per-worker). If the user didn't state a tier, propose one with a reason;
never silently assume premium. Missing pieces → ask
AT MOST 3 questions in one message. Do not start writing files until the
outcome is unambiguous.

## Step 2 — Write the three files FROM TEMPLATES (never from memory)

1. `cp docs/templates/GOAL.template.md GOAL.md` → fill every {{placeholder}}.
   Keep mission text to 2–4 sentences of OUTCOME, not tasks.
2. `cp docs/templates/features.template.json features.json` → replace example
   features. Rules for each feature:
   - description = user-observable behavior ("page renders X from Y"), never
     implementation ("add a useEffect")
   - steps = executable checks a worker can literally perform (navigate, run,
     grep, curl) — no vibes ("works correctly" is forbidden)
   - priority encodes the dependency DAG: structure before styling, schema
     before UI, low number = first
   - 3–10 features; bigger missions get split into two missions
   - every feature starts "passes": false
   - validate: `python3 -c "import json; json.load(open('features.json'))"`
3. Copy docs/templates/WORKER_TASK.template.md → docs/tasks/T-001.md for the
   priority-1 feature ONLY. Fill allow/deny lists from real repo paths
   (verify they exist), name the skills the task needs, set max_attempts: 2.

## Step 3 — GATE 0 (mandatory stop)

Present to the human: the feature list (id + description + priority only),
the Fleet table (tier + exact invocations, filled in GOAL.md), the resolved
orchestrator model+version (alias resolution logged to PROGRESS.md), which worker
T-001 is routed to and why (per dispatch-worker skill), and any assumption
made. DO NOT dispatch anything until the human approves. On
approval → follow .agents/skills/dispatch-worker/SKILL.md.

## Never

- Never invent file formats — templates are the only source of structure.
- Never write features the repo's AGENTS.md forbids.
- Never create more than the first WORKER_TASK at init (later tasks are written
  after earlier reviews, with real findings baked in).
