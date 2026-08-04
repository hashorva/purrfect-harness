---
name: mission-init
description: >
  Bootstrap an orchestrated mission: create a dated folder under docs/missions/
  with GOAL.md, features.json, PROGRESS.md, and the first WORKER_TASK from the
  repo's templates. MUST be used whenever the user says "start a mission",
  "new goal", "bootstrap the loop", "let's run the orchestration on X", or asks
  to begin orchestrated work of any kind. Also use to re-scope an existing
  mission. Produces files mechanically from docs/missions/templates/ — never
  freestyle the formats. Runs fleet-inventory at GATE 0 and always shows the
  seat→model map for human confirm/swap. Default chair is Opus (Cursor intake
  plans briefly; Opus weighs and orchestrates) unless the human names otherwise.
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
- Load `docs/missions/MODEL_ROUTING.md` once for this GATE 0 decision.

## Chair resolution (before writing files)

Default brain = **Opus**. Exceptions (human must say, or session already is):

| Signal | Chair |
|---|---|
| Already on Opus (Claude Code **or** Cursor UI) | This session |
| “You are the orchestrator” / “no handoff” | Current model |
| “No orchestration — just execute” | STOP mission-init; implement in chat |
| “Orchestrator = Fable” | Fable (**named only** — never auto-escalate) |
| “Orchestrator = Codex highest” / Sol | Inventory `brain_codex` / family `sol` |

**Cursor intake:** if a brief plan exists in a Cursor (often Grok) chat, Opus
reads it, weighs whether the split looks balanced, then continues mission-init.
Do not treat the intake chat as the orchestrator unless named above.

## Step 0b — Local CLI inventory (mandatory)

```bash
command -v claude; command -v codex; command -v agent; command -v agy
bash scripts/fleet-inventory.sh
```

Always present the printed seat→model map at GATE 0. Human may remap any seat
(economy ↔ premium, or brain) before approval. Copy approved binds into GOAL
Fleet. Missing a CLI → strike that row; do not invent invocations.

## Step 1 — Extract the mission (interview only if needed)

From the user's paragraph (and any Cursor intake brief), determine: outcome,
forcing function, out-of-scope, human gates, chair (above), fleet tier
(economy | premium | mixed). Slug: `YYYYMMDD-short-kebab-name`. At most 3
clarifying questions. Do not write files until the outcome is unambiguous.

## Step 2 — Write the mission folder FROM TEMPLATES

```bash
SLUG="{{YYYYMMDD-short-name}}"
MISSION="docs/missions/$SLUG"
mkdir -p "$MISSION/tasks"
cp docs/missions/templates/GOAL.template.md "$MISSION/GOAL.md"
cp docs/missions/templates/features.template.json "$MISSION/features.json"
cp docs/missions/templates/PROGRESS.template.md "$MISSION/PROGRESS.md"
cp docs/missions/templates/WORKER_TASK.template.md "$MISSION/tasks/T-001.md"
```

Fill placeholders. Set `status: draft`. Paste inventory binds into Fleet.
Validate: `python3 -c "import json; json.load(open('$MISSION/features.json'))"`.
Only create `tasks/T-001.md` at init (later tasks after reviews).

### `"bootstrap"` — set it at authoring time, never after

Every feature carries a `"bootstrap"` boolean. It is **not** cosmetic:
`verify-mission.sh` requires a worker receipt for each `passes: true` feature
**unless** that feature is `"bootstrap": true`.

- **`false` (the default)** — anything a worker will implement. Needs a receipt.
- **`true`** — features **no worker will ever run**: orchestrator-authored `AGENTS.md`
  and docs edits, mission scaffolding, decisions recorded by the brain.

**Keep the field on every feature you author.** The template ships it as `false` on each
entry; when you write a real `features.json` it is tempting to drop it as noise. Don't —
a missing field is not `true`, but it does mean the mission's own record no longer says
whether a receipt was ever expected.

Getting this wrong is quiet, not loud. A `passes: true` orchestrator-only feature with no
`bootstrap` flag makes `verify-mission` fall back to accepting *any* worker receipt and
emit only a WARN, so the mission goes green on a receipt that belongs to a different
feature. That has already happened once in a real mission.

**Decide it when you write the feature, not when the gate complains.** Adding
`"bootstrap": true` after GATE 0 is an edit to an approved feature — the one thing
`features.json`'s own rules forbid — so the honest fix at that point is to flag it and
carry it to the next mission, which costs a whole cycle.

## Step 3 — GATE 0 (mandatory stop)

**Brain CLI proof (mandatory unless human names current-chat chair):**

```bash
bash scripts/fleet-inventory.sh
bash scripts/spawn-brain.sh "$MISSION" mission-init   # real claude --model opus
# If human said "you are the orchestrator" / already on Opus in this chat:
#   bash scripts/spawn-brain.sh "$MISSION" waiver --reason "already on Opus in Cursor"
bash scripts/verify-mission.sh "$MISSION"             # must pass before greenlight
```

PROGRESS prose is not proof. Greenlight = `.tasks/receipts/brain-*.json` with
`exit: 0` and `cli: claude` (or documented `waiver`).

Present:

1. Feature list (id + description + priority)
2. **Full fleet inventory map** (seat / CLI / model / family) — confirm or swap
3. Resolved brain + concrete model + **brain receipt path**
4. T-001 worker + tier (premium Grok vs economy Composer for Cursor, etc.)
5. Assumptions

DO NOT dispatch until the human approves the features **and** the bind map
**and** `verify-mission.sh` is green for brain.

On approval:
1. Append Human — GATE 0 PROGRESS entry (include approved binds + receipt path).
2. Set GOAL `status: approved` → `in-progress` on first spawn.
3. Follow `.agents/skills/dispatch-worker/SKILL.md` with
   `scripts/spawn-worker.sh … --tier … --feature F00X`.

## Never

- Never invent file formats — templates only.
- Never write features AGENTS.md forbids.
- Never auto-escalate to Fable.
- Never put mission files at repo root.
- Never skip showing the inventory map at GATE 0.
- Never flip `passes: true` or `status: done` without `bash scripts/verify-mission.sh` green.
- Never claim Claude/Cursor CLI ran without a matching `.tasks/receipts/*.json`.
- Never implement allow-listed worker files in the orchestrator chat when spawn-worker is available.
