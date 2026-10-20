---
note: Append-only. Newest entry on top. One entry per worker session or human gate. Hand-written by the orchestrator until F004 is accepted; from then on generated from progress.jsonl.
---

# Progress

## 2026-10-19 — Human — GATE 1

- **Verdict:** approved (owner, in chat 2026-10-19) with three CI jobs (ubuntu 3.12, ubuntu 3.14, macOS 3.14).
- **Notes:** README must declare Python 3.12+ supported and fleet-doctor.sh must fail on an older python3 (task). New owner direction ahead of F001: goal-style harness, event-driven Front Desk, steps 0-4 and 6 (step 5, the phone, is skipped for now).
- **Next:** in-progress.

## BLOCKER / DECISION NEEDED (2026-10-19) — token budget calibration (F013 step 2)
Landed and verified: Gate 1 passed; step 0 audit (2 receipt-backed brain runs, 9 ad hoc planner runs have no saved logs and are marked manual); T-060 audit script, T-061 computed subagent_stats + manual rows ignored + jq cross-check, T-062 README Python 3.12+ and fleet-doctor check, T-063 goal-style principle in prompts/skills/AGENTS/ORCHESTRATION, T-064 runner-enforced budgets (overrun recorded, over 2x stops as budget_exceeded). T-065 (events + gated SubagentStop hook) is committed (7960525) but its run was itself stopped by the new rule: outcome budget_exceeded, so it is NOT verified/accepted; the chain stopped there. T-066..T-068 not started (T-066/T-067 mission-run.sh and T-068 usage report have tasks written).
**The problem (measured from 190 receipts):** token totals that count cache reads (the way every number so far was counted) are far above the budgets: worker runs median 0.5M (cursor), 0.9M (claude), 1.7M (codex), 4.0M (agy), p90 2.4M-8.7M; brain/planning runs 1.3M-6.6M. Budgets of planning 1,000,000 / review 400,000 / workers 150k-800k with a stop at 2x would kill most normal runs. Options: (A) budget counts input+output+reasoning only and excludes cache reads (cache reads are cheap and re-counted per turn); (B) keep counting cache reads and raise the numbers to about p90 of the measured totals (planning 6M, review 2M, workers by size 2M/4M/8M); (C) A for the stop rule and report both numbers. Recommendation: C.
Everything else waits for this decision (T-065 must be re-run once the rule is settled).

## STATUS REPORT (2026-10-20) — chain of T-065..T-080 and T-066..T-068 finished; decisions below
**Done:** T-060..T-064 (audit, computed subagent stats, Python 3.12 check, goal-style principle, budget enforcement, later removed); T-065 accepted as already implemented (7960525); T-065-R1 (test indentation) verified; T-069 (no token caps), T-070 (no budget in prompts), T-071 (per-provider token figures), T-072 (receipt tokens and role tag), T-073 (ledger row fields), T-074 accepted as already implemented (51aa511), T-075 (usage report) accepted with a fixture exception, T-076 (known-failure fixes), T-077 (one safe-git helper), T-078 (every git call uses it), T-079 (failed verification prints argv, exit code and output lines), T-080 (CI status check), T-066 (mission-run core), T-067 (round limit and recovery), T-068 (read-only usage report) accepted with a fixture exception.
**Verified by the verifier:** 10 tasks (T-066, T-067, T-071, T-072, T-073, T-076, T-077, T-078, T-079, T-080). **Accepted by the owner, not by a verifier run:** T-065, T-074, T-075, T-068.
**Receipts (local, all runs, counted by provider, role and outcome):** codex worker completed 115, failed 2, budget_exceeded 1 (before the budget stop was removed); agent (cursor) worker completed 90, failed 1; claude worker completed 28; claude brain completed 66, timed out 4, interrupted 2; codex brain completed 5, failed 2; agy worker completed 9. Token figures per provider and role are in each receipt and ledger row (T-071, T-072).
**Stopped attempts (13 stop events) and their causes:** dirty tree before dispatch (3, fixed: stale bytecode and verifier record commits); scope failures where a worker edited files outside its allow-list (3: T-074 attempt 4, T-077 attempt 1, T-068); a verification gap where the failing test name was cut from the output (fixed by T-079); an allow-list with a trailing slash the dispatcher refuses (T-080, fixed); a worker that made no change because its task was already implemented (T-065, T-074 attempts 5 and 6, accepted).
**Planner errors found (same pattern three times):** T-075 and T-068 oracles read fixtures that were not on their allow-lists; T-074 and T-077 verification commands ran test files outside their allow-lists. Fix in progress: planning must check every path a verification command uses against the allow-list.
**Not done yet:** a real red run to confirm the verifier's failure output (T-079); the phone notification (step 5 skipped per owner); the usage figures for Front Desk tokens per accepted task (T-068 reports them; not yet run on real transcripts for the baseline/after comparison); the 10-run before/after batches for F001.
**Decisions needed:** (1) accept T-065, T-074, T-075 and T-068 as the owner did, or re-run any of them with a real change; (2) run the 2B gate for F001 and F002 next, or take the rest of the list first; (3) whether to keep the phone notification skipped.

## REPORT AT GATE 1 — SAFETY NET (2026-10-19) — stopped for your verdict
**Gate 0:** passed 2026-10-18 (fleet frozen from the proposal after a fresh probe: fleet-doctor no ERROR, fleet-inventory.sh, freeze-v2, validate-fleet ok, all 13 seats incl. claude.mid and codex.mid; Gate 0 brain receipt f97b795d; entry below).
**Runs by seat and class (2B routing-data.jsonl, 27 worker runs):** done: cursor.economy 14, codex.economy 7, agy.economy 1, brain 1. Not done: codex.economy failed (task) 3, cursor.economy verify-failed (task) 1. Failures were all task defects (oracles that read live growing files, a fixture list missing a new module, a fixture line tripping the ledger privacy pattern); each was fixed by a planner retry.
**F000 safety net: ACCEPTED** (T-017 acceptance run; Opus medium strict review: FAIL then PASS after T-018..T-020). Landed: golden argv test with fixtures and a manifest + a git immutability check wired into CI (a changed existing contract fails unless a new contract number is added), the 2A evidence fixture audit in CI, the Python matrix, test discovery by file pattern (no manual list), one shared run-id validator (scripts/run_id.py) with an ast-based scanner, the promoted lessons in AGENTS.md and the skills, 2A PROGRESS.md frozen.
**CI on the gate commit 9ff9a87 (PR #5, draft, not for merge):** green on ubuntu 3.12, ubuntu 3.14 and macOS 3.14. DEVIATION: GATE 1 and F000 step 4 say four jobs (two OS x 3.12 and 3.14); the implemented matrix has no macOS 3.12 job (the macOS runner ships 3.14; Opus accepted the matrix as pinned by tests/test-ci-workflow.py). Your call: accept three jobs or ask for macOS 3.12 via setup-python.
**Also landed for Gate 2 (F001/F002 prep, not yet accepted):** T-001/R1/R2 planning_stats baseline (frozen fixture of the 2A routing data), T-002 subagent field in receipts and ledger rows, T-003 effort-by-role refusals at launch, T-004/R1 batch stats, T-005 goal-style brain prompts with token budgets, T-006 compare tooling, T-007/T-008 seeded-defect replay, T-009 the official planning action `spawn-brain.sh <mission> plan --request FILE` (planner runs now leave receipts and ledger rows), T-050 plan_extract.py, T-051 docs.
**Tokens per planning run (2B, 9 logged ad-hoc planner runs before the plan action existed):** median total 2.23M incl. cache reads (range 0.46M to 6.5M; explorer subagent used in 7 of 9 runs). The 1M target is NOT met yet: the F001 'after' batch must come from planning runs launched through the new plan action, which start now; this is why F001 stays open (Gate 2).
**Quota readings:** estimated only (meter lands in F002). Claude Opus planners and reviews ran all day without a limit; Codex, Cursor and agy Flash workers hit no limits; Argon was not used.
**Features accepted:** F000. **Open:** F001 (needs the after batch of 10 planning runs + seeded-defect replay), F002 and the rest.
**Decisions for you:** (1) GATE 1: approve (and say whether three CI jobs are acceptable). (2) After approval I continue unattended with F001 completion, F002, then F004, F003 to the next gates.

## Current status (2026-10-18)

- **Mission:** 2B The Dark Factory, status: in-progress (GOAL.md), owner: Zamir. Gate 0 passed 2026-10-18.
- **Features:** F000–F012, all `passes: false`, all `bootstrap: false`; `run_order` F000, F001, F002, F004, F003, F005, F006, F007, F008–F012; each `priority` equals its `run_order` index.
- **Fleet:** `fleet.json` frozen (schema_version 2, 13 seats, approved 2026-10-18T15:21:39Z by Zamir); a fresh inventory at 2026-10-18T15:48:51Z resolves every seat to its frozen binding (map below).
- **Dispatch:** none. No worker has run for 2B.

## 2026-10-18 — Human — GATE 0

- **Verdict:** approved (owner, in chat 2026-10-18, with changes).
- **Notes:** changes applied: F000 safety net first; F004 before F003; F001 acceptance measurable; fleet frozen from the proposal after a fresh probe (fleet-doctor no ERROR, fleet-inventory.sh, freeze-v2, validate-fleet ok, mid seats included); lessons promotion, T-010..T-016 planned. Brain Gate 0 receipt f97b795d; `verify-mission.sh` exit 0 before and after.
- **Next:** in-progress. Run order F000, F001, F002, F004, F003, F005, F006, F007, F008..F012; stop at each gate.

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
