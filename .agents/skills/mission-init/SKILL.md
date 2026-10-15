---
name: mission-init
description: >
  Bootstrap or re-scope an orchestrated mission from docs/missions/templates/.
  MUST be used when beginning orchestrated work. Present the feature list and
  truthful fleet inventory at Human Gate 0, then freeze approved bindings in the
  mission's fleet.json before worker dispatch. Default chair is Opus unless the
  human names another chair.
---

# Mission init (orchestrator only)

## 1. Establish scope and chair

Read AGENTS.md and docs/missions/MODEL_ROUTING.md. Run
`bash scripts/active-mission.sh`; do not create a second active mission. For an
existing active mission, follow the human's direction to finish, wait, or re-scope.
Root-level GOAL.md and features.json are obsolete; resolve them before starting.

Determine outcome, forcing function, non-goals, human gates, and fleet tier.
Default brain is Opus. A human-named chair or “you are the orchestrator” selects
that chair; “no orchestration” means this skill does not govern the work.
Fable is named only, never an automatic escalation.

## 2. Inventory the local fleet

```bash
bash scripts/fleet-doctor.sh
bash scripts/fleet-inventory.sh
```

Any `ERROR` from the doctor (two different programs under one name, wrong
identity, logged out) must be fixed before Gate 0. `WARN` lines (duplicate PATH
entries, symlinks to the same binary, a missing CLI) are listed in the Gate 0 report.

Present the actual seat/provider/model/family/health/source map at Gate 0.
Unavailable providers cannot be bound. Failed probes preserve per-provider
last-good state as degraded; fallback guesses remain degraded, never observed.
Inventory is a local proposal, not worker dispatch authority.

## 3. Create and fill the templates

```bash
SLUG="{{YYYYMMDD-short-name}}"
MISSION="docs/missions/$SLUG"
mkdir -p "$MISSION/tasks"
cp docs/missions/templates/GOAL.template.md "$MISSION/GOAL.md"
cp docs/missions/templates/features.template.json "$MISSION/features.json"
cp docs/missions/templates/PROGRESS.template.md "$MISSION/PROGRESS.md"
cp docs/missions/templates/WORKER_TASK.template.md "$MISSION/tasks/T-001.md"
```

Fill every placeholder and keep GOAL status `draft`. Include proposed seats
in GOAL Fleet and author one pending feature per task. Validate JSON and commit
the draft before launching a brain; all launcher paths require a clean tree.

The worker task must contain:

- matching filename stem, `task_id`, and `feature`;
- a `Files you MAY touch` section of backtick-quoted relative paths/globs;
- PROGRESS.md in the allow-list if the worker will update it;
- a `Verification commands` section with consecutive code-span bullets,
  each containing a non-empty JSON argv of non-empty strings;
- a scope, baseline, exit criteria, and bounded iteration policy.

Example command bullet:

```markdown
- `["bash","tests/run-tests.sh"]`
```

Commit the finalized task before dispatch: verification reads its authorized
commands from the receipt's base commit, not from a later edited task.

### Task planning (structured plan)

When the brain decomposes work into a structured task plan (a JSON document,
not only committed `tasks/T-*.md` files), that plan must validate against
`schemas/task-plan.schema.json`. Check a saved plan file:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_verdict.py \
  schemas/task-plan.schema.json /path/to/plan.json
```

When the plan JSON is taken from a provider transcript saved to a file, use
`validate_verdict.py --after-run` as documented in dispatch-worker for
providers whose registry `structured_output.json_schema_flag` is null; otherwise
validate the saved JSON file directly with the command above.

### Bootstrap is an authoring decision

Keep a `bootstrap` boolean on every feature. Use `"bootstrap": false` for worker
implementation; acceptance needs an exact passing VerificationRecord linked to
its spec and receipt. `"bootstrap": true` exempts work no worker will run, such as scaffolding
or recorded orchestrator decisions. It does not exempt code merely because a
worker failed.

Choose the exemption before Gate 0. The current audit fails closed for missing
non-bootstrap evidence; it never borrows another feature's receipt.

## 4. Obtain real brain evidence and present Gate 0

Select the proposed brain variables from the truthful inventory and the human's
chair choice:

```bash
bash scripts/spawn-brain.sh "$MISSION" mission-init \
  --provider "$BRAIN_PROVIDER" --model "$BRAIN_MODEL" \
  --effort "$BRAIN_EFFORT" --speed "$BRAIN_SPEED"
bash scripts/verify-mission.sh "$MISSION"
```

Draft `mission-init` and `gate0` actions permit explicit configuration;
later `review` uses the frozen brain seat. Keep the tree clean between launches.

The audit requires a completed, in-scope brain ExecutionReceipt under
`.tasks/receipts/<run-id>.json`, linked to exact persisted spec bytes.
A current-chat chair does not waive local CLI evidence. There is no `waiver`
action.

Present the feature list, complete inventory map, proposed brain configuration
and receipt UUID, first task/provider/tier, and any degraded bindings or assumptions.
Do not dispatch workers before the human approves the feature list and bind map.

## 5. Freeze the approved map and transition explicitly

After approval, prepare `.tasks/gate0-bindings.json` from the approved seats.
Each output seat maps to:

```json
{"inventory_seat":"<inventory key>","effort":"<approved effort>","speed":"<approved speed>"}
```

The output `brain` may select inventory `brain`, `brain_codex`, or
`brain_fable` according to the human's chair choice. Do not re-probe between
approval and freezing. Set APPROVED_BY and the RFC3339 APPROVED_AT timestamp
from the actual verdict.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/fleet_state.py freeze \
  --mission-dir "$MISSION" --inventory .tasks/fleet-inventory.json \
  --bindings .tasks/gate0-bindings.json \
  --approved-by "$APPROVED_BY" --approved-at "$APPROVED_AT"
PYTHONDONTWRITEBYTECODE=1 python3 scripts/fleet_state.py validate-fleet "$MISSION/fleet.json"
```

This creates canonical immutable `fleet.json`; it cannot overwrite an existing
snapshot. Log the Human Gate 0 verdict, exact bindings, and brain UUID in
PROGRESS.md. Set status `approved` and commit.

Before first dispatch, explicitly transition to `in-progress`, run the mission
audit, and commit the transition. The wrapper does not promote `approved`.
Then use dispatch-worker with explicit tier, feature, attempt, effort, and speed.

## Never

- Never invent mission formats or use root-level mission files.
- Never hide degraded inventory or skip the human bind-map approval.
- Never dispatch from a mutable inventory, task override, or GOAL narrative.
- Never rewrite an approved fleet to repair a failed dispatch.
- Never use a waiver or legacy receipt as current CLI proof.
- Never let workers edit features.json or accept their own work.
- Never advance a gate/status without current mission audit evidence.
