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
- **2026-10-16 — ARCHITECT PLANNING REQUEST (two deliverables; write this file only; put patches/scripts as text blocks)** **A. Ledger task (owner step 2), design for ONE economy-seat task with a REFERENCE PATCH.** Items: (a) new source value `configured` for requested_model, resolved_model, effort (from spec/receipt configuration); `observed` only for what the CLI reported; (b) `door` holds the real door name from the registry (cursor-composer, cursor-grok, ...) and a separate `tier` field is added (schema, validator, runner row builder, fixtures, view/fold readers); (c) fix the pool lookup that counts Grok at standard speed as Composer; (d) read pool and billing_class at the run's `base_commit` (git show of harness-registry.json), so a worker cannot rewrite its own row. Check what committed rows exist (`docs/missions/ledger.jsonl` does not exist yet, `.tasks/ledger/*.json` do) and say whether old local rows need migration or can be dropped.
  **Owner process rule, you apply it:** build the reference patch in a scratch clone of HEAD (`git archive`), then show (1) every verification command FAILS on the base and PASSES after the patch, (2) the list of mutants of the patch and which test kills each. Deliver: the task text (allow-list, verification commands as JSON argv, "why each check exists", long-command rule, mutation list as file:line:expression instructions), the reference patch as a unified diff in a fenced block, and the expected files list. The worker will NOT see the patch.
  **B. Proposal text for `docs/proposals/20261016-structured-progress.md` (max 2 pages):** progress.jsonl (one event per run, review, decision, amendment, lesson or gate; schema-validated: feature, task, run_id, type, status, link), `progress.py add` as the only writer and `progress.py brief --task T-xxx` (task file + events of its feature and dependencies + last few events + active lessons for its category), PROGRESS.md generated read-only, prose in linked files. Say whether it should start 2B or be pulled into 2A, with cost estimate in tasks. Proposal only.
  **C.** one paragraph: how to make rule 6 (fail on base, pass after a scripted edit) cheap for the Front Desk for every future task; no code.
- **2026-10-16 — cursor.premium re-frozen to grok-4.7-high (drift event, owner approved); smoke passed** `fleet.json` cursor.premium: model `grok-4.7-xhigh`/effort medium → `grok-4.7-high`/effort high, speed standard (never fast); `validate-fleet` exit 0. The file was chmod'd writable for this one edit and set back to 444. Drift event written locally to `.tasks/drift/20261014-2a-foundation.jsonl` (folded into the committed drift.jsonl by the T-030 fold at F005 acceptance).
  Seat smoke (`fleet-doctor.sh --smoke --seat cursor.premium`, two runs; the first with --keep): completed, "both smoke files in HEAD", run d240aeaf-5a16-4621-aeb4-37460a329b25. The kept scratch clone was removed. cursor.premium joins rotation, used first for routine reviews.
- **2026-10-16 — F003 and F006 accepted (owner approved)** F003: run 86a9c529-95d9-42b3-9e23-b24c18fec0ff, record sha a85b3ac1…, `ACCEPT OK`; F006: run db01ac53-00de-4d30-9230-05894b952ebe, sha recomputed d652eeea… before running, `ACCEPT OK`.
  `verify-mission.sh --require-workers` after each: `VERIFY OK`, exit 0. Accepted by "Front Desk (claude-sonnet-5-5), owner-approved by Zamir (2026-10-16)". features.json committed.
- **2026-10-16 — PROGRESS.md reset (owner step 0)** Moved all 250 entries (717 KB) verbatim to `progress-archive/2026-10-14_15.md`; PROGRESS.md now holds status, decisions in force, open decisions, active lessons and recent entries (5.4 KB).
  Reviewer outputs go to `reviews/<run-id>.md`; workers no longer write this file (launcher prompt and template change to follow as a task).
  The structured-progress proposal is the next Architect planning run.
- **2026-10-15 — day 3 stop report.** Stopped because everything left needed agy or an owner decision. 21 worker runs on day 3 (11 first-time done, 10 task failures after review, 3 not attributable); no limit hit; F005/F006 ready for acceptance; T-036 done; agy still hangs in repo and fresh folder; Cursor Opus ids are credit-only. Details: `progress-archive/2026-10-14_15.md` (entries "MORNING REPORT — DAY 3" and "CORRECTION").
- **2026-10-15 — T-034 chain closed.** Three task failures, Architect redesign (budgeted greedy scan), R3 + R4 verified and reviewed. Archive entry "redesign of the --after-run extractor".
- **2026-10-15 — T-030 chain closed.** Fold keyed on run_id, 4-key drift shape, no cap on committed targets. Archive entries "T-030", "T-030-R1", "T-030-R2".
- **2026-10-15 — T-028-R4 / T-029 chain closed.** Privacy rule extended; ledger step never changes a run's outcome. Archive entries "T-028-R4", "T-029-R1..R3".
- **2026-10-15 — F005/F006 acceptance commands prepared** (see the day-3 correction in the archive; superseded by the approved sequence above).
