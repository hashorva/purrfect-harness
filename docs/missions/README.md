---
title: Missions
version: 2.0.0
---

# Missions

Everything the orchestrator/worker loop needs lives here. Product docs stay
elsewhere under `docs/`. Instance folders (dated mission work) are
**project-owned** — `update-harness.sh` never deletes them.

## Layout

```text
docs/missions/
  README.md                 # this file
  ORCHESTRATION.md          # loop protocol
  MODEL_ROUTING.md          # load at GATE 0 / mission advance only
  templates/                # GOAL, features, PROGRESS, WORKER_TASK, bootstrap
  YYYYMMDD-short-name/      # one folder per mission (instance)
    GOAL.md
    features.json
    PROGRESS.md
    tasks/                  # WORKER_TASK files for this mission
      T-001.md
```

## Active mission

A mission is **active** when exactly one folder under `docs/missions/` (excluding
`templates/`) has `GOAL.md` frontmatter `status:` of `in-progress` or
`awaiting-gate`.

```bash
bash scripts/active-mission.sh          # prints the active dir, or exits 1
```

Never keep two missions active. Archive by setting `status: done` (keep the
folder). Root-level `GOAL.md` / `features.json` are obsolete as of harness 2.0.0.

## Starting a mission

Follow `.agents/skills/mission-init/SKILL.md`. It creates the dated folder from
templates, verifies local worker CLIs (`claude`, `codex`, `agent`, `agy`), and
stops at GATE 0.

## Fleet inventory (GATE 0)

```bash
bash scripts/fleet-inventory.sh    # seat → model map; write .tasks/fleet-inventory.json
```

Always show the map at GATE 0; human may remapp binds. See MODEL_ROUTING.md.

## Spawning a worker on this machine

Orchestrators must call the real CLIs installed on the Mac (not re-implement
inside one Cursor chat). Prefer:

```bash
bash scripts/spawn-worker.sh <codex|agent|agy|claude> docs/missions/<slug>/tasks/T-XXX.md --tier premium|economy
```

See `.agents/skills/dispatch-worker/SKILL.md` and `MODEL_ROUTING.md` (mission
advance only).
