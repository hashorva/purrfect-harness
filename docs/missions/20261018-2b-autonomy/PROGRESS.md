---
note: Append-only. Newest entry on top. One entry per worker session or human gate. Hand-written by the orchestrator until F004 is accepted; from then on generated from progress.jsonl.
---

# Progress

## Current status (2026-10-18)

- **Mission:** 2B The Dark Factory, status: draft (GOAL.md), owner: Zamir. Waiting for GATE 0.
- **Features:** F000–F012, all `passes: false`, all `bootstrap: false`; `run_order` F000, F001, F002, F004, F003, F005, F006, F007, F008–F012; each `priority` equals its `run_order` index.
- **Fleet:** `fleet.json` frozen (schema_version 2, 13 seats, approved 2026-10-18T15:21:39Z by Zamir); a fresh inventory at 2026-10-18T15:48:51Z resolves every seat to its frozen binding (map below).
- **Dispatch:** none. No worker has run for 2B.

## 2026-10-18 — Brain (claude / Opus, high) — GATE 0 package check

- **Did:** Checked the Gate 0 package for the owner: GOAL.md, features.json, fleet-proposal.md, estimates.md, tasks/T-001.md and the planner's F000 tasks T-010..T-016. Ran a fresh `bash scripts/fleet-doctor.sh` (exit 0: claude, codex, cursor and agy identity and login OK) and `bash scripts/fleet-inventory.sh` (exit 0), then resolved every frozen seat against that inventory. The map is committed as `evidence/fleet-inventory-gate0.json`. Started this PROGRESS.md. No worker was dispatched and the status stays `draft`.
- **Fleet inventory map (fresh probe 2026-10-18T15:48:51Z; every seat matches its frozen `approved_resolution`):**

  | Seat | Door | Model | Effort | Source |
  | --- | --- | --- | --- | --- |
  | brain | claude | opus | high | alias |
  | brain_argon | agy-argon | gemini-4-argon-high | high | observed |
  | brain_codex | codex | gpt-6.1-sol | high | observed |
  | claude.economy | claude | haiku | medium | alias |
  | claude.mid | claude | sonnet | medium | alias |
  | claude.premium | claude | opus | medium | alias |
  | codex.economy | codex | gpt-6-luna | medium | observed |
  | codex.mid | codex | gpt-5.6-terra | medium | observed |
  | codex.premium | codex | gpt-6.1-sol | medium | observed |
  | cursor.economy | cursor-composer | composer-2.5 | medium | observed |
  | cursor.premium | cursor-grok | grok-4.7-medium | medium | observed |
  | agy.economy | agy | gemini-3.8-flash-medium | medium | observed |
  | agy.premium | agy-argon | gemini-4-argon-medium | medium | observed |

  Speed is `unknown` on the claude, codex and agy seats and `standard` on the cursor seats. The inventory lists models outside the frozen seats (for example, Claude and GPT models behind the cursor and agy doors). They stay unbound, as native-only requires.
- **Verified:** features.json parses. The ids are F000–F012 with no gaps, `run_order` covers every id once, each `priority` equals its `run_order` index, and every feature has `passes: false` and `bootstrap: false`. `fleet_state.py validate-fleet` exits 0 and `validate-inventory` exits 0 on the fresh probe. The brain receipt for this run is written by the runner when the run ends, so `verify-mission.sh` can only pass after this run. Before that it reports "no completed, in-scope brain ExecutionReceipt", as expected.
- **Commits:** this entry and `evidence/fleet-inventory-gate0.json`.
- **Blocked / handoff notes:** These need an owner decision at Gate 0:
  1. **Seat lines in T-001 and T-010..T-016.** Each one says "any usable economy (or premium) seat", which includes `claude.economy` and `claude.premium`. GOAL says guard tasks never go to a Claude worker, and no Claude worker is dispatched while F012 is open (risk 3, F003 step 5). Until the loop enforces this, the Front Desk must leave the Claude seats out by hand. Another option is a planner rerun that names the non-Claude seats.
  2. **Task ids and the size cap.** The F000 tasks are numbered T-010..T-016, but GOAL says "from T-003 on". There are seven files, but a planner run writes at most 3. They were written before Gate 0, and GOAL says the first planner run after Gate 0 writes them. Rule 6 (the oracle fails on the base and passes after the reference patch, run in a scratch clone) has not been recorded for any of them. Approve them as they are, or have the first planner run after Gate 0 redo them.
  3. Gate 0 decisions 1–10 in GOAL.md are still open. After approval, record a **Human — GATE 0** entry here, set `status: approved`, then commit `in-progress` before the first dispatch.
