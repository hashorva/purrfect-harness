---
note: Current state only. Full history is in progress-archive/ (read-only). Newest entry on top; at most 10 lines per entry; full reviewer outputs go to reviews/<run-id>.md. Workers do not write this file; the Front Desk records each run from its receipt.
---

# Progress

## Current status (2026-10-16)
- Mission 2A Foundation, branch `mission/2a-foundation`, status in-progress. Gate 0 passed. **Gate 1 target:** F001–F006 accepted and the deterministic suite green (prepare, do not advance).
- **Accepted:** F001, F003, F006. **Waiting on one task (ledger fixes):** F005. **F004** and **F007** wait for the agy amendment (agy dropped from the mission by owner decision; T-026 and T-039 deferred).
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
- **2026-10-16 — T-042 reviewed by Opus: PASS (calibration 2 of 3: same blocking verdict; grok missed 3 surviving mutants and a NUL base_commit ValueError, one grok point did not reproduce)** Opus run 983ac285-bf93-4096-bedf-1a038df9dd89, full text `reviews/983ac285-bf93-4096-bedf-1a038df9dd89.md`. Non-blocking: N2 a NUL in `base_commit` raises an uncaught ValueError (WARN, no leak); N3 every read path validates against the working-tree registry, so retiring/renaming a door later would break fold/view of historical rows (needs a decision before any door change); N5 launcher lock release still reads the working-tree registry.
  Next: set the v1 rows aside, fold, accept F005 in one commit.
- **2026-10-16 — BRAIN review (Opus) of T-042 / commit 0e3ceba — calibration review 2, Opus side. Run 983ac285-bf93-4096-bedf-1a038df9dd89, log `.tasks/logs/983ac285-bf93-4096-bedf-1a038df9dd89.log`. Verdict PASS, no blocking issues.** Attribution: receipt fdf5dd38 (codex.economy, attempt 2): comple …
  Full text: `reviews/entry-0a56dc8b.md`.
- **2026-10-16 — T-042 verified (run fdf5dd38-1433-45eb-972b-823493f9e671, attempt 2 codex.economy); calibration review 2 of 3 grok done; Opus review requested** Record VERIFY PASS (7 commands incl. both oracles and the full suite); commit 0e3ceba. Grok review (read-only, did not execute tests): PAS …
  Full text: `reviews/entry-ebf16b6a.md`.
- **2026-10-15 — T-042 attempt 1 (cursor.economy, run f87755da-6925-41a0-80e8-bf7ee4d78002): no commit, a test still failing — task failure** Receipt: completed, exit 0, scope pass, 5 paths, but commits [] and a dirty tree (a verifier cannot use it). Work preserved as `.tasks/wip/T-042-a1.patch` (unverified), tree restored. The worker's log shows it read the reference patch from `.tasks/plans/`: incident — reference patches now live outside the repository tree (session scratchpad). Class task (cursor.economy × ledger).
  Attempt 2 on codex.economy with the wip patch as a starting point and an explicit commit instruction (task-text change recorded).
- **2026-10-15 — T-042 ready (rule 6 checked, incl. full suite after the patch); dispatch on cursor.economy** Architect plan run 5f1c114d-66d5-410e-b383-06108375ed7e: task text, 23-style mutant list (`reviews/5f1c114d-66d5-410e-b383-06108375ed7e-mutants.md`), reference patch kept local (`.tasks/plans/T-042-reference.patch`). My check: 2 oracle commands fail on base and pass after the patch; the full suite passes after the patch.
- **2026-10-15 — ARCHITECT PLANNING RUN T-042 (brain run 5f1c114d-66d5-410e-b383-06108375ed7e, log `.tasks/logs/5f1c114d-66d5-410e-b383-06108375ed7e.log`): T-042 delivered complete.** Planning only. No worker ran, no commits were reviewed, and this run wrote only this file. The blocks are at the end …
  Full text: `reviews/entry-0b7c18f9.md`.
- **2026-10-15 — ARCHITECT PLANNING RUN T-042 (not a diff review; time box 30 min; entry max 10 lines)** Design T-042 (task text + reference patch + mutants, owner rule 6) for ledger item (d): pool and billing_class read from `harness-registry.json` at the run's `spec.base_commit` (`git -C <repo> sh …
  Full text: `reviews/entry-18e92843.md`.
- **2026-10-15 — T-041 reviewed by Opus: PASS (calibration 1 of 3: grok and Opus agree on blocking, grok missed 2 non-blocking)** Opus run cb23708f-7387-4c3b-85b0-77df3be10740, full text `reviews/cb23708f-7387-4c3b-85b0-77df3be10740.md`: 32 hostile probes refused without echo, 30 mutants all killed. Non-blocking: N1 validator accepts any non-empty `door` (check against registry doors in T-042); N2 one mutant is killed only by an oracle; N3 the local v1 rows of this mission must be set aside before the F005 fold; N4 grok's output had no evidence (19 bytes).
  Calibration row appended to routing-data.jsonl (`type: review-calibration`). Next: T-042 (pool/billing at base_commit + door check) via an Architect planning run, then fold + F005 acceptance.
- **2026-10-15 — BRAIN review (Opus) of T-041 / commit 0bff888 — calibration review 1, Opus side. Run cb23708f-7387-4c3b-85b0-77df3be10740, log `.tasks/logs/cb23708f-7387-4c3b-85b0-77df3be10740.log`. Verdict PASS, no blocking issues.** Attribution: receipt a5343e36 (codex.economy) lists commit 0bff8 …
  Full text: `reviews/entry-8b9aad05.md`.
