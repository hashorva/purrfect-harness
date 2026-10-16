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
- **2026-10-16 — T-037 reviewed by Opus (brain run e515632d-bd49-42b3-af50-b71e654512e6, commit 639250b, worker run 5131b318-…): FAIL, 1 blocking** Log `.tasks/logs/e515632d-bd49-42b3-af50-b71e654512e6.log`; full text in its `=== FILE: reviews/e515632d-bd49-42b3-af50-b71e654512e6.md ===` block. Fake …
  Full text: `reviews/entry-42bc837c.md`.
- **2026-10-16 — T-037 verified (run 5131b318-bc47-4380-9513-0449ceb8e147, cursor.economy, commit 639250b); Opus review requested** VERIFY PASS (9 commands: 3 oracles, seat-smoke and reconstruct tests, shellcheck, the full suite, clean tree, no bytecode).
  Full text: `reviews/entry-ce35184c.md`.
- **2026-10-16 — T-037 rule 6 re-checked by the Front Desk (3 oracle commands fail on base and pass after; suite passes after, 384 s); dispatch on cursor.economy**
- **2026-10-16 — Architect T-037 revision received (run 204f6de4-89d4-4765-bf2c-d5ebd7462fa3): 3 doors / 4 runs + 1 brain; Front Desk re-runs rule 6** Task text copied to tasks/T-037.md, mutants to reviews/, patch (sha 50fec781…) kept outside the tree. Architect result: 3 oracles fail on base and pass after; full suite passes after; mutants 6 of 8 killed (the two survivors are non-blocking). Old defects fixed: `reconstruct --all` picked up the brain receipt; an exit-code check passed on the base. Checks 2, 3 (fleet-doctor.sh) and 7 (suite) run only in the verifier.
- **2026-10-16 — Architect (Opus brain run 204f6de4-89d4-4765-bf2c-d5ebd7462fa3): T-037 revised for 3 doors / 4 runs + 1 brain; rule 6 checked incl. full suite; reference patch built** Log `.tasks/logs/204f6de4-89d4-4765-bf2c-d5ebd7462fa3.log`. The `=== FILE: tasks/T-037.md ===` and `=== FILE: revie …
  Full text: `reviews/entry-8a0022cd.md`.
- **2026-10-16 — ARCHITECT PLANNING RUN T-037 REVISED (not a diff review). HARD DEADLINE: write your entry by minute 25** Revise `tasks/T-037.md` (F007 smoke mode) for the owner's amendment: **agy is dropped; the smoke runs 4 worker runs through 3 doors: claude.economy, codex.economy, cursor.economy …
  Full text: `reviews/entry-39995b58.md`.
- **2026-10-16 — T-046 verified (run 35ecb39a-5c22-4108-acef-41f7fc694ad6, claude.economy, commit 27f3a85): F004 READY FOR ACCEPTANCE (command prepared, not run); grok review found docs contradictions** VERIFY PASS (13 commands = the F004 coverage list, incl. the full suite). Grok (docs review, plan mode) verdict FAIL on consistency, not on the two replacements: `.agents/skills/mcp-hygiene/SKILL.md` rule 5 and its self-check still tell workers to write PROGRESS.md, and `AGENTS.md` ("Mission rules": append the required mission progress record) contradicts the launcher prompt. The first is a small docs task (T-047, queued); AGENTS.md is the owner's file (decision for you).
  **F004 acceptance command (owner decides; I do not run it):** `bash scripts/accept-feature.sh --run-id 35ecb39a-5c22-4108-acef-41f7fc694ad6 --verification-sha256 64e8240bde0c6b62f682024a2c4f7ac56b8e433abdbc9d73d23dcd6d68d16268 --accepted-by "<identity>" docs/missions/20261014-2a-foundation`, then `bash scripts/verify-mission.sh --require-workers docs/missions/20261014-2a-foundation`. F004 is accepted on the amended steps (agy removed).
- **2026-10-16 — T-046 written by the Front Desk: F004 acceptance run (rule 6 checked incl. full suite); dispatch on claude.economy** Verification = the T-026 coverage list without the agy/chair step (`encodings` check cursor-only), plus an oracle for a tiny docs change that gives the run a real change (ORCHESTRATION.md worker step; mcp-hygiene skill). Rule 6: the oracle fails on base, passes after; the 12 coverage commands pass on both (an acceptance run proves existing work); full suite passes after. Review: grok (docs). AGENTS.md and docs/templates/AGENTS.md.template still say "one entry appended to mission PROGRESS.md": owner's files, not touched (decision for you).
