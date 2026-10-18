---
title: Model Routing Policy
version: 3.1.0
updated: 2026-10-18
---

<!-- markdownlint-disable MD025 -->

# Model Routing — the right brain for each task

> Mission-scoped. Load at GATE 0 / when advancing a mission — not on every
> casual coding session. Lives only under `docs/missions/`.

**Policy one-liner:** Opus chairs by default (or the current chat if it’s already
Opus / you name the chair). Cursor workers: Grok premium, Composer economy.
Concrete slugs come from a probed fleet inventory at GATE 0; families in this
file are durable. Always show the map at GATE 0 so the human can swap binds.

## Native-only (owner 2026-10-18)

- Every model runs only on its own vendor's quota: claude (Opus, Sonnet, Haiku),
  codex (Sol, Terra, Luna), agy (Argon, Flash), cursor (Composer and Grok, one
  Cursor pool).
- A door never serves another vendor's model. Models that agy lists from other
  vendors are never bound.
- `freeze-v2` refuses a foreign door and `resolve_v2` skips one.
- A move to another vendor is an explicit choice of another approved native seat,
  never a door fallback.

| Role | claude | codex | agy | cursor |
| --- | --- | --- | --- | --- |
| Brain and planning (up to high) | Opus high (`brain`) | Sol high (`brain_codex`) | Argon high (`brain_argon`) | none |
| Review (up to medium) | Opus medium (`claude.premium`; Sonnet medium is the swap) | Sol medium (`codex.premium`) | Argon medium, or low when agy lists no medium (`agy.premium`) | Grok medium (`cursor.premium`) |
| Worker (medium, economy seats) | Haiku (`claude.economy`) | Luna (`codex.economy`) | Flash (`agy.economy`) | Composer (`cursor.economy`) |

- Opus is the brain. When Claude has no quota, use Argon or Sol on their own
  quota, through `bash scripts/spawn-brain.sh <mission> review --seat brain_argon`,
  then `--seat brain_codex`.
- The reviewer is on a different vendor than the worker where possible.
- Opus medium reviews dispatch, verification, acceptance, safety and privacy code.

These family labels describe routing preferences, not current vendor availability
or pricing. The probed inventory reports the models this machine can bind.

## Durable seats (names rot; seats don’t)

| Seat             | Job                                                                          |
| ---------------- | ---------------------------------------------------------------------------- |
| `brain`          | Orchestrator — plans mission, writes features/tasks, reviews, accepts verified runs |
| `worker.premium` | Judgment-heavy implementation                                                |
| `worker.economy` | Volume / tight / safely delegable work                                       |

Concrete model IDs are **proposed** by `scripts/fleet-inventory.sh` into families
(`opus`, `fable`, `sol`, `grok`, `composer`, `terra`, `luna`, `sonnet`, `haiku`, …).
GATE 0 always prints the bind map; the human may remap any seat before dispatch.
Binds freeze as canonical mission `fleet.json` after human approval. Re-probing
the local inventory cannot change an active mission's authorization.

## Who chairs (`brain`)

| Situation                                        | Chair                                                |
| ------------------------------------------------ | ---------------------------------------------------- |
| **Default**                                      | **Opus** on Claude Code (claude quota)               |
| Already chatting with Opus                       | This session is the chair (no handoff)               |
| Human: “you are the orchestrator” / “no handoff” | Current model chairs                                 |
| Human: “no orchestration — just execute”         | Skip mission loop; current chat implements           |
| Human: “orchestrator = Fable”                    | Fable (**named only** — never auto-escalate; costly) |
| Human: “orchestrator = Codex highest” / Sol      | Inventory’s top Codex bind (family `sol`)            |

### Cursor → Opus handoff (default intake)

1. Human + Cursor (often Grok) sketch a brief plan in chat.
2. Opus reads that plan, weighs whether the split looks balanced/correct.
3. Opus runs `mission-init` → GOAL / features / fleet / GATE 0 (shows inventory map).

Cursor is **intake**, not the default orchestrator — unless the human names this
chat as chair or the session is already Opus.

## The four routing criteria (apply in order)

1. **Task horizon.** Short + well-scoped → cheapest seat wins. Long chains → brain / premium.
2. **Cost of a silent error.** Caught in review → economy fine. Ships unattended → premium / brain.
3. **Verifiability.** Tests exist → economy + verify beats premium without tests.
4. **Volume.** High volume → always economy.

Rule of thumb: **judgment up, volume down.**

## Worker families (Gate 0 preferences; frozen fleet authorizes dispatch)

### Cursor (`cursor-agent` CLI)

The provider name is `cursor`, and the harness calls the `cursor-agent` binary;
`agent` is a legacy name kept for frozen fleets and v3 evidence, and the launcher
converts `cursor` to it. Grok Build also installs a bare `agent`, and on a machine
with both, `agent` can start Grok Build. Run `cursor-agent login` with the account the Cursor app uses.

| Seat    | Family                                      | Fallback                                       |
| ------- | ------------------------------------------- | ---------------------------------------------- |
| Premium | **Grok** (prefer highest non-`-fast` match) | Composer if Grok off / unavailable / no tokens |
| Economy | **Composer**                                | —                                              |

Orchestrators should delegate small, safe tasks to Composer (economy), not burn
Grok on boilerplate.

### Codex (`codex` CLI)

Seats are **inventory-classified** (names may change). Today’s families:

| Seat               | Family (typical)               | Notes                            |
| ------------------ | ------------------------------ | -------------------------------- |
| Brain (when named) | `sol`                          | Highest Codex / frontier agentic |
| Premium worker     | `terra` (or inventory premium) | Everyday strong implement        |
| Economy worker     | `luna` (or inventory economy)  | Fast / affordable                |

If the human asks “Sol as brain, Terra premium, Luna economy,” the inventory
must bind those families for real and GATE 0 must show them for confirm/swap.

### Antigravity (`agy`) — first-class, especially UI

Not a leftover. Use studio Antigravity credits when the human asks for `agy`,
or when the task is **UI / shadcn / Luma / appearance / chatbuilding** and agy
is on PATH with a healthy inventory bind.

| Seat    | Family (typical today)                                              | Notes                                          |
| ------- | ------------------------------------------------------------------- | ---------------------------------------------- |
| Premium | **Argon** (e.g. `gemini-4-argon-high`)                              | Heavier UI / multi-file layout                 |
| Economy | Gemini **Flash**-class (e.g. `gemini-*-flash-high`)                 | Fast UI passes, polish, boilerplate components |

**Home-fleet defaults (intake context):**

| You’re working from…                | Default workers                                     | agy                            |
| ----------------------------------- | --------------------------------------------------- | ------------------------------ |
| Cursor                              | Grok premium / Composer economy                     | Opt-in, or prefer for UI tasks |
| Codex                               | Terra premium / Luna economy (Sol = brain if named) | Opt-in, or prefer for UI tasks |
| Explicit “use agy” / GATE 0 UI lane | —                                                   | Primary for those features     |

GATE 0 must list `agy.premium` / `agy.economy` whenever `agy` is present so the
human can assign UI features there and spend those credits on purpose.

Note (F009): In Google AI Pro, agy.premium binds gemini-4-argon on its weekly-only agy-argon pool, agy.economy binds gemini-3.8-flash, and contract 8 encodes agy effort only in the model name over stream-json with stdin closed.

### Claude (Claude Code and `claude -p` workers)

| Seat    | Family / effort                         |
| ------- | --------------------------------------- |
| Brain   | `opus` alias, effort high               |
| Premium | `opus` or `sonnet` alias, effort medium |
| Economy | `haiku` alias, effort medium            |

## Fleet inventory (mandatory at GATE 0)

```bash
bash scripts/fleet-inventory.sh          # print map + write .tasks/fleet-inventory.json
bash scripts/fleet-inventory.sh --json   # JSON only
```

- Probe each CLI on PATH (`claude`, `codex`, `cursor-agent`, `agy`).
- Classify into seats by **family regex**, not hard-pinned version strings.
  Rank by version, then release date, then effort. A preview is below a stable
  release. A `-fast` model is never chosen automatically: fast modes cost more
  and run only when the human asks for them.
- A successful list without a family member gives an `unavailable` seat. The
  probe never guesses an id that the CLI did not list.
- **Always show** the map at GATE 0; human may interchange economy/premium (or
  brain) binds before approval.
- Log the approved binds in PROGRESS.md + the mission GOAL Fleet table, and
  persist them with `scripts/fleet_state.py freeze` as described in mission-init.
  GOAL is narrative; dispatch authority is the immutable mission `fleet.json`.
- Snapshot path `.tasks/fleet-inventory.json` is machine-local (gitignore
  `.tasks/`); do not commit auth-specific lists.
- If a probe fails: retain last-good per-provider state and mark it degraded;
  without retained state, label any policy fallback as degraded. Unavailable
  models cannot be bound. Present health/source explicitly at Gate 0.

**Alias / inventory doctrine:** mid-mission, do not re-bind. Finish on the
approved map; adopt new vendor flagships at the next GATE 0.

## Spawn

Prefer:

```bash
MISSION=$(bash scripts/active-mission.sh)
bash scripts/spawn-worker.sh "$PROVIDER" "$MISSION/tasks/T-XXX.md" \
  --tier "$TIER" --feature F00X --attempt 1 \
  --effort "$APPROVED_EFFORT" --speed "$APPROVED_SPEED"
```

Use the provider/tier/effort/speed from the approved frozen seat. `--model <id>`,
effort, and speed are equality assertions; task frontmatter `invocation:` is
descriptive. None can override `fleet.json`. A fallback is a Gate 0 proposal or
an explicit selection of another already-approved seat, never a silent dispatch
rebind. External `--repo` execution is disabled in Phase 1.
Every seat may be checked before dispatch with `bash scripts/probe-seat.sh <seat>`, runs under the runner's stall and zero-turn guards, and launches Claude with `--strict-mcp-config`; workers never write `PROGRESS.md`.
Interactive CLIs driven by scripts/drive-cli.sh stop with exit 3 on any prompt after an answered trust prompt and on numbered or menu approval prompts; boxed menus and alternate-screen redraws are accepted residuals that end as an exit-4 stall, and no wrong answer is ever sent.

Note (F010): Contract 9 runs every provider with its full native toolset (Claude bypassPermissions with CLAUDE_DISALLOWED_TOOLS and --strict-mcp-config, Codex workspace-write with network and live web search on and cua_repl/node_repl disabled per run, and CLI --help flag baselines tracked by probe-seat.sh).

## Pricing

Consult current vendor pricing and the account's actual subscription when cost
matters. This protocol does not treat an old price table as execution authority.
