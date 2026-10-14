---
title: Missions
version: 2.3.2
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
    fleet.json              # immutable human-approved dispatch bindings
    verification/           # immutable run-specific VerificationRecords
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
templates, verifies local worker CLIs (`claude`, `codex`, `cursor-agent`, `agy`), and
stops at GATE 0.

## Fleet inventory (GATE 0)

```bash
bash scripts/fleet-inventory.sh    # seat → model map; write .tasks/fleet-inventory.json
```

Always show the map at GATE 0; the human may remap binds before approval.
Freeze the approved map as mission `fleet.json` using the mission-init skill.
Dispatch reads that snapshot, not mutable inventory. See MODEL_ROUTING.md.

## Brain + worker receipts (proof of CLI)

```bash
# Draft brain action: pass the proposed chair's concrete configuration.
bash scripts/spawn-brain.sh "$MISSION" mission-init \
  --provider "$BRAIN_PROVIDER" --model "$BRAIN_MODEL" \
  --effort "$BRAIN_EFFORT" --speed "$BRAIN_SPEED"
# After Human Gate 0, frozen fleet, and committed in-progress status:
bash scripts/spawn-worker.sh agent "$MISSION/tasks/T-XXX.md" \
  --tier premium --feature F00X --effort "$APPROVED_EFFORT" --speed "$APPROVED_SPEED"
bash scripts/verify-mission.sh --run-id "$RUN_ID" "$MISSION"
# Effect review and separate accept-feature.sh invocation precede this audit:
bash scripts/verify-mission.sh --require-workers "$MISSION"
```

PROGRESS alone is not evidence. One UUID links `.tasks/specs/<uuid>.json`,
`.tasks/receipts/<uuid>.json`, the mission VerificationRecord, and orchestrator
acceptance fields. See ORCHESTRATION.md for the exact acceptance command.
External `--repo` execution is disabled in Phase 1.

## Spawning a worker on this machine

Orchestrators must call the real CLIs installed on the Mac (not re-implement
inside one Cursor chat). Prefer:

```bash
bash scripts/spawn-worker.sh "$PROVIDER" "$MISSION/tasks/T-XXX.md" \
  --tier "$TIER" --feature F00X --attempt 1 \
  --effort "$APPROVED_EFFORT" --speed "$APPROVED_SPEED"
```

See `.agents/skills/dispatch-worker/SKILL.md` and `MODEL_ROUTING.md` (mission
advance only).
