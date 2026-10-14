---
note: Append-only. Newest entry on top. One entry per worker session or human gate.
---

# Progress

## 2026-10-14 — T-001-R1 worker — complete; awaiting orchestrator verification

- **Checked:** every `tests/test-*.py` file and `tests/run-tests.sh` for filesystem writes, copies, deletes and permission changes. The integration tests' mutations target their temporary fixture repositories; `tests/test-verification-record.py` was the live-tree writer. Its guard mutation now runs against a temporary copy of `scripts/`, `tests/`, `schemas/` and `docs/missions/templates/`, removed by `TemporaryDirectory` even on failure. No other live-tree writes were found.
- **Changed:** `tests/test-verification-record.py` to isolate the guard mutation while preserving the real focused test entry-point assertion; `docs/missions/templates/WORKER_TASK.template.md` to include the required long-command rule in Iteration policy.
- **Baseline:** shellcheck, manifest/features JSON validation and `python3 tests/test-fleet-state.py` all exit 0.
- **Checks:** `python3 tests/test-verification-record.py` exit 0 (12 tests); two concurrent copies of each `tests/test-*.py` completed without failure; `bash tests/run-tests.sh` exit 0 (`ALL TESTS PASSED`). The shipped template rendered and verified through the full suite. `git diff --check` exit 0. The test runs left no changes beyond the two intended files before this progress entry.
- **Result:** no feature acceptance or mission gate/status change. Scoped change and this entry committed as `test: mutate a temporary copy, never the live tree`.

## 2026-10-14 — T-001 worker — blocked at baseline

- **Did:** read the task, mission instructions, newest progress, features, fleet-state constants and manifest; inspected `git log --oneline -10`.
- **Baseline:** `bash tests/run-tests.sh` exit 1 before any implementation edits. The failing check reported `VerificationRecord and acceptance real-entry contracts`; remaining output was truncated by the command tool, so no further failure detail is available.
- **Result:** stopped as required by T-001's pre-code baseline rule. No registry files, manifest ownership, or acceptance/gate state changed. Retry requires baseline repair and redispatch.

## 2026-10-14 — Front Desk (Sonnet 5.5) — T-001 attempt 1 diagnosed; T-001-R1 written

- **Diagnosis (proven):** not a sandbox limit. The suite passes under `codex sandbox -P :workspace` (test file 12/12 in 68s, full suite 149s). The worker started a second copy of the suite while the first was still running; `tests/test-verification-record.py` (line 285) edits the live `scripts/verification_record.py` to mutate guards, so the concurrent copy saw a broken guard. Reproduced: two concurrent copies, one fails with 3 failures, first at `test_required_guard_mutations_break_the_real_focused_entry_and_restore`, `AssertionError ... not found` at line 320. Tree clean afterwards.
- **Owner-approved fix:** T-001-R1 (feature F001, `codex.economy`): grep all tests for live-tree writes, make mutations happen in a temporary copy, add the long-command rule to the worker template's Iteration policy. Checks: two concurrent copies of every `tests/test-*.py` exit 0; `git status --short` empty; `bash tests/run-tests.sh` exit 0 (once).
- **T-001 attempt 2:** only after R1 is accepted. Its baseline becomes shellcheck, JSON validation and `python3 tests/test-fleet-state.py`; `python3 tests/test-registry.py` is a T-001 check, not a baseline; the full suite stays in its verification commands. T-001 text is updated then.
- **L-002 candidate:** run a long check once; never launch a duplicate while it runs. (Replaces the earlier sandbox guess; no L-002 text was ever written to this file.)
- **L-003 candidate:** tests must never mutate the live tree; mutate a temp copy.

## 2026-10-14 — Front Desk (Sonnet 5.5) — status in-progress

- **Did:** moved `approved` → `in-progress`. `verify-mission.sh` exit 0 on the in-progress mission. Dispatching T-001 (F001, codex.economy, attempt 1) next.

## 2026-10-14 — Front Desk (Sonnet 5.5) — fleet frozen, status approved

- **Fleet:** `fleet.json` frozen from the inventory probed 2026-10-14T15:00:44Z, approved by Zamir at 2026-10-14T15:25:56Z. `validate-fleet` exit 0. No re-probe between approval and freeze.
- **Seats:** brain = claude / opus (alias), effort high. cursor.premium = grok-4.7-xhigh; cursor.economy = composer-2.5 (effort medium, speed standard). codex.premium = gpt-5.6-terra; codex.economy = gpt-6-luna. agy.economy = gemini-3.8-flash-high. claude.premium = sonnet; claude.economy = haiku (alias, effort medium). Not bound: agy.premium (unavailable), brain_codex, brain_fable.
- **Brain evidence:** run `ec402a2f-6830-425a-b932-88332b044933`, receipt `.tasks/receipts/ec402a2f-6830-425a-b932-88332b044933.json`; `verify-mission.sh` exit 0 before this entry.
- **Status:** `approved`.

## 2026-10-14 — Human — GATE 0 (chair option 2)

- **Verdict:** option 2 approved: freeze now with the brain on `claude` / `opus`, effort high.
- **Chair intent:** Opus via agy (Google AI Pro pool). Interim: Opus via claude, because the v3 brain seat cannot carry an agy model. Switch to agy Opus when F001 (registry lets agy carry an Opus seat) and F004 (logged mid-mission change) are both accepted; the switch is a logged drift event, not a fleet rewrite.
- **Change:** F004 gets the step "the chair seat can resolve to agy claude-opus-5-5-high, and the change is logged as a drift event." (draft-stage edit, before freeze).
- **Assumption (Front Desk):** worker seats frozen at effort `medium`, as in Phase 1; speed `standard` for cursor, `unknown` elsewhere. Say so if you want other values before dispatch beyond T-001.

## 2026-10-14 — Human — GATE 0

- **Verdict:** approved with changes (recorded by Front Desk from the owner's message).
- **Scope:** F002 (Grok Build provider) removed; ids not renumbered. Grok runs through `cursor-agent`. F007 smoke uses claude, codex, cursor-agent (Composer and Grok) and agy. Dependent steps in F001, F003, F004, F005, F007 were aligned in the same draft-stage edit.
- **Findings recorded:** `cursor-agent` JSON gives usage and `session_id` but no model, so observed model is `unknown` unless stream-json init reports it. Grok Build headless: `acceptEdits` cancelled both file and shell tool calls. Deferred experiment X-GROK: Grok via `grok` against via `cursor-agent`, measured in the ledger on spare quota.
- **Decisions:** (1) chair Opus 5.5, effort high, via `agy` model `claude-opus-5-5-high`; fall back to `claude` / `opus` only if the first agy brain run fails to launch, and record why. (2) Frozen-fleet amendment approved: a probe may change an active mission, never silently. (3) Phase 1 non-goals lifted for Phase 2; 2A uses none. (4) Budgets: per spawn 40 min; per night max 12 worker + 4 Architect runs; per pool stop at an estimated 80% of a 5-hour window or 70% of the weekly cap; never credits, never fast modes.
- **Architect questions:** (1) each run writes `.tasks/ledger/<run_id>.json` (gitignored); the orchestrator folds rows into `docs/missions/ledger.jsonl` in each acceptance commit and at gates. (2) Terra premium, Luna economy; tier follows family, not version. (3) FALLBACKS copied unchanged in T-001, deleted in F004.
- **Approved:** T-001 on codex.economy (Luna).
- **Next:** blocked before freeze. The `brain` seat is fixed to `claude`/`opus` in `scripts/fleet_state.py` (`SEAT_SPECS`); `freeze` accepts only `brain`, `brain_codex` or `brain_fable` and checks provider/family match. An `agy` Opus brain cannot be frozen with the current code. Status stays `draft` until the owner decides.

## 2026-10-14 — Brain (claude/opus, effort high) — mission-init

- **Run:** `ec402a2f-6830-425a-b932-88332b044933`; log `.tasks/logs/ec402a2f-6830-425a-b932-88332b044933.log`. The launcher writes the receipt `.tasks/receipts/ec402a2f-6830-425a-b932-88332b044933.json` when this run ends; it did not exist while this entry was written.
- **Checked:** GOAL.md, features.json, PROGRESS.md and tasks/T-001.md exist, match the templates, and have no `{{` placeholders. GOAL status stays `draft`. `active-mission.sh` reports no active mission (exit 1, expected for a draft).
- **Baseline (base `cef58cc`):** `shellcheck scripts/*.sh tests/*.sh` exit 0; JSON validation of the manifest and features.json exit 0; `bash tests/run-tests.sh` exit 0.
- **Inventory:** no re-probe. `.tasks/fleet-inventory.json` (probed 2026-10-14T15:00:44Z) matches the GOAL Fleet table seat for seat. `grok` is on PATH but not in the inventory (F002).
- **Architect edits (features.json, ids and scope unchanged, all `passes:false`/`bootstrap:false`):** made these steps checkable by a command: F001 step 2 (grep for literal definitions, not names that `dispatch_policy.py` still imports), F001 step 5 (marked local-only, kept out of CI), F001 step 7 (exact greps), F002 step 5, F004 step 3 (drift write failure must fail the spawn), F007 step 5 (reconstruct command replaces "a human can rebuild"). Added an F005 step: a committed `ledger.jsonl` row must not break the clean-tree or snapshot-equality checks.
- **Open for Gate 0 (beyond the four proposal decisions):** (a) F005: where and when the ledger row is committed, because appending after a run dirties the tree that the next launch and `verify-mission.sh` require clean; (b) `codex.premium` binds `gpt-5.6-terra` while `codex.economy` binds the newer `gpt-6-luna`, so confirm or swap; (c) the `FALLBACKS` constant (`gpt-5.6-sol`, `cursor-grok-4.5-high`) is older than the observed models; T-001 copies it as-is for parity.
- **First task:** T-001 (F001 slice 1), proposed `codex.economy` (luna). T-001 was committed in `cef58cc`.
- **Not done:** no worker dispatched, no fleet.json frozen, no feature accepted, no status change.

## 2026-10-14 — Front Desk (Sonnet 5.5) — mission-init setup

- **Did:** Created branch `mission/2a-foundation`, committed the Phase 2 proposal (`8cf00ee`), checked the CLIs, ran `fleet-inventory.sh`, scaffolded this draft mission.
- **Step 2:** duplicate PATH entries only; all hits resolve to one binary per CLI (owner accepted).
- **L-001 candidate:** in prompts and tasks, state why a check exists, not only its rule.
- **Inventory:** seats and health are in the Gate 0 report and `GOAL.md`. `claude` seats are alias-sourced (0 models listed). `agy.premium` is unavailable. No `grok` provider yet (feature F002).
- **Blocked / handoff notes:** Architect run (brain) pending. Status stays `draft`. No worker dispatched.
