---
note: Current state only. Full history is in progress-archive/ (read-only). Newest entry on top; at most 10 lines per entry; full reviewer outputs go to reviews/<run-id>.md. Workers do not write this file; the Front Desk records each run from its receipt.
---

# Progress

- **2026-10-16 — T-045 complete (launcher):** workers no longer write PROGRESS.md; the prompt in `scripts/spawn-worker.sh`, `tests/run-tests.sh` and `tests/test-execution-integration.py` and `WORKER_TASK.template.md` now say the Front Desk records the run from its receipt. Brain prompt untouched.
- Verification: oracle, shellcheck, `tests/test-execution-integration.py` and `tests/run-tests.sh` all exit 0; no bytecode folders. This run's launcher prompt still said to append, so this entry is the one allowed by T-045.
- **2026-10-16 — T-044 complete (privacy near-misses):** case-insensitive sensitive/absolute paths, expanded path roots, Unicode whitespace after Bearer, and U+061C now reject; runtime near-miss and rule mutation tests added.
- Verification: Oracle G passed (23 hostile, 16 legitimate, 10 committed rows/fixtures); `tests/test-ledger.py` passed (81); shellcheck, JSON validation, full suite, and bytecode check passed.
- Mutation evidence: `tests/test-ledger.py` exercises every named near-miss mutant, including lookbehind punctuation and relative-path over-refusal; scoped commit f08a615.
## Current status (2026-10-16)
- Mission 2A Foundation, branch `mission/2a-foundation`, status in-progress. Gate 0 passed. **Gate 1 target:** F001–F006 accepted and the deterministic suite green (prepare, do not advance).
- **Accepted:** F001, F003, F005, F006 (F005 with the first ledger fold). **F004** and **F007** wait for the agy amendment (agy dropped from the mission by owner decision; T-026 and T-039 deferred).
- Full history before this reset: `progress-archive/2026-10-14_15.md` (717 KB, kept verbatim). Routing data: `routing-data.jsonl`. Receipts/records: `.tasks/receipts/`, `verification/`.
- Seats: usable claude.economy, claude.premium, codex.economy, codex.premium, cursor.economy, **cursor.premium** (re-frozen grok-4.7-high/high/standard, smoke passed 2026-10-16); **agy.economy unusable** (every turn hangs; evidence in the archive, entry "day 3 / agy re-smoke").

## Owner decisions in force (2026-10-16 message)
1. Order: archive PROGRESS.md; accept F003 and F006; re-freeze cursor.premium to grok-4.7-high standard (drift event); ledger task (Architect review) then fold + accept F005; two small tasks (verifier: a skipped check is a failure; privacy near misses); drop agy (amend F004/F007, defer T-026/T-039, T-037 uses claude, codex, cursor); stop at Gate 1 prepared.
2. Reviews: guard/safety/privacy changes -> Claude Opus (brain). Routine diffs -> grok-4.7-high via cursor.premium (replaces the code-reviewer subagent). Calibration: for the next 3 guard reviews run grok-4.7-high first, then Opus, and record in `routing-data.jsonl` whether grok found the same blocking issues.
3. Process rule for every task writer (Front Desk included): before committing a task, run its verification commands in a scratch clone; they must fail on the base and pass after a scripted application of the intended edit.
4. Parallel dispatch stays in 2B (option A). Lesson candidates accepted as candidates.
5. Workers no longer write PROGRESS.md; the Front Desk records each run from its receipt (task-template and launcher prompt change to follow).

## Open decisions / waiting on the owner
- Proposal `docs/proposals/20261016-structured-progress.md` (progress.jsonl + progress.py + generated PROGRESS.md): to be written by the Architect; owner decides whether it starts 2B or is pulled into 2A.
- Gate 1 verdict (after F001–F006 accepted).

## Active lessons (candidates; none promoted through skillify)
- State why a check exists, not only its rule. Run a long check once; never start a duplicate.
- Tests never mutate the live tree; verification must not depend on it (clean worktree).
- CLI login state is invisible in the Codex sandbox; known seat limits belong in the registry.
- A task that adds a test also wires it into `tests/run-tests.sh`.
- Worker PROGRESS narratives are not evidence; receipts and records are (the receipt decides attribution).
- Negative tests: assert the specific refusal at the real entry point, one test per pattern in a pattern list, name the exact field path; a mutation must make the entry point admit the violation.
- A guard-mutation oracle must reject every compile error; near-miss patterns for sandbox-mount decisions; re-run narrower rules' mutation proofs when a broader rule is added.
- Reproduce a failure on the unfixed tree before filing a fix; a task item that names a value must name its field; a follow-up that loosens a gate goes to the Architect.
- A subset validator must validate the shape of every keyword value and recurse into every schema-valued keyword; every guard on untrusted input must cover every branch; a skip-ahead scanner needs an adjacent-character test; mutation proofs listed per test as file:line:expression.
- Any CLI that takes a run id validates it as a canonical UUID first, with a hostile-id/symlink test at the entry point.
- The Front Desk writes nothing into the repository while a worker or Architect run is in progress.

## Recent entries (newest first)
- **2026-10-16 — REAL F007 SMOKE RAN (exit 0) — one finding: Codex reports no model, so F007 step 2 is not met as written** Smoke (scratch clone `.tasks/smoke/f007/repo`, base 7088dfec): 4 workers completed — claude.economy (observed model claude-haiku-5-5), codex.economy (gpt-6-luna requested; observed model **unknown**: Codex's JSON output has usage but no model), cursor.economy (Composer 2.5), cursor.premium (Grok 4.7 256K High, grok-4.7-high standard) — and one brain run (claude-opus-5-5) completed; all four VerificationRecords pass, ledger rows valid, audit exit 0, reconstruct exit 0. No fast model, no credits door.
  **Decision for you:** F007 step 2 says every non-cursor run has a non-unknown observed model. Options: (a) amend the step to "claude and the brain are observed; codex and cursor may stay unknown (Codex JSON carries no model)"; (b) a task to read Codex's own session record after the run (observed, from the CLI's records); (c) leave F007 unaccepted. I will not claim step 2 as met. T-038 (evidence file) is revised so its check validates the source flags only and its text must state the Codex gap plainly.
- **2026-10-16 — T-037 chain closed: T-037-R1 re-reviewed by Opus PASS (B1 closed); real F007 smoke (T-038 step H-1) next** Opus run 0ce9af26-5d3e-4287-a8f5-affceefb031c: D1 reproduced on the old script, fixed at 35718af; all 25 seat-smoke tests pass; mutating the late check at scripts/seat_smoke.py:498 fails the new test. Running `fleet-doctor.sh --smoke --f007 --keep` on this Mac now: 4 tiny worker runs (claude.economy, codex.economy, cursor.economy, cursor.premium grok-4.7-high, no fast, no credits) plus one brain run (claude opus) in a scratch clone.
- **2026-10-16 — T-037-R1 re-reviewed by Opus (brain run 0ce9af26-5d3e-4287-a8f5-affceefb031c, commit 35718af, worker run a46c63a8-…): PASS, B1 closed** Log `.tasks/logs/0ce9af26-5d3e-4287-a8f5-affceefb031c.log`. Scratch clone, fake CLIs only, PYTHONDONTWRITEBYTECODE=1.
  D1: with the old script (639250b) and the new test, a brain that writes the live TRACKED.txt leaves the smoke at exit 0 (test fails). At 35718af: exit 1 with `live tree changed during seat smoke`. Happy path and all 25 seat-smoke tests pass (6 F007).
  Mutant: late check at `scripts/seat_smoke.py:498` disabled (`if False and …`) → new test fails. Diff is only the two lines, the fake-brain `live-touch` mode and the one test; no files outside the allow-list. Clean tree, no bytecode.
  Non-blocking: the late check runs on both paths (F007 and plain), which is correct. Not run here: shellcheck and the full suite (the verifier already ran them).
  Verdict: PASS
- **2026-10-16 — T-037-R1 verified (run a46c63a8-4fe8-429f-bbd1-c000e15681a5, claude.economy, commit 35718af); short Opus re-review requested** VERIFY PASS (oracle, seat-smoke tests, shellcheck, full suite, clean tree, no bytecode).
  **ARCHITECT RE-REVIEW REQUEST, T-037-R1 (commit 35718af), SHORT and limited to your blocking issue B1.** Reproduce D1 (a fake brain that writes the live TRACKED.txt) on this tree: the smoke must now exit 1 with `live tree changed during seat smoke`; check the happy path still exits 0; mutate the new late check once and show the new test fails; confirm the diff is only the two lines plus the fake-brain mode and the test. Fake CLIs only, scratch clones, PYTHONDONTWRITEBYTECODE=1. PROGRESS entry at most 6 lines. End with Verdict: PASS or FAIL.
- **2026-10-16 — T-037 reviewed by Opus: FAIL (one blocking: live-tree check before the brain step); T-037-R1 written, rule 6 checked, dispatched on claude.economy** Opus run e515632d-bd49-42b3-af50-b71e654512e6: confirmed by effect four seats in order + one brain, no agy, refusals before creation, no fast/credits, no remote; B1: a brain that writes the live tree leaves the smoke at exit 0. Mutants 7 of 15 killed (survivors are gates that back each other up; non-blocking). Its verdict validated against `schemas/review-verdict.schema.json`.
  T-037-R1 = two lines + a brain live-touch test; rule 6: the oracle fails on base and passes after; suite passes after (395 s).
- **2026-10-16 — T-037 reviewed by Opus (brain run e515632d-bd49-42b3-af50-b71e654512e6, commit 639250b, worker run 5131b318-…): FAIL, 1 blocking** Log `.tasks/logs/e515632d-bd49-42b3-af50-b71e654512e6.log`; full text in its `=== FILE: reviews/e515632d-bd49-42b3-af50-b71e654512e6.md ===` block. Fake …
  Full text: `reviews/entry-42bc837c.md`.
- **2026-10-16 — T-037 verified (run 5131b318-bc47-4380-9513-0449ceb8e147, cursor.economy, commit 639250b); Opus review requested** VERIFY PASS (9 commands: 3 oracles, seat-smoke and reconstruct tests, shellcheck, the full suite, clean tree, no bytecode).
  Full text: `reviews/entry-ce35184c.md`.
- **2026-10-16 — T-037 rule 6 re-checked by the Front Desk (3 oracle commands fail on base and pass after; suite passes after, 384 s); dispatch on cursor.economy**
- **2026-10-16 — Architect T-037 revision received (run 204f6de4-89d4-4765-bf2c-d5ebd7462fa3): 3 doors / 4 runs + 1 brain; Front Desk re-runs rule 6** Task text copied to tasks/T-037.md, mutants to reviews/, patch (sha 50fec781…) kept outside the tree. Architect result: 3 oracles fail on base and pass after; full suite passes after; mutants 6 of 8 killed (the two survivors are non-blocking). Old defects fixed: `reconstruct --all` picked up the brain receipt; an exit-code check passed on the base. Checks 2, 3 (fleet-doctor.sh) and 7 (suite) run only in the verifier.
- **2026-10-16 — Architect (Opus brain run 204f6de4-89d4-4765-bf2c-d5ebd7462fa3): T-037 revised for 3 doors / 4 runs + 1 brain; rule 6 checked incl. full suite; reference patch built** Log `.tasks/logs/204f6de4-89d4-4765-bf2c-d5ebd7462fa3.log`. The `=== FILE: tasks/T-037.md ===` and `=== FILE: revie …
  Full text: `reviews/entry-8a0022cd.md`.
